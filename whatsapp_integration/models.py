from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class MessageStatus(Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class MessageType(Enum):
    TEXT = "text"
    IMAGE = "image"
    DOCUMENT = "document"
    AUDIO = "audio"


@dataclass
class Contact:
    phone_number: str
    name: str
    is_active: bool = True


@dataclass
class Message:
    id: str
    to: str
    body: str
    message_type: MessageType = MessageType.TEXT
    status: MessageStatus = MessageStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sent_at: Optional[datetime] = None
    error: Optional[str] = None
    remote_message_id: Optional[str] = None
    operation_id: Optional[str] = None


@dataclass
class Conversation:
    id: str
    contact: Contact
    messages: list = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: Optional[datetime] = None
