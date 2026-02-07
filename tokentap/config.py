"""Configuration constants for tokentap."""

from pathlib import Path

# Defaults
DEFAULT_TOKEN_LIMIT = 65536
DEFAULT_PROXY_PORT = 8080
DEFAULT_PROMPTS_DIR = Path("./prompts").resolve()
DEFAULT_UPSTREAM_HOST = "http://127.0.0.1:1234"

# Dashboard settings
PROMPT_PREVIEW_LENGTH = 200
MAX_LOG_ENTRIES = 100
