# This is an MCP server for the execution agent.
# It is responsible for handling situations based on the presented frame and context.
# It can perform actions such as notifying home residents, saving uncertain frames for future training of the CV model, etc...

# What this server CANNOT DO:
# 1. CURRENTLY, it cannot perform any actions that require physical interaction with the environment (e.g., turning on lights, opening doors, etc.).
# 2. It cannot make decisions that require human judgment or ethical considerations (e.g., deciding whether to call emergency services).
# 3. It cannot access or manipulate personal data without explicit consent from the user.

import asyncio
import json
import os
from dataclasses import dataclass

from courier import Courier
from mcp.server import MCPServer
from ollama import chat


@dataclass
class User:
    id: str
    name: str
    email: str
    phone: str

AGENT_NAME = "Execution Agent"

"""
COURIER SETUP SECTION
"""
client = Courier(os.getenv("COURIER_API_KEY"))

#setup users

with open("agent_hub/profiles/profiles.json", "r", encoding='utf-8') as f:
    data = json.load(f)

users: list[User] = [User(**user) for user in data["users"]]

for user in users:
    client.profiles.create(
        id=user.id,
        profile={"email": user.email, "name": user.name, "phone_number": user.phone}
    )

    
"""
MCP SECTION
"""

mcp = MCPServer(
    name=AGENT_NAME,
    description="This is an MCP server for the execution agent. It is responsible for handling situations based on the presented frame and context.",
    version="1.0.0",
    author="BBtornado"
    )

async def notify_user(user: User, message: str):
    """Send a notification to the user via email."""
    try: 
        response = await client.send.message(
            message={
                "to": {"type": "email", "email": user.email},
                "content": {"title": f"Notification from {AGENT_NAME}", "body": message},
            }
        )

        print(f"Notification sent to {user.name} ({user.email}): {response.request_id}")
    except Exception as e:
        print(f"Failed to send notification to {user.name} ({user.email}): {e}")


@mcp.tool()
async def notify_user_action(user_id: str, message: str):
    """Notify a specific user via email.
    
    Args:
        user_id (str): The ID of the user to notify.
        message (str): The message to send to the user.
    """
    user = next((user for user in users if user.id == user_id), None)
    if user:
        await notify_user(user, message)
    else:
        print(f"User with ID {user_id} not found.")

@mcp.tool()
async def notify_home_residents(message: str):
    """Notify all home residents via email.
    
    Args:
        message (str): The message to send to all home residents."""
    for user in users:
        await notify_user(user, message)

async def main():
    """Main function to run the MCP server."""
    # TODO: RUN OLLAMA AGENT WITH THE MCP TEST SERVER

    message = [
        {
            'role': 'user', 
            'content': {
                "image_id": "123456",
                "pre_proccessing_captions": "",
                "people": "",
                "objects": "",
                "post_proccessing_captions": "",
                "urgency": "",
                "frame_description": "",
                "errors": ""
            }
        }
    ],

    response = chat(
        model=os.getenv("EXECUTION_MODEL"),
        messages=message,
                        )

if __name__ == "__main__":
    asyncio.run(main())