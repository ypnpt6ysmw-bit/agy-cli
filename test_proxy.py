import urllib.request
import json
import sys
import os

# Bypass proxies for local tests
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"
for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
    if key in os.environ:
        del os.environ[key]

def test_models():
    print("Testing /v1/models...")
    try:
        req = urllib.request.Request("http://localhost:8000/v1/models")
        with urllib.request.urlopen(req) as response:
            res = response.read().decode('utf-8')
            print("Models Response:", res)
            assert "Gemini 3.5 Flash" in res
            print("Models test passed!\n")
    except Exception as e:
        print("Models test failed:", e)
        sys.exit(1)

def test_chat_completions(model="Gemini 3.5 Flash", prompt="say hello in exactly three words", stream=False):
    print(f"Testing /v1/chat/completions (model={model}, stream={stream})...")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "stream": stream
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        "http://localhost:8000/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            if stream:
                print("Streaming response:")
                has_reasoning = False
                has_content = False
                for line in response:
                    line_str = line.decode('utf-8').strip()
                    if line_str and line_str.startswith("data:"):
                        # Try parsing JSON to check reasoning vs content
                        try:
                            json_str = line_str[5:].strip()
                            if json_str == "[DONE]":
                                print(line_str)
                                continue
                            data_json = json.loads(json_str)
                            delta = data_json["choices"][0]["delta"]
                            if "reasoning_content" in delta:
                                has_reasoning = True
                                print(f"[THINKING] {repr(delta['reasoning_content'])}")
                            if "content" in delta:
                                has_content = True
                                print(f"[CONTENT] {repr(delta['content'])}")
                        except Exception as parse_err:
                            print(f"Error parsing line: {line_str} - {parse_err}")
                print(f"Streaming completions test completed! Has reasoning: {has_reasoning}, Has content: {has_content}\n")
            else:
                res = response.read().decode('utf-8')
                print("Completions Response:", res)
                # Verify JSON structure
                data_json = json.loads(res)
                msg = data_json["choices"][0]["message"]
                if "reasoning_content" in msg:
                    print(f"Found reasoning: {repr(msg['reasoning_content'])}")
                print(f"Found content: {repr(msg['content'])}")
                print("Non-streaming completions test passed!\n")
    except Exception as e:
        print("Completions test failed:", e)
        sys.exit(1)

if __name__ == "__main__":
    test_models()
    test_chat_completions(model="Gemini 3.5 Flash", stream=False)
    test_chat_completions(model="Gemini 3.5 Flash", stream=True)
    print("--- Claude Sonnet 4.6 (Thinking Model) Tests ---")
    test_chat_completions(model="Claude Sonnet 4.6", prompt="why is the sky blue?", stream=True)
