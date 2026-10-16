"""
Execution agent for the home security pipeline.

NO separate captioning agent. This agent IS the vision model: it receives
the raw JPEG frames of a short flagged clip directly (base64-encoded,
already sampled dense-around-trigger upstream — see TODO.md §3), plus
whatever YOLO already detected in that clip as text context, and reasons
over the actual pixels to both score urgency and decide whether to call
notify_user. There is no intermediate text-captioning stage — that
architecture was considered and deliberately dropped in favor of this one,
specifically to avoid losing visual detail through a lossy caption
bottleneck.

The model bound here MUST be a vision-capable Ollama model (e.g. a
qwen3-vl tag). A text-only model will not accept the image content blocks
this module builds.

Current design is SINGLE-SHOT: the model gets one turn, any tool calls it
returns are executed, and the function returns. The model does NOT see
tool results and cannot retry or route around a failed tool call within
this function. If you want "the model figures out another way to solve
the problem" (as described in AGENTS.md's Error Handling section), that
requires a real multi-turn loop feeding tool results back in — not yet
implemented. AGENTS.md has been updated to reflect single-shot behavior;
revisit both together if you build the loop.

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
from agent_hub_types import User 

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
            # Courier's documented signature takes the user id as the first
            # positional arg, not as `id=`. Verify against your installed
            # trycourier version if this errors.
            client.profiles.create(
                user.id,
                profile={"email": user.email, "name": user.name, "phone_number": user.phone},
            )
        except Exception:
            # A bad profile shouldn't take down startup for everyone else.
            log.exception("Failed to sync Courier profile for user_id=%s", user.id)


# ---------------------------------------------------------------------------
# Notification cooldown — prevents the same incident from spamming residents
# if multiple frames trigger the agent in a short window. In-memory only;
# if you run more than one process, move this to Redis or a shared table.
#
# IMPORTANT: keyed on (user_id, camera_id) — NOT on the message text. The
# model writes fresh wording every call, so hashing the message would
# almost never match between calls about the same ongoing incident and
# the cooldown would silently fail to do anything. If you need
# incident-level (not just camera-level) cooldown granularity, thread an
# explicit incident/clip id through instead of relying on message text.
# ---------------------------------------------------------------------------

_last_notified: dict[str, float] = {}


def _cooldown_key(user_id: str, camera_id: str) -> str:
    return f"{user_id}:{camera_id}"


def _in_cooldown(key: str) -> bool:
    last = _last_notified.get(key)
    return last is not None and (time.time() - last) < NOTIFY_COOLDOWN_SECONDS


def _mark_notified(key: str) -> None:
    _last_notified[key] = time.time()


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

def build_notify_tool(client: Courier, users: list[User], camera_id: str):
    """Builds the notify_user tool with the user_id constrained to the
    actual known users, so the model cannot hallucinate an ID.

    camera_id is closed over so the cooldown key can be keyed correctly
    (see note above) without asking the model to supply it."""

    if not users:
        raise ValueError("No users loaded — cannot build a notify tool with zero valid targets.")

    UserId = Enum("UserId", {u.id: u.id for u in users})
    users_by_id = {u.id: u for u in users}

    class NotifyUserArgs(BaseModel):
        user_id: str = Field(description="ID of the resident to notify. Must be a known user.")
        message: str = Field(description="Notification body to send.")
        urgency: int = Field(
            ge=1, le=9,
            description="Your own 1-9 urgency score for this event, per the rubric in AGENTS.md. "
                         "Logged for audit purposes — not just used to decide whether to call this tool.",
        )

    @tool("notify_user", args_schema=NotifyUserArgs)
    def notify_user(user_id: str, message: str, urgency: int) -> str:
        """Notify a specific home resident by email. Use this when the
        situation concerns one identifiable person or pet's owner."""
        user = users_by_id[user_id.value]
        log.info("Urgency score for camera %s: %d", camera_id, urgency)
        key = _cooldown_key(user.id, camera_id)
        if _in_cooldown(key):
            log.info("Skipping notify for %s — camera %s already notified within cooldown window.",
                      user.name, camera_id)
            return f"Skipped: {user.name} was already notified about camera {camera_id} recently."

        try:
            response = client.send.message(
                message={
                    "to": {"email": user.email},
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


def build_clip_message(
    frames_b64: list[str],
    camera_id: str,
    timestamp: str,
    yolo_labels: Optional[list[str]] = None,
) -> HumanMessage:
    """Builds the multimodal HumanMessage: image frames + a short text
    header giving the model context it can't get from pixels alone
    (which camera, when, and what YOLO already flagged as present).

    yolo_labels is optional context, not a substitute for the model's own
    judgment — YOLO tells you an object/person is present, it doesn't
    tell you whether the situation is actually concerning."""
    if not frames_b64:
        raise ValueError("No frames provided — cannot build a clip message with zero images.")

    header_lines = [f"Camera: {camera_id}", f"Time: {timestamp}"]
    if yolo_labels:
        header_lines.append(f"CV pre-detection flagged: {', '.join(yolo_labels)}")
    header_lines.append(
        "The following frames are sampled from a short clip around the trigger event. "
        "Assess urgency and decide whether to notify, per your instructions."
    )

    content_blocks = [{"type": "text", "text": "\n".join(header_lines)}]
    content_blocks.extend(
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{f}"}}
        for f in frames_b64
    )
    return HumanMessage(content=content_blocks)


def run_execution_agent(
    frames_b64: list[str],
    camera_id: str,
    timestamp: str,
    client: Courier,
    users: list[User],
    yolo_labels: Optional[list[str]] = None,
    model_name: Optional[str] = None,
) -> list[str]:
    """Runs the execution agent for one flagged clip. Returns a list of
    human-readable result strings — one per tool call made, or an empty
    list if the model decided no notification was warranted. A caller
    (e.g. a LangGraph node, or a FastAPI worker per TODO.md §5) uses this
    return value to update shared state.

    Single-shot: the model does not see tool execution results within this
    call. See module docstring. model_name must be a vision-capable Ollama
    tag (e.g. qwen3-vl:8b-thinking) — this is not a text-only call."""
    model_name = model_name or os.getenv("EXECUTION_MODEL")
    if not model_name:
        raise RuntimeError("EXECUTION_MODEL env var is not set.")

    notify_tool = build_notify_tool(client, users, camera_id)
    llm = ChatOllama(model=model_name, base_url=os.getenv("EXECUTION_MODEL_HOST")).bind_tools([notify_tool])

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        build_clip_message(frames_b64, camera_id, timestamp, yolo_labels),
    ]

    ai_msg = llm.invoke(messages)

    if not ai_msg.tool_calls:
        # Could mean "model correctly judged no action needed" OR "model
        # failed to produce a valid tool call." These are not the same
        # thing for a security system — log the raw content so you can
        # tell the difference, and consider a fallback notification path
        # if this happens on frames YOLO flagged as high-confidence.
        log.info("No tool calls returned for camera %s. Raw content: %r", camera_id, ai_msg.content)
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
    client = Courier(api_key=os.getenv("COURIER_API_KEY"))
    sync_courier_profiles(client, users)

    # TODO: replace with the real frames coming from the Pi (see TODO.md §3/§4
    # for trigger-centered sampling). frames_b64 is a list of base64-encoded
    # JPEG strings, already sampled — this function does no sampling itself.
    example_frames_b64: list[str] = []
    run_execution_agent(
        frames_b64=example_frames_b64,
        camera_id="front_door",
        timestamp="2026-09-21T14:32:00",
        client=client,
        users=users,
        yolo_labels=["person"],
    )


if __name__ == "__main__":
    main()