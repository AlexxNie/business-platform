from pydantic import BaseModel
from datetime import datetime


class ModuleCreate(BaseModel):
    code: str
    name: str
    description: str | None = None
    icon: str | None = None


class ModuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    is_active: bool | None = None


class ModuleResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str | None
    icon: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
