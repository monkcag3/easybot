
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import time


@dataclass
class InboundMessage:
    """Message received from a chat peer."""
    session_hash: str # session identifier
    sender_hash: str # sender identifier
    content: str # Message text
    timestamp: datetime = field(default_factory=datetime.now)
    media: list[str] = field(default_factory=list) # Media URLs
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @property
    def session_key(self) -> str:
        return self.session_hash


@dataclass
class OutboundMessage:
    """Message to send to a chat peer."""
    session_hash: str
    content: str
    reply_to: str | None = None
    send_time: int = field(default_factory=lambda: int(time.time()))
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)