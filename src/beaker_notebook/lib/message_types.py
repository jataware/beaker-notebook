from typing import Any, Optional, Literal, TypeVar, TypeAlias, Generic
from pydantic import BaseModel, Field, ConfigDict

Channel: TypeAlias = Literal['shell', 'control', 'iopub', 'stdin']

MessageType = TypeVar("MessageType", bound=str)
ContentType = TypeVar("ContentType", bound=BaseModel)

class Header(BaseModel, Generic[MessageType]):
    date: str
    msg_id: str
    msg_type: MessageType
    session: str
    username: str
    subshell_id: Optional[str]
    version: str


class Message(BaseModel, Generic[MessageType, ContentType]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    buffers: Optional[bytearray]
    channel: Channel
    content: ContentType
    header: Header[MessageType]
    metadata: dict[str, Any]
    parent_header: Optional[Header]


class BaseResponse(BaseModel):
    pass


class MessageContent(BaseModel):
    model_config = ConfigDict(extra="allow")


# class CodeAnalysisResponse(MessageContent):
