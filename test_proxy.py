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

def test_chat_completions(stream=False):
    print(f"Testing /v1/chat/completions (stream={stream})...")
    payload = {
        "model": "Gemini 3.5 Flash",
        "messages": [
            {
                "role": "user",
                "content": "say hello in exactly three words"
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
                for line in response:
                    line_str = line.decode('utf-8').strip()
                    if line_str:
                        print(line_str)
                print("Streaming completions test completed!\n")
            else:
                res = response.read().decode('utf-8')
                print("Completions Response:", res)
                assert "hello" in res.lower() or "world" in res.lower()
                print("Non-streaming completions test passed!\n")
    except Exception as e:
        print("Completions test failed:", e)
        sys.exit(1)

if __name__ == "__main__":
    test_models()
    test_chat_completions(stream=False)
    test_chat_completions(stream=True)
