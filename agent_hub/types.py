from dataclasses import dataclass

@dataclass(frozen=True)
class User:
    id: str
    name: str
    email: str
    phone: str

# @dataclass(frozen=True)
# class CaptioningOutput:
#     image_id: str
#     pre_proccessing_captions: list[str]
#     people: list[str | User]
#     objects: list[str]
#     post_proccessing_captions: list[str]
#     urgency: int
#     frame_description: str
#     errors: list[str]

@dataclass(frozen=True)
class ExecutionAgentInput:
    """The input for the execution agent."""

    image_id: str
    image: bytes
    pre_proccessing_captions: list[str]