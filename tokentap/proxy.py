"""HTTP relay proxy for intercepting LLM API traffic."""

import ssl
import json
from pathlib import Path
from typing import Callable
from datetime import datetime
from urllib.parse import urlparse

import aiohttp
from aiohttp import web

from tokentap.parser import count_tokens, parse_anthropic_request, parse_openai_request


class ProxyServer:
    """HTTP relay proxy that forwards requests to upstream APIs."""

    def __init__(
        self,
        base_url: str,
        port: int,
        prompts_dir: Path,
        on_request: Callable[[dict], None] | None = None,
    ):
        """Initialize the proxy server.

        Args:
            port: Local port to listen on
            on_request: Callback function called with parsed request data
        """
        self.base_url = base_url
        self.port = port
        self.on_request = on_request
        self.prompts_dir = prompts_dir
        self.app = web.Application()
        self.app.router.add_route("*", "/{path:.*}", self.handle_request)
        self._runner = None
        self._site = None

    async def handle_request(self, request: web.Request) -> web.Response:
        """Handle incoming request and forward to upstream."""
        path = "/" + request.match_info.get("path", "")
        if request.query_string:
            path += "?" + request.query_string

        upstream_base = self.base_url
        upstream_url = upstream_base + path

        # Read request body
        body = await request.read()

        # Parse and count tokens for supported endpoints
        parsed = self._parse_request(body, path)
        if body and self.on_request:
            self.on_request(parsed)
            self._save_prompt_to_file(parsed)

        # Forward request to upstream
        headers = dict(request.headers)
        headers.pop("Host", None)
        headers.pop("Content-Length", None)

        ssl_context = ssl.create_default_context()
        timestamp = datetime.fromisoformat(parsed["timestamp"])
        base_filename = timestamp.strftime(f"%Y-%m-%d_%H-%M-%S_{parsed['provider']}")
        response_filename = self.prompts_dir / f"{base_filename}_chunks.txt"
        chunks = []

        try:
            with open(response_filename, "wb") as response_fp:
                async with aiohttp.ClientSession() as session:
                    async with session.request(
                        method=request.method,
                        url=upstream_url,
                        headers=headers,
                        data=body,
                        ssl=ssl_context,
                    ) as upstream_response:
                        resp = web.StreamResponse(status=upstream_response.status)
                        for k, v in upstream_response.headers.items():
                            resp.headers[k] = v
                        await resp.prepare(request)

                        async for chunk in upstream_response.content:
                            await resp.write(chunk)
                            response_fp.write(chunk)
                            chunks.append(chunk.decode("utf8"))
                        await resp.write_eof()
                        self._write_response_to_file(parsed, chunks)
                        return resp
        except aiohttp.ClientError as e:
            return web.Response(
                status=502,
                text=f"Upstream error: {e}",
            )

    def _parse_request(self, body: bytes, path: str) -> None:
        """Process request body for token counting and logging."""
        default = {
            "timestamp": datetime.now().isoformat(),
            "provider": urlparse(self.base_url).netloc,
            "path": path,
        }
        if not body:
            return default
        try:
            body_dict = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return default

        if "/v1/messages" in path:
            parsed = parse_anthropic_request(body_dict)
        else:
            parsed = parse_openai_request(body_dict)

        if parsed and self.on_request:
            tokens = count_tokens(parsed.get("total_text", ""))
            event = {
                "timestamp": datetime.now().isoformat(),
                "provider": urlparse(self.base_url).netloc,
                "model": parsed.get("model", "unknown"),
                "tokens": tokens,
                "messages": parsed.get("messages", []),
                "raw_body": body_dict,
                "path": path,
            }
            return event

    async def start(self) -> None:
        """Start the proxy server."""
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "127.0.0.1", self.port)
        await self._site.start()

    async def stop(self) -> None:
        """Stop the proxy server."""
        if self._runner:
            await self._runner.cleanup()
    
    def _write_response_to_file(self, parsed, chunks):
        timestamp = datetime.fromisoformat(parsed["timestamp"])
        base_filename = timestamp.strftime(f"%Y-%m-%d_%H-%M-%S_{parsed['provider']}")
        response_filename = self.prompts_dir / f"{base_filename}_response.json"
        merged = {
            "choices": {}
        }
        for chunk in chunks:
            chunk: str
            if not chunk.startswith("data: "):
                continue
            chunk = chunk[len("data: "):]
            try:
                chunk = json.loads(chunk)
            except:
                continue
            assert type(chunk) is dict
            if chunk["object"] != "chat.completion.chunk":
                # other types are not implemented and could cause undefined behavior
                return
            for k,v in chunk.items():
                if k != "choices":
                    merged[k] = v
                    continue
                for choice in v:
                    index = choice["index"]
                    if index not in merged["choices"]:
                        merged["choices"][index] = {
                            "role": None,
                            "content": {},
                            "finish_reason": None,
                        }
                    at_index = merged["choices"][index]
                    if choice.get("finish_reason", None):
                        at_index["finish_reason"] = choice["finish_reason"]
                    if choice.get("logprobs", None):
                        if "logprobs" not in at_index:
                            at_index["logprobs"] = []
                        at_index["logprobs"].append(choice["logprobs"])
                    if "delta" not in choice:
                        merged["choices"][index] = at_index
                        continue
                    delta = choice["delta"]
                    if delta.get("role", None):
                        at_index["role"] = delta["role"]
                    if "reasoning" in delta:
                        if "reasoning" not in at_index["content"]:
                            at_index["content"]["reasoning"] = ""
                        at_index["content"]["reasoning"] += delta["reasoning"]
                    if "content" in delta:
                        if "content" not in at_index["content"]:
                            at_index["content"]["content"] = ""
                        at_index["content"]["content"] += delta["content"]
                    if "tool_calls" in delta:
                        if "tool_calls" not in at_index:
                            at_index["tool_calls"] = {}
                        for tool_call in delta["tool_calls"]:
                            index = tool_call["index"]
                            if index not in at_index["tool_calls"]:
                                at_index["tool_calls"][index] = {"function": {"name": "", "arguments": ""}}
                            if tool_call["type"] != "function":
                                at_index["tool_calls"][index] = "unsupported"
                                merged["choices"][index] = at_index
                                continue
                            if "id" in tool_call:
                                at_index["tool_calls"][index]["id"] = tool_call["id"]
                            if "function" in tool_call:
                                for k,v in tool_call["function"].items():
                                    at_index["tool_calls"][index]["function"][k] += v

                    merged["choices"][index] = at_index
        with open(response_filename, "w") as f:
            json.dump(merged, f, indent=2)


    def _save_prompt_to_file(self, body: dict) -> None:
        """Save a prompt to markdown and raw JSON files."""
        self.prompts_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.fromisoformat(body["timestamp"])
        base_filename = timestamp.strftime(f"%Y-%m-%d_%H-%M-%S_{body['provider']}")

        # Save markdown file (human-readable)
        md_filepath = self.prompts_dir / f"{base_filename}.md"
        lines = [
            f"# Prompt - {timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Provider:** {body['provider'].capitalize()}",
            f"**Model:** {body['model']}",
            f"**Tokens:** {body['tokens']:,}",
            "",
            "## Messages",
        ]

        for msg in body.get("messages", []):
            role = msg.get("role", "unknown").capitalize()
            content = msg.get("content", "")
            lines.append(f"### {role}")
            lines.append(content)
            lines.append("")

        md_filepath.write_text("\n".join(lines))

        # Save raw JSON file (original request body)
        raw_body = body.get("raw_body")
        if raw_body is not None:
            json_filepath = self.prompts_dir / f"{base_filename}.json"
            json_filepath.write_text(json.dumps(raw_body, indent=2))