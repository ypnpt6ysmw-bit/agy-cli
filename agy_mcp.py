import subprocess
from mcp.server import fastmcp

mcp = fastmcp.FastMCP("Antigravity")

@mcp.tool()
def ask_antigravity(prompt: str, model: str = "") -> str:
    """Sends a prompt to the Google Antigravity Agent and returns the response.
    
    This agent runs with access to the local workspace and is powered by the
    configured Gemini/Claude models using your Antigravity Pro subscription.
    """
    cmd = ["agy", "--print", prompt, "--dangerously-skip-permissions"]
    if model:
        cmd += ["--model", model]
        
    res = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True
    )
    if res.returncode != 0:
        return f"Error running Antigravity CLI: {res.stderr or res.stdout}"
    return res.stdout

def main():
    mcp.run()

if __name__ == "__main__":
    main()
