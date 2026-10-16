"""
Execution agent for the home security pipeline.

Given context about a flagged frame, this agent decides whether to notify
residents and does so via Courier. No MCP involved — the Courier action is
a plain LangChain tool, called directly by the model in this process.

What this agent CANNOT do (kept from the original design intent):
1. Physical actions (lights, doors, locks, etc.) — not implemented.
2. Judgment calls that need a human or legal authority (e.g. calling
   emergency services) — this agent only notifies residents.
3. Access personal data beyond the profiles it's explicitly given.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("caption_agent")

AGENT_NAME = "Caption Agent"


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

with open(Path(__file__).parent / "AGENTS.md", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()



def run_caption_agent(
    frame: Any, model_name: str | None = None
) -> dict[str, str]:
    """Runs the caption agent for one flagged frame. Returns JSON output from the model
    
    """
    model_name = model_name or os.getenv("CAPTION_MODEL")
    if not model_name:
        raise RuntimeError("EXECUTION_MODEL env var is not set.")

    llm = ChatOllama(model=model_name, base_url=os.getenv("CAPTION_MODEL_HOST"))

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content="TODO: GET IMAGE"),
    ]

    ai_msg = llm.invoke(messages)

    return ai_msg


def main() -> None:

    # TODO: replace with the real frame payload.
    example_img = {}
    run_caption_agent(example_img)


if __name__ == "__main__":
    main()