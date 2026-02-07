"""CLI interface for tokentap."""

import asyncio
import json
import threading
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console

from tokentap.config import DEFAULT_PROXY_PORT, DEFAULT_TOKEN_LIMIT, DEFAULT_PROMPTS_DIR, DEFAULT_UPSTREAM_HOST
from tokentap.dashboard import TokenTapDashboard
from tokentap.proxy import ProxyServer

console = Console()


def save_prompt_to_file(event: dict, prompts_dir: Path) -> None:
    """Save a prompt to markdown and raw JSON files."""
    prompts_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.fromisoformat(event["timestamp"])
    base_filename = timestamp.strftime(f"%Y-%m-%d_%H-%M-%S_{event['provider']}")

    # Save markdown file (human-readable)
    md_filepath = prompts_dir / f"{base_filename}.md"
    lines = [
        f"# Prompt - {timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Provider:** {event['provider'].capitalize()}",
        f"**Model:** {event['model']}",
        f"**Tokens:** {event['tokens']:,}",
        "",
        "## Messages",
    ]

    for msg in event.get("messages", []):
        role = msg.get("role", "unknown").capitalize()
        content = msg.get("content", "")
        lines.append(f"### {role}")
        lines.append(content)
        lines.append("")

    md_filepath.write_text("\n".join(lines))

    # Save raw JSON file (original request body)
    raw_body = event.get("raw_body")
    if raw_body is not None:
        json_filepath = prompts_dir / f"{base_filename}.json"
        json_filepath.write_text(json.dumps(raw_body, indent=2))


def get_prompts_dir_interactive() -> Path:
    """Prompt user for prompts directory."""
    console.print(f"[cyan]Directory to save prompts (press Enter for default):[/cyan]")
    console.print(f"[dim]Default: {DEFAULT_PROMPTS_DIR}[/dim]")

    try:
        user_input = input("> ").strip()
    except EOFError:
        user_input = ""

    if user_input:
        return Path(user_input).expanduser().resolve()
    return DEFAULT_PROMPTS_DIR

def get_upstream_host_interactive() -> Path:
    """Prompt user for upstream host."""
    console.print(f"[cyan]Host to proxy (press Enter for default):[/cyan]")
    console.print(f"[dim]Default: {DEFAULT_UPSTREAM_HOST}[/dim]")

    try:
        user_input = input("> ").strip()
    except EOFError:
        user_input = ""

    if user_input:
        return user_input
    return DEFAULT_UPSTREAM_HOST

@click.command()
@click.option("--port", "-p", default=DEFAULT_PROXY_PORT, help="Proxy port number")
@click.option("--limit", "-l", default=DEFAULT_TOKEN_LIMIT, help="Token limit for fuel gauge")
def main(port: int, limit: int):
    """Start the proxy and dashboard.
    """

    print(Path(".").resolve())
    base_url = get_upstream_host_interactive()
    
    prompts_dir = get_prompts_dir_interactive()
    prompts_dir.mkdir(parents=True, exist_ok=True)

    # Create dashboard
    dashboard = TokenTapDashboard(token_limit=limit)

    # Event queue for thread-safe communication
    event_queue = []
    event_lock = threading.Lock()

    def on_request(event: dict) -> None:
        """Handle incoming request event."""
        # Save prompt to file
        save_prompt_to_file(event, prompts_dir)
        # Queue event for dashboard
        with event_lock:
            event_queue.append(event)

    def poll_events() -> list[dict]:
        """Poll for new events (called by dashboard)."""
        with event_lock:
            events = event_queue.copy()
            event_queue.clear()
        return events

    # Create and start proxy
    proxy = ProxyServer(
        base_url=base_url,
        port=port,
        on_request=on_request
    )

    loop = asyncio.new_event_loop()

    def run_proxy():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(proxy.start())
        loop.run_forever()

    proxy_thread = threading.Thread(target=run_proxy, daemon=True)
    proxy_thread.start()

    # Give proxy time to start
    import time
    time.sleep(0.5)

    console.print(f"[green]Proxy running on http://127.0.0.1:{port}[/green]")
    console.print(f"[green]Saving prompts to {prompts_dir}[/green]")
    console.print()
    console.print("[dim]Starting dashboard...[/dim]")

    import time
    time.sleep(1)

    # Run dashboard
    try:
        dashboard.run(poll_events)
    except KeyboardInterrupt:
        pass
    finally:
        loop.call_soon_threadsafe(loop.stop)
        console.print()
        console.print(f"[cyan]Session complete. Total: {dashboard.total_tokens:,} tokens across {len(dashboard.requests)} requests.[/cyan]")


if __name__ == "__main__":
    main()
