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

import json
import logging
import os
import time
from enum import Enum
from pathlib import Path
from typing import Optional

from courier import Courier
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field
from types import User

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("execution_agent")

AGENT_NAME = "Execution Agent"
PROFILES_PATH = Path("agent_hub/profiles/profiles.json")
NOTIFY_COOLDOWN_SECONDS = int(os.getenv("NOTIFY_COOLDOWN_SECONDS", "300"))





def load_users(path: Path = PROFILES_PATH) -> list[User]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [User(**u) for u in data["users"]]


def sync_courier_profiles(client: Courier, users: list[User]) -> None:
    """Push local profiles into Courier. Call explicitly, not at import time,
    so importing this module never has side effects or network calls."""
    for user in users:
        try:
            client.profiles.create(
                id=user.id,
                profile={"email": user.email, "name": user.name, "phone_number": user.phone},
            )
        except Exception:
            # A bad profile shouldn't take down startup for everyone else.
            log.exception("Failed to sync Courier profile for user_id=%s", user.id)


# ---------------------------------------------------------------------------
# Notification cooldown — prevents the same incident from spamming residents
# if multiple frames trigger the agent in a short window. In-memory only;
# if you run more than one process, move this to Redis or a shared table.
# ---------------------------------------------------------------------------

_last_notified: dict[str, float] = {}


def _cooldown_key(user_id: str, message: str) -> str:
    return f"{user_id}:{hash(message)}"


def _in_cooldown(key: str) -> bool:
    last = _last_notified.get(key)
    return last is not None and (time.time() - last) < NOTIFY_COOLDOWN_SECONDS


def _mark_notified(key: str) -> None:
    _last_notified[key] = time.time()


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

def build_notify_tool(client: Courier, users: list[User]):
    """Builds the notify_user tool with the user_id constrained to the
    actual known users, so the model cannot hallucinate an ID."""

    if not users:
        raise ValueError("No users loaded — cannot build a notify tool with zero valid targets.")

    UserId = Enum("UserId", {u.id: u.id for u in users})
    users_by_id = {u.id: u for u in users}

    class NotifyUserArgs(BaseModel):
        user_id: User.UserId = Field(description="ID of the resident to notify. Must be a known user.")
        message: str = Field(description="Notification body to send.")

    @tool("notify_user", args_schema=NotifyUserArgs)
    def notify_user(user_id: User.UserId, message: str) -> str:
        """Notify a specific home resident by email. Use this when the
        situation concerns one identifiable person or pet's owner."""
        user = users_by_id[user_id.value]
        key = _cooldown_key(user.id, message)
        if _in_cooldown(key):
            log.info("Skipping notify for %s — same message sent within cooldown window.", user.name)
            return f"Skipped: {user.name} was already notified with a similar message recently."

        try:
            response = client.send.message(
                message={
                    "to": {"type": "email", "email": user.email},
                    "content": {"title": f"Notification from {AGENT_NAME}", "body": message},
                }
            )
            _mark_notified(key)
            log.info("Notified %s (%s): request_id=%s", user.name, user.email, response.request_id)
            return f"Notified {user.name}."
        except Exception:
            # Never fail silently — this is a security notification pipeline.
            log.exception("Failed to notify %s (%s)", user.name, user.email)
            return f"Failed to notify {user.name}. See logs — this needs attention."

    return notify_user


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

with open(Path(__file__).parent / "AGENTS.md", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()


def format_frame_context(frame: dict) -> str:
    """Turn the frame context dict into a plain-text prompt the model can read."""
    lines = [f"{k}: {v}" for k, v in frame.items() if v]
    return "Flagged frame context:\n" + "\n".join(lines) if lines else "Flagged frame context: (empty)"


def run_execution_agent(
    frame: dict, client: Courier, users: list[User], model_name: Optional[str] = None
) -> list[str]:
    """Runs the execution agent for one flagged frame. Returns a list of
    human-readable result strings — one per tool call made, or an empty
    list if the model decided no notification was warranted. A caller
    (e.g. a LangGraph node) uses this return value to update shared state."""
    model_name = model_name or os.getenv("EXECUTION_MODEL")
    if not model_name:
        raise RuntimeError("EXECUTION_MODEL env var is not set.")

    notify_tool = build_notify_tool(client, users)
    llm = ChatOllama(model=model_name, base_url=os.getenv("EXECUTION_MODEL_HOST")).bind_tools([notify_tool])

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=format_frame_context(frame)),
    ]

    ai_msg = llm.invoke(messages)

    if not ai_msg.tool_calls:
        log.info("Model decided no notification was warranted for this frame.")
        return []

    results: list[str] = []
    for call in ai_msg.tool_calls:
        if call["name"] == "notify_user":
            result = notify_tool.invoke(call["args"])
            log.info("Tool result: %s", result)
            results.append(result)
        else:
            log.warning("Model called unknown tool: %s", call["name"])
            results.append(f"Unknown tool call: {call['name']}")
    return results


def main() -> None:
    users = load_users()
    client = Courier(os.getenv("COURIER_API_KEY"))
    sync_courier_profiles(client, users)

    # TODO: replace with the real frame payload coming from the captioning agent.
    example_frame = {
        "image_id": "123456789",
        "pre_proccessing_captions": "",
        "people": "",
        "objects": "",
        "post_proccessing_captions": "",
        "urgency": "",
        "frame_description": "",
        "errors": ""
    }
    run_execution_agent(example_frame, client, users)


if __name__ == "__main__":
    main()