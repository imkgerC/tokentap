"""HTTP relay proxy for intercepting LLM API traffic."""

import json
import ssl
from datetime import datetime
from typing import Callable

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
        if body and self.on_request:
            self._process_request(body, path)

        # Forward request to upstream
        headers = dict(request.headers)
        headers.pop("Host", None)
        headers.pop("Content-Length", None)

        ssl_context = ssl.create_default_context()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=request.method,
                    url=upstream_url,
                    headers=headers,
                    data=body,
                    ssl=ssl_context,
                ) as upstream_response:
                    response_body = await upstream_response.read()

                    # Build response headers
                    response_headers = dict(upstream_response.headers)
                    response_headers.pop("Content-Encoding", None)
                    response_headers.pop("Transfer-Encoding", None)
                    response_headers.pop("Content-Length", None)

                    return web.Response(
                        status=upstream_response.status,
                        headers=response_headers,
                        body=response_body,
                    )
        except aiohttp.ClientError as e:
            return web.Response(
                status=502,
                text=f"Upstream error: {e}",
            )

    def _process_request(self, body: bytes, path: str) -> None:
        """Process request body for token counting and logging."""
        try:
            body_dict = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

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
            self.on_request(event)

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
