# Claude-as-brain / Gemini-as-hands orchestrator

Claude (`claude-opus-4-8`) plans and reviews. Gemini writes code. Claude is
the only thing that talks back to you; Gemini is just a tool it calls.

## Setup

```bash
pip install -r requirements.txt

# Claude credentials (one of):
export ANTHROPIC_API_KEY=sk-ant-...
# or: ant auth login

# Gemini credentials:
export GEMINI_API_KEY=...
```

Optional env vars:

- `GEMINI_MODEL` (default `gemini-2.5-pro`) -- confirm the exact model ID
  against Google's current docs; not covered by this setup.
- `MAX_GEMINI_CALLS` (default `6`) -- hard cap on delegated calls per task,
  to bound cost/latency if Claude and Gemini get stuck in a retry loop.
- `MAX_TURNS` (default `20`) -- hard cap on the Claude planning loop.
- `ORCHESTRATOR_LOG` (default `orchestrator.log`) -- where the full
  spec/response trace is written for debugging.

## Run

```bash
python orchestrator.py "Write a Python function that parses a CSV and returns per-column stats"
```

or run with no args and it will prompt you.

## How it works

1. You give Claude a task.
2. Claude breaks it into a precise spec and calls the `write_code` tool.
3. The tool call is intercepted locally and forwarded to Gemini.
4. Gemini's raw output comes back to Claude as a tool result.
5. Claude reviews it. If it's wrong, Claude calls `write_code` again with a
   corrected spec (up to `MAX_GEMINI_CALLS` times).
6. Once satisfied, Claude gives you the final code + explanation.

Every spec sent to Gemini and every response received is written to
`orchestrator.log` so you can see exactly what was delegated and what came
back, even if Claude only shows you the final result.
