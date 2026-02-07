
# This is a fork

I adapted tokentap to be able to inspect prompts send to a local model instead of the original frontier model providers.

---

<p align="center">
  <h1 align="center">Tokentap (FORK)</h1>
  <p align="center">
    <strong>Token Tracker for LLM CLI Tools</strong>
  </p>
  <p align="center">
    <a href="#installation">Installation</a> •
    <a href="#quick-start">Quick Start</a> •
    <a href="#features">Features</a> •
    <a href="#commands">Commands</a> •
    <a href="#contributing">Contributing</a>
  </p>
</p>

---

tokentap tracks token usage for LLM CLI tools with a live terminal dashboard. See exactly how many tokens you're using in real-time.

## Why tokentap?

- **Track Token Usage**: See exactly how many tokens each request consumes
- **Monitor Context Windows**: Visual fuel gauge shows cumulative usage against your limit
- **Debug Prompts**: Automatically saves every prompt as markdown and JSON for review
- **Zero Configuration**: No certificates, no setup - just install and go

## Installation

```bash
git clone https://github.com/imkgerC/tokentap.git
cd tokentap
python -m venv venv
source venv/bin/activate
pip install -e .
```

### Requirements

- Python 3.10+

## Quick Start

### Step 1: Start the Dashboard

```bash
tokentap start
```

You'll be prompted to choose where to save captured prompts, then the dashboard appears:

```
┌─────────────────────────────────────────────────────────────┐
│  TOKENTAP - LLM Traffic Inspector                           │
├─────────────────────────────────────────────────────────────┤
│  Context Usage  ████████████░░░░░░░░░░░░░░░░  42%           │
│                 (84,231 / 200,000 tokens)                   │
├─────────────────────────────────────────────────────────────┤
│  Time     Provider    Model                      Tokens     │
│  14:23:01 Anthropic   claude-sonnet-4-20250514   12,847     │
│  14:23:45 Anthropic   claude-sonnet-4-20250514   8,234      │
│  14:24:12 Anthropic   claude-sonnet-4-20250514   15,102     │
├─────────────────────────────────────────────────────────────┤
│  Last Prompt: "Can you help me refactor this function..."   │
└─────────────────────────────────────────────────────────────┘
```

### Step 2: Run Your LLM Tool (with tokentap configured as the llm provider)

That's it! Watch the dashboard update in real-time as you work.

## Features

### Live Terminal Dashboard

Real-time token tracking with color-coded fuel gauge:
- Green: < 50% of limit
- Yellow: 50-80% of limit
- Red: > 80% of limit

### Prompt Archive

Every intercepted request is saved to your chosen directory:
- **Markdown** - Human-readable format with metadata
- **JSON** - Raw API request body for debugging

### Session Summary

When you exit, see your total usage:

```
Session complete. Total: 84,231 tokens across 12 requests.
```

## Commands

| Command | Description |
|---------|-------------|
| `tokentap start` | Start the proxy and dashboard |

### Options

```bash
tokentap start [OPTIONS]

Options:
  -p, --port NUM    Proxy port (default: 8080)
  -l, --limit NUM   Token limit for fuel gauge (default: 200000)
```

```bash
tokentap claude [OPTIONS] [ARGS]...

Options:
  -p, --port NUM    Proxy port (default: 8080)
```

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│  Terminal 1: tokentap start                                     │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  HTTP Proxy (localhost:8080)                                ││
│  │  + Dashboard                                                ││
│  │  + Prompt Archive                                           ││
│  └─────────────────────────────────────────────────────────────┘│
└───────────────────────────────┬─────────────────────────────────┘
                                │ HTTP
                                │
┌───────────────────────────────┴─────────────────────────────────┐
│  Terminal 2: your llm-powered tool                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Set provider url=http://localhost:8080                     ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ HTTPS
                                ▼
                      ┌───────────────────┐
                      │ your llm provider │
                      └───────────────────┘
```


## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

