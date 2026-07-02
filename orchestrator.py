"""
Claude-as-brain / Gemini-as-hands orchestrator.

Claude (claude-opus-4-8) plans, delegates coding tasks to Gemini via the
`write_code` tool, reviews the result, and retries with a corrected spec
if needed. Gemini never talks to the user directly -- Claude is the only
voice back to the caller.
"""

import json
import logging
import os
import sys
from dataclasses import dataclass, field

import anthropic
from google import genai

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CLAUDE_MODEL = "claude-opus-4-8"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")  # confirm against Google docs
MAX_GEMINI_CALLS_PER_RUN = int(os.environ.get("MAX_GEMINI_CALLS", "6"))
MAX_TURNS = int(os.environ.get("MAX_TURNS", "20"))

LOG_PATH = os.environ.get("ORCHESTRATOR_LOG", "orchestrator.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("orchestrator")

SYSTEM_PROMPT = """You are a senior engineering lead directing a junior code-generation \
model (accessed via the `write_code` tool). You do NOT write code yourself.

Workflow:
1. Understand the user's requirement fully before delegating anything.
2. Break the work into one or more precise, self-contained specs. Each spec \
must include: target language, exact function/class signatures, inputs/outputs, \
edge cases, and (when useful) an example.
3. Call `write_code` with the spec. You will get back raw generated code.
4. Review the code yourself: does it match the spec, is it correct, does it \
handle edge cases, is it free of obvious bugs?
5. If it's wrong, incomplete, or below standard, call `write_code` again with a \
corrected, more specific spec explaining what was wrong. Do not just repeat the \
same spec.
6. Once you are satisfied, present the final code to the user along with a \
short explanation of what it does and any caveats. Do not show intermediate \
failed attempts unless the user asks.

Be economical with `write_code` calls -- you have a limited budget per task. \
If you're on your last attempt and the code is still imperfect, present the \
best version you have and clearly say what's still wrong.
"""

WRITE_CODE_TOOL = {
    "name": "write_code",
    "description": (
        "Delegate an implementation task to the code-generation model. "
        "Provide a complete, unambiguous spec: language, exact signatures, "
        "constraints, edge cases, and an example if helpful. Returns the "
        "raw generated code as text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "spec": {
                "type": "string",
                "description": "Complete, self-contained specification of the code to write.",
            }
        },
        "required": ["spec"],
    },
}


# ---------------------------------------------------------------------------
# Gemini call
# ---------------------------------------------------------------------------

@dataclass
class GeminiCaller:
    client: genai.Client
    model: str
    call_count: int = 0
    max_calls: int = MAX_GEMINI_CALLS_PER_RUN

    def call(self, spec: str) -> str:
        if self.call_count >= self.max_calls:
            msg = (
                f"[write_code unavailable: budget exhausted "
                f"({self.max_calls} calls used). Stop delegating and report "
                f"the best result you have to the user.]"
            )
            log.warning("Gemini call budget exhausted (%d/%d)", self.call_count, self.max_calls)
            return msg

        self.call_count += 1
        log.info("Gemini call #%d -- spec (%d chars):\n%s", self.call_count, len(spec), spec)

        response = self.client.models.generate_content(
            model=self.model,
            contents=spec,
        )
        text = response.text or ""
        log.info("Gemini call #%d -- result (%d chars)", self.call_count, len(text))
        return text


# ---------------------------------------------------------------------------
# Claude orchestration loop
# ---------------------------------------------------------------------------

@dataclass
class OrchestratorResult:
    final_text: str
    turns_used: int
    gemini_calls_used: int
    messages: list = field(default_factory=list)


def run(task: str) -> OrchestratorResult:
    claude = anthropic.Anthropic()
    gemini_client = genai.Client()
    gemini = GeminiCaller(client=gemini_client, model=GEMINI_MODEL)

    messages = [{"role": "user", "content": task}]
    log.info("Task: %s", task)

    for turn in range(1, MAX_TURNS + 1):
        response = claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            tools=[WRITE_CODE_TOOL],
            messages=messages,
        )

        log.info("Claude turn %d -- stop_reason=%s", turn, response.stop_reason)

        if response.stop_reason == "refusal":
            log.error("Claude refused the request.")
            return OrchestratorResult(
                final_text="[Claude declined this request.]",
                turns_used=turn,
                gemini_calls_used=gemini.call_count,
                messages=messages,
            )

        if response.stop_reason == "end_turn":
            final_text = next(
                (b.text for b in response.content if b.type == "text"), ""
            )
            messages.append({"role": "assistant", "content": response.content})
            return OrchestratorResult(
                final_text=final_text,
                turns_used=turn,
                gemini_calls_used=gemini.call_count,
                messages=messages,
            )

        # stop_reason == "tool_use" (or similar): execute tool calls
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "write_code":
                spec = block.input.get("spec", "")
                try:
                    code = gemini.call(spec)
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": code}
                    )
                except Exception as exc:  # network/API errors from Gemini
                    log.exception("Gemini call failed")
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Error calling Gemini: {exc}",
                            "is_error": True,
                        }
                    )
            else:
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Unknown tool: {block.name}",
                        "is_error": True,
                    }
                )

        messages.append({"role": "user", "content": tool_results})

    log.warning("Hit MAX_TURNS (%d) without a final answer.", MAX_TURNS)
    return OrchestratorResult(
        final_text="[Reached max turns without a final answer.]",
        turns_used=MAX_TURNS,
        gemini_calls_used=gemini.call_count,
        messages=messages,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        task = input("Describe the coding task: ").strip()

    if not task:
        print("No task provided.")
        sys.exit(1)

    result = run(task)

    print("\n" + "=" * 60)
    print("FINAL RESULT")
    print("=" * 60)
    print(result.final_text)
    print("=" * 60)
    print(f"(turns used: {result.turns_used}, gemini calls used: {result.gemini_calls_used})")
    print(f"(full log: {LOG_PATH})")


if __name__ == "__main__":
    main()
