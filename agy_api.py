import asyncio
import json
import subprocess
import time
import os
import glob
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

app = FastAPI(title="Antigravity Pro API Proxy")

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    stream: Optional[bool] = False
    temperature: Optional[float] = None
    reasoning_effort: Optional[str] = None
    session_id: Optional[str] = None
    
    class Config:
        extra = "allow"

SESSION_FILE = "/Users/arielkurek/.hermes/agy-api/sessions.json"

def get_agy_conv_id(session_id: str) -> Optional[str]:
    if not os.path.exists(SESSION_FILE):
        return None
    try:
        with open(SESSION_FILE, "r") as f:
            data = json.load(f)
            return data.get(session_id)
    except Exception as e:
        print(f"Error reading session file: {e}", flush=True)
        return None

def save_session_mapping(session_id: str, agy_conv_id: str):
    data = {}
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading session file for save: {e}", flush=True)
    
    data[session_id] = agy_conv_id
    try:
        os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
        with open(SESSION_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error writing session file: {e}", flush=True)

def get_db_files() -> set:
    db_dir = "/Users/arielkurek/.gemini/antigravity-cli/conversations"
    if not os.path.exists(db_dir):
        return set()
    return set(glob.glob(os.path.join(db_dir, "*.db")))

def detect_and_save_session(session_id: Optional[str], before_files: set):
    if not session_id:
        return
    
    after_files = get_db_files()
    new_files = after_files - before_files
    
    agy_conv_id = None
    if new_files:
        new_db_file = list(new_files)[0]
        agy_conv_id = os.path.basename(new_db_file).replace(".db", "")
        print(f"Detected new conversation ID: '{agy_conv_id}' for session '{session_id}'", flush=True)
    else:
        # Fallback to the most recently modified database file
        db_dir = "/Users/arielkurek/.gemini/antigravity-cli/conversations"
        files = glob.glob(os.path.join(db_dir, "*.db"))
        if files:
            newest = max(files, key=os.path.getmtime)
            agy_conv_id = os.path.basename(newest).replace(".db", "")
            print(f"Re-detected existing conversation ID (newest): '{agy_conv_id}' for session '{session_id}'", flush=True)
            
    if agy_conv_id:
        save_session_mapping(session_id, agy_conv_id)

def run_agy_print(prompt: str, model: str, conversation_id: Optional[str] = None) -> str:
    # Run the wrapped agy command with stdin redirected to DEVNULL
    cmd = ["agy", "--print", prompt]
    if conversation_id:
        cmd += ["--conversation", conversation_id]
    if model:
        cmd += ["--model", model]
    
    print(f"RUNNING COMMAND: {cmd}", flush=True)
    res = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True
    )
    if res.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Antigravity CLI failed: {res.stderr or res.stdout}"
        )
    return res.stdout

def map_model_name(model_name: str, reasoning_effort: Optional[str]) -> str:
    name = model_name.strip()
    effort = (reasoning_effort or "").strip().lower()
    
    # Gemini 3.1 Pro mapping
    if "gemini 3.1 pro" in name.lower() or "gemini-3.1-pro" in name.lower():
        if effort in ("high", "xhigh"):
            return "Gemini 3.1 Pro (High)"
        else:
            return "Gemini 3.1 Pro (Low)"
            
    # Gemini 3.5 Flash mapping
    if "gemini 3.5 flash" in name.lower() or "gemini-3.5-flash" in name.lower():
        if effort in ("high", "xhigh"):
            return "Gemini 3.5 Flash (High)"
        elif effort in ("low", "minimal"):
            return "Gemini 3.5 Flash (Low)"
        else:
            return "Gemini 3.5 Flash (Medium)"
            
    # Claude Sonnet 4.6 mapping
    if "claude sonnet 4.6" in name.lower() or "claude-sonnet-4.6" in name.lower():
        return "Claude Sonnet 4.6 (Thinking)"
        
    # Claude Opus 4.6 mapping
    if "claude opus 4.6" in name.lower() or "claude-opus-4.6" in name.lower():
        return "Claude Opus 4.6 (Thinking)"
        
    # GPT-OSS 120B mapping
    if "gpt-oss 120b" in name.lower() or "gpt-oss-120b" in name.lower():
        return "GPT-OSS 120B (Medium)"
        
    return name

@app.get("/v1/models")
async def list_models():
    models_list = [
        "Gemini 3.5 Flash",
        "Gemini 3.1 Pro",
        "Claude Sonnet 4.6",
        "Claude Opus 4.6",
        "GPT-OSS 120B"
    ]
    return {
        "object": "list",
        "data": [
            {
                "id": m,
                "object": "model",
                "created": 1717800000,
                "owned_by": "antigravity"
            } for m in models_list
        ]
    }

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest, raw_request: Request):
    try:
        raw_body = await raw_request.json()
        print(f"RAW REQUEST BODY: {raw_body}", flush=True)
    except Exception as e:
        print(f"ERROR reading raw body: {e}", flush=True)
    # Formulate the prompt from messages
    # We take the content of the last user message
    prompt = request.messages[-1].content
    model_name = request.model
    mapped_model = map_model_name(model_name, request.reasoning_effort)
    print(f"Mapping request model: '{model_name}' -> '{mapped_model}' (reasoning_effort: '{request.reasoning_effort}')", flush=True)
    
    session_id = request.session_id
    agy_conv_id = None
    if session_id:
        agy_conv_id = get_agy_conv_id(session_id)
        print(f"Session '{session_id}' maps to conversation ID: '{agy_conv_id}'", flush=True)
        
    before_files = get_db_files()
    
    if request.stream:
        # Return a streamed response if requested
        async def stream_generator():
            # Run the command in a separate thread so it doesn't block the async loop
            response_text = await asyncio.to_thread(run_agy_print, prompt, mapped_model, agy_conv_id)
            detect_and_save_session(session_id, before_files)
            
            chunk_id = f"chatcmpl-{int(time.time())}"
            # Stream response chunks by yielding chunks
            # For simplicity, we chunk by words to simulate streaming
            words = response_text.split(" ")
            for i, word in enumerate(words):
                space = " " if i < len(words) - 1 else ""
                chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_name,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": word + space},
                        "finish_reason": None
                    }]
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                await asyncio.sleep(0.01)
            
            # Final chunk
            final_chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model_name,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }]
            }
            yield f"data: {json.dumps(final_chunk)}\n\n"
            yield "data: [DONE]\n\n"
 
        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    
    # Non-streaming response
    response_text = await asyncio.to_thread(run_agy_print, prompt, mapped_model, agy_conv_id)
    detect_and_save_session(session_id, before_files)
    
    return {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": response_text
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
    }

def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

if __name__ == "__main__":
    main()
