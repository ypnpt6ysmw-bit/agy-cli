import asyncio
import click
import os
from dotenv import load_dotenv
from google.antigravity import Agent, LocalAgentConfig

# Load environment variables from .env if present
load_dotenv()

@click.group()
def cli():
    """Google Antigravity CLI Tool (agy)."""
    # Ensure GEMINI_API_KEY is configured
    if not os.environ.get("GEMINI_API_KEY"):
        click.echo(
            click.style(
                "WARNING: GEMINI_API_KEY environment variable is not set.\n"
                "Please set it or create a .env file containing:\n"
                "GEMINI_API_KEY=your_api_key_here\n"
                "Get a key at: https://aistudio.google.com/app/api-keys",
                fg="yellow"
            )
        )

@cli.command()
@click.option(
    "--model",
    default=None,
    help="Gemini model identifier to use (defaults to gemini-3.5-flash)."
)
@click.option(
    "--system-instructions",
    default=None,
    help="System instructions or persona for the agent."
)
def chat(model, system_instructions):
    """Start an interactive chat session with the Antigravity agent."""
    async def run_chat():
        config = LocalAgentConfig(
            model=model or "gemini-3.5-flash",
            system_instructions=system_instructions
        )
        async with Agent(config=config) as agent:
            click.echo(click.style("Starting interactive Antigravity loop...", fg="cyan"))
            await agent.run_interactive_loop()

    try:
        asyncio.run(run_chat())
    except KeyboardInterrupt:
        click.echo("\nGoodbye!")

@cli.command()
@click.argument("prompt")
@click.option(
    "--model",
    default=None,
    help="Gemini model identifier to use."
)
@click.option(
    "--thoughts/--no-thoughts",
    default=False,
    help="Stream internal model thoughts/reasoning before the final answer."
)
def ask(prompt, model, thoughts):
    """Send a single prompt to the agent and stream the response."""
    async def run_ask():
        config = LocalAgentConfig(model=model or "gemini-3.5-flash")
        async with Agent(config=config) as agent:
            response = await agent.chat(prompt)
            
            if thoughts:
                click.echo(click.style("Thoughts:", fg="magenta"))
                async for token in response.thoughts:
                    click.echo(token, edit=False, nl=False)
                click.echo("\n" + click.style("Response:", fg="cyan"))
            
            async for token in response:
                click.echo(token, edit=False, nl=False)
            click.echo()

    asyncio.run(run_ask())

@cli.command()
def info():
    """Show active configuration details and credentials check."""
    key = os.environ.get("GEMINI_API_KEY")
    masked_key = f"{key[:8]}...{key[-4:]}" if key else "Not set"
    click.echo(click.style("--- Antigravity CLI Configuration ---", fg="cyan"))
    click.echo(f"GEMINI_API_KEY: {masked_key}")
    click.echo(f"Working Directory: {os.getcwd()}")

if __name__ == "__main__":
    cli()
