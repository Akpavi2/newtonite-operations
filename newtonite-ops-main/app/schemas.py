from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

Priority = Literal["Low", "Medium", "High", "Urgent"]
Status = Literal["Open", "In Progress", "Awaiting Approval", "Resolved", "Closed"]
ItemType = Literal["incident", "customer issue", "payment", "compliance", "task"]

class LoginInput(BaseModel):
    email: str
    password: str

class ItemCreate(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=10000)
    item_type: ItemType = "task"
    priority: Priority = "Medium"
    team_id: int
    assignee_id: int | None = None
    due_date: str | None = None

class ItemUpdate(BaseModel):
    version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=3, max_length=180)
    description: str | None = Field(default=None, max_length=10000)
    priority: Priority | None = None
    assignee_id: int | None = None
    due_date: str | None = None

class TransitionInput(BaseModel):
    version: int = Field(ge=1)
    status: Status

class CommentInput(BaseModel):
    body: str = Field(min_length=1, max_length=4000)

class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str
    item_type: str
    priority: str
    status: str
    team_id: int
    assignee_id: int | None
    creator_id: int
    due_date: str | None
    version: int
    created_at: datetime
    updated_at: datetime
