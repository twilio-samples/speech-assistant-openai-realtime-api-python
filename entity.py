from pydantic import BaseModel


class Call(BaseModel):
    phone: str
    intent: str