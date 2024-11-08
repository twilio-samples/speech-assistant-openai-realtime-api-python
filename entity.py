from pydantic import BaseModel
from typing import Optional


class Call(BaseModel):
    phone: str
    intent_prompt: str

class Message(BaseModel):
    sender: str
    content: str

class Session(BaseModel):
    intent_prompt: str
    transcript: Optional[list[Message]] = None
