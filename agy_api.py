import asyncio
import json
import subprocess
import time
import os
import glob
# Load environment variables including proxy bypass settings from ~/.hermes/.env
env_file = os.path.expanduser("~/.hermes/.env")
if os.path.exists(env_file):
    try:
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    os.environ[key] = val
    except Exception as e:
        print(f"Error loading .env file: {e}", flush=True)
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union

class ThinkingParser:
    def __init__(self, debug_file: Optional[str] = None):
        self.buffer = ""
        self.in_thinking = False
        self.debug_file = debug_file
        if self.debug_file:
            try:
                os.makedirs(os.path.dirname(self.debug_file), exist_ok=True)
                with open(self.debug_file, "a") as f:
                    f.write(f"\n--- NEW STREAM SESSION: {int(time.time())} ---\n")
            except Exception as e:
                print(f"Error initializing debug file: {e}", flush=True)

    def feed(self, text: str) -> List[tuple]:
        if self.debug_file:
            try:
                with open(self.debug_file, "a") as f:
                    f.write(f"FEED CHUNK: {repr(text)}\n")
            except Exception:
                pass

        self.buffer += text
        results = []

        tags = [
            ("<think>", True), ("</think>", False),
            ("<thinking>", True), ("</thinking>", False),
            ("<thought>", True), ("</thought>", False),
            ("Thoughts:", True), ("Response:", False)
        ]

        while self.buffer:
            first_idx = -1
            found_tag = None
            is_start = False

            for tag, start in tags:
                idx = self.buffer.find(tag)
                if idx != -1:
                    if first_idx == -1 or idx < first_idx:
                        first_idx = idx
                        found_tag = tag
                        is_start = start

            if first_idx != -1:
                pre_text = self.buffer[:first_idx]
                if pre_text:
                    results.append(("thinking" if self.in_thinking else "content", pre_text))

                self.in_thinking = is_start
                self.buffer = self.buffer[first_idx + len(found_tag):]
            else:
                max_possible_partial_len = 0
                for tag, _ in tags:
                    for i in range(1, len(tag)):
                        if self.buffer.endswith(tag[:i]):
                            max_possible_partial_len = max(max_possible_partial_len, i)

                if max_possible_partial_len > 0:
                    pre_text = self.buffer[:-max_possible_partial_len]
                    if pre_text:
                        results.append(("thinking" if self.in_thinking else "content", pre_text))
                    self.buffer = self.buffer[-max_possible_partial_len:]
                    break
                else:
                    results.append(("thinking" if self.in_thinking else "content", self.buffer))
                    self.buffer = ""
                    break

        if self.debug_file:
            try:
                with open(self.debug_file, "a") as f:
                    f.write(f"PARSED RESULTS: {results}\n")
            except Exception:
                pass

        return results

app = FastAPI(title="Antigravity Pro API Proxy")

class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]

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
AGY_RUN_LOG_DIR = "/Users/arielkurek/.hermes/logs/agy-runs"

# The agy CLI exits 0 with EMPTY stdout on fatal agent errors (quota
# RESOURCE_EXHAUSTED, expired Antigravity login, ...). Each run gets its own
# --log-file so the real failure reason can be extracted and surfaced instead
# of returning a silent empty response that clients retry blindly.
MAX_CONCURRENT_AGY = 3
EMPTY_OUTPUT_RETRIES = 2
EMPTY_OUTPUT_RETRY_DELAY_S = 3.0

agy_semaphore = asyncio.Semaphore(MAX_CONCURRENT_AGY)

# (substring in run log, message for client, retryable)
FATAL_LOG_PATTERNS = [
    ("RESOURCE_EXHAUSTED", "Antigravity quota exhausted (RESOURCE_EXHAUSTED 429).", False),
    ("Failed to get OAuth token", "Antigravity login expired — run `agy` interactively once to re-login.", False),
]

def extract_failure_reason(log_path: str) -> tuple:
    """Parse a per-run agy log for the real failure reason.

    Returns (message or None, retryable).
    """
    try:
        with open(log_path, "r", errors="replace") as f:
            text = f.read()
    except Exception:
        return None, True

    # The authoritative line carries the agent's terminal error
    for line in text.splitlines():
        if "agent executor error:" in line:
            reason = line.split("agent executor error:", 1)[1].strip()
            retryable = "RESOURCE_EXHAUSTED" not in reason
            return reason, retryable

    for needle, message, retryable in FATAL_LOG_PATTERNS:
        if needle in text:
            return message, retryable
    return None, True

def make_run_log_path(chunk_id: str, attempt: int) -> str:
    try:
        os.makedirs(AGY_RUN_LOG_DIR, exist_ok=True)
    except Exception:
        pass
    return os.path.join(AGY_RUN_LOG_DIR, f"{chunk_id}-a{attempt}.log")

def cleanup_run_log(path: str):
    try:
        os.remove(path)
    except Exception:
        pass

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

def detect_and_save_session(session_id: Optional[str], before_files: set, started_at: float):
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
        # Fallback: only consider DBs touched during this request, otherwise a
        # concurrent request's conversation gets mapped to this session.
        db_dir = "/Users/arielkurek/.gemini/antigravity-cli/conversations"
        files = [
            f for f in glob.glob(os.path.join(db_dir, "*.db"))
            if os.path.getmtime(f) >= started_at - 1
        ]
        if files:
            newest = max(files, key=os.path.getmtime)
            agy_conv_id = os.path.basename(newest).replace(".db", "")
            print(f"Re-detected existing conversation ID (newest): '{agy_conv_id}' for session '{session_id}'", flush=True)

    if agy_conv_id:
        save_session_mapping(session_id, agy_conv_id)

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

def make_chunk(chunk_id: str, model_name: str, delta: Dict[str, Any], finish_reason: Optional[str] = None) -> str:
    chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_name,
        "choices": [{
            "index": 0,
            "delta": delta,
            "finish_reason": finish_reason
        }]
    }
    return f"data: {json.dumps(chunk)}\n\n"

@app.get("/health")
async def health():
    return {"status": "ok"}

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
        body_str = str(raw_body)
        print(f"RAW REQUEST BODY: {body_str[:1000]}... (truncated, total length: {len(body_str)})", flush=True)
    except Exception as e:
        print(f"ERROR reading raw body: {e}", flush=True)
    # Formulate the prompt from messages
    # We take the content of the last user message
    last_msg = request.messages[-1]
    if isinstance(last_msg.content, str):
        prompt = last_msg.content
    else:
        text_parts = []
        for part in last_msg.content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        prompt = "\n".join(text_parts)
    model_name = request.model
    mapped_model = map_model_name(model_name, request.reasoning_effort)
    print(f"Mapping request model: '{model_name}' -> '{mapped_model}' (reasoning_effort: '{request.reasoning_effort}')", flush=True)

    # Detect if we should request thinking/reasoning output
    should_think = False
    if "thinking" in model_name.lower() or "thinking" in mapped_model.lower():
        should_think = True
    elif request.reasoning_effort and request.reasoning_effort.lower() in ("high", "xhigh"):
        should_think = True
    elif "high" in mapped_model.lower():
        should_think = True

    if should_think:
        prompt += "\n\n[Please output your detailed thinking/reasoning process wrapped in <think>...</think> tags first, and then provide your final answer.]"
        print(f"Thinking model detected. Appended thinking instruction to prompt.", flush=True)

    session_id = request.session_id
    agy_conv_id = None
    if session_id:
        agy_conv_id = get_agy_conv_id(session_id)
        print(f"Session '{session_id}' maps to conversation ID: '{agy_conv_id}'", flush=True)

    before_files = get_db_files()
    started_at = time.time()

    cmd = ["agy", "--print", prompt, "--print-timeout", "30m", "--dangerously-skip-permissions"]
    if agy_conv_id:
        cmd += ["--conversation", agy_conv_id]
    if mapped_model:
        cmd += ["--model", mapped_model]

    print(f"RUNNING COMMAND: {cmd}", flush=True)

    if request.stream:
        # Return a streamed response if requested
        async def stream_generator():
            chunk_id = f"chatcmpl-{int(time.time())}"
            parser = ThinkingParser(debug_file="/Users/arielkurek/.hermes/logs/agy-api-debug.log")
            last_stderr = ""
            last_return_code = 0

            for attempt in range(EMPTY_OUTPUT_RETRIES + 1):
                emitted_output = False
                return_code = 0
                run_log = make_run_log_path(chunk_id, attempt)
                async with agy_semaphore:
                    try:
                        process = await asyncio.create_subprocess_exec(
                            *cmd, "--log-file", run_log,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            stdin=asyncio.subprocess.DEVNULL,
                            env=os.environ
                        )
                    except Exception as e:
                        print(f"FAILED to start subprocess: {e}", flush=True)
                        yield make_chunk(chunk_id, model_name,
                                         {"content": f"[agy bridge error: failed to start Antigravity CLI: {e}]"},
                                         "stop")
                        yield "data: [DONE]\n\n"
                        return

                    # Collect stderr in memory and mirror to the debug log
                    stderr_lines: List[str] = []
                    async def collect_stderr():
                        try:
                            while True:
                                line = await process.stderr.readline()
                                if not line:
                                    break
                                decoded_line = line.decode('utf-8', errors='replace')
                                stderr_lines.append(decoded_line)
                                try:
                                    with open("/Users/arielkurek/.hermes/logs/agy-api-stderr-debug.log", "a") as f:
                                        f.write(decoded_line)
                                except Exception:
                                    pass
                        except Exception as e:
                            print(f"Error logging stderr: {e}", flush=True)
                    stderr_task = asyncio.create_task(collect_stderr())

                    try:
                        while True:
                            data_chunk = await process.stdout.read(1024)
                            if not data_chunk:
                                break
                            emitted_output = True
                            decoded_text = data_chunk.decode('utf-8', errors='replace')

                            parsed_parts = parser.feed(decoded_text)
                            for block_type, text in parsed_parts:
                                delta = {"reasoning_content": text} if block_type == "thinking" else {"content": text}
                                yield make_chunk(chunk_id, model_name, delta)
                    except Exception as e:
                        print(f"Error reading process output: {e}", flush=True)

                    return_code = await process.wait()
                    await stderr_task
                    last_stderr = "".join(stderr_lines)
                    last_return_code = return_code

                if emitted_output:
                    cleanup_run_log(run_log)
                    # Flush leftover parser buffer if any
                    if parser.buffer:
                        delta = {"reasoning_content": parser.buffer} if parser.in_thinking else {"content": parser.buffer}
                        yield make_chunk(chunk_id, model_name, delta)
                        parser.buffer = ""

                    detect_and_save_session(session_id, before_files, started_at)

                    if return_code != 0:
                        yield make_chunk(chunk_id, model_name,
                                         {"content": f"\n\n[Antigravity CLI Error (exit code {return_code}): {last_stderr}]"},
                                         "stop")
                    else:
                        yield make_chunk(chunk_id, model_name, {}, "stop")
                    yield "data: [DONE]\n\n"
                    return

                # Empty output: nothing has been yielded yet, so retrying is safe.
                reason, retryable = extract_failure_reason(run_log)
                cleanup_run_log(run_log)
                print(f"EMPTY OUTPUT from agy (attempt {attempt + 1}/{EMPTY_OUTPUT_RETRIES + 1}, "
                      f"exit code {return_code}, reason={reason!r}, retryable={retryable}, "
                      f"stderr={last_stderr[:500]!r})", flush=True)
                if reason and not retryable:
                    yield make_chunk(chunk_id, model_name,
                                     {"content": f"[agy bridge error: {reason}]"},
                                     "stop")
                    yield "data: [DONE]\n\n"
                    return
                if attempt < EMPTY_OUTPUT_RETRIES:
                    await asyncio.sleep(EMPTY_OUTPUT_RETRY_DELAY_S)

            # Out of retries, still empty
            detail = f"exit code {last_return_code}"
            if last_stderr:
                detail += f", stderr: {last_stderr[:1000]}"
            yield make_chunk(chunk_id, model_name,
                             {"content": f"[agy bridge error: Antigravity CLI returned empty output after "
                                         f"{EMPTY_OUTPUT_RETRIES + 1} attempts ({detail})]"},
                             "stop")
            yield "data: [DONE]\n\n"

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    # Non-streaming response
    response_text = ""
    last_stderr = ""
    last_return_code = 0
    for attempt in range(EMPTY_OUTPUT_RETRIES + 1):
        run_log = make_run_log_path(f"chatcmpl-{int(started_at)}", attempt)
        async with agy_semaphore:
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd, "--log-file", run_log,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.DEVNULL,
                    env=os.environ
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to start Antigravity CLI: {e}")

            stdout_bytes, stderr_bytes = await process.communicate()
            last_return_code = process.returncode
            last_stderr = stderr_bytes.decode('utf-8', errors='replace')

        if last_return_code != 0:
            cleanup_run_log(run_log)
            raise HTTPException(
                status_code=500,
                detail=f"Antigravity CLI failed (exit code {last_return_code}): {last_stderr}"
            )

        response_text = stdout_bytes.decode('utf-8', errors='replace')
        if response_text.strip():
            cleanup_run_log(run_log)
            break

        reason, retryable = extract_failure_reason(run_log)
        cleanup_run_log(run_log)
        print(f"EMPTY OUTPUT from agy (attempt {attempt + 1}/{EMPTY_OUTPUT_RETRIES + 1}, "
              f"reason={reason!r}, retryable={retryable}, stderr={last_stderr[:500]!r})", flush=True)
        if reason and not retryable:
            raise HTTPException(status_code=502, detail=f"agy bridge: {reason}")
        if attempt < EMPTY_OUTPUT_RETRIES:
            await asyncio.sleep(EMPTY_OUTPUT_RETRY_DELAY_S)

    if not response_text.strip():
        raise HTTPException(
            status_code=502,
            detail=f"Antigravity CLI returned empty output after {EMPTY_OUTPUT_RETRIES + 1} attempts "
                   f"(exit code {last_return_code}, stderr: {last_stderr[:1000]})"
        )

    detect_and_save_session(session_id, before_files, started_at)

    # Parse thoughts for non-streaming response
    parser = ThinkingParser()
    parsed_parts = parser.feed(response_text)
    thinking_text = "".join(part[1] for part in parsed_parts if part[0] == "thinking")
    content_text = "".join(part[1] for part in parsed_parts if part[0] == "content")
    if parser.buffer:
        if parser.in_thinking:
            thinking_text += parser.buffer
        else:
            content_text += parser.buffer

    message_dict = {
        "role": "assistant",
        "content": content_text
    }
    if thinking_text:
        message_dict["reasoning_content"] = thinking_text

    return {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [{
            "index": 0,
            "message": message_dict,
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
