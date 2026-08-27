import uuid

from pydantic import BaseModel


class ToolConfirmRequest(BaseModel):
    message_id: uuid.UUID
    approved: bool


class ToolConfirmResponse(BaseModel):
    message_id: uuid.UUID
    tool_name: str
    approved: bool
    result: str
