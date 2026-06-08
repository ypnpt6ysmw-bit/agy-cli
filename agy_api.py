import asyncio
import json
import subprocess
import time
from fastapi import FastAPI, HTTPException
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

def run_agy_print(prompt: str, model: str) -> str:
    # Run the wrapped agy command with stdin redirected to DEVNULL
    cmd = ["agy", "--print", prompt]
    if model:
        cmd += ["--model", model]
    
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

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    # Formulate the prompt from messages
    # We take the content of the last user message
    prompt = request.messages[-1].content
    model_name = request.model
    
    if request.stream:
        # Return a streamed response if requested
        async def stream_generator():
            # Run the command in a separate thread so it doesn't block the async loop
            response_text = await asyncio.to_thread(run_agy_print, prompt, model_name)
            
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
    response_text = await asyncio.to_thread(run_agy_print, prompt, model_name)
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
