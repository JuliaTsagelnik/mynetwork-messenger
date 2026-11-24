from typing import List
from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    role: str = "user"


class MessageCreate(BaseModel):
    sender: str
    receiver: str
    text: str


class GroupCreate(BaseModel):
    name: str
    creator: str
    members: List[str]


class GroupMessageCreate(BaseModel):
    sender: str
    text: str