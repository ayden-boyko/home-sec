# This is an MCP server for the execution agent.
# It is responsible for handling situations based on the presented frame and context.
# It can perform actions such as notifying home residents, saving uncertain frames for future training of the CV model, etc...

# What this server CANNOT DO:
# 1. CURRENTLY, it cannot perform any actions that require physical interaction with the environment (e.g., turning on lights, opening doors, etc.).
# 2. It cannot make decisions that require human judgment or ethical considerations (e.g., deciding whether to call emergency services).
# 3. It cannot access or manipulate personal data without explicit consent from the user.

from types import *

from courier import Courier
from mcp.server import MCPServer

client = Courier()

mcp = MCPServer(
    name="Execution Agent",
    description="This is an MCP server for the execution agent. It is responsible for handling situations based on the presented frame and context.",
    version="1.0.0",
    author="BBtornado"
    )


