"""
Orchestrator for the home security agent pipeline.
 
Wires the captioning agent and the execution agent into a single LangGraph
graph. One flagged cli[] goes in, the graph runs each node in order, and
the final state tells you what happened.
 
Run: python orchestrator.py
"""


import logging

from typing import *

from langgraph.types import Send
from types import CaptioningOutput

log = logging.getLogger("orchestrator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


"""
STATES: define the state of the orchestrator and workers, which is persisted to disk and restored on restart.
This is used to avoid re-processing frames on restart, and to keep track of the last frame that was processed by the CV model and passed to the execution agent, as well as the last captioning output that was processed by the execution agent.
"""

class State(TypedDict):
    """The state of the orchestrator, which is persisted to disk and restored on restart."""

    last_clipframe_id: Optional[str] # last frame ID that was processed by the captioning agent and passed to the execution agent. Used to avoid re-processing frames on restart.

    last_captioning_output: Optional[CaptioningOutput] # last captioning output that was processed by the execution agent. Used to avoid re-processing frames on restart.

    last_executed_clip_id: Optional[str] # last frame ID that was processed by the execution agent. Used to avoid re-processing frames on restart.


class WorkerState(TypedDict):
    """The state of a single worker, which is persisted to disk and restored on restart."""

    last_clip_id: Optional[str] # last frame ID that was processed by the worker. Used to avoid re-processing frames on restart.

    last_captioning_output: Optional[CaptioningOutput] # last captioning output that was processed by the worker. Used to avoid re-processing frames on restart.

"""
NODES: define the nodes in the orchestrator graph, which are used to route messages between agents.
"""


def execution_node() -> Send:
    """The execution node:
        1. receives a short video and a captioning output from the CV model
        2. sends notifications to the users
        3. then sends the results back to the orchestrator.
    """
    return Send(
        agent_name="execution_agent",
        message_type="CaptioningOutput",
        message_schema=CaptioningOutput,
    )