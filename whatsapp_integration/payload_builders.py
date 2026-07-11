"""Message payload builders for the WhatsApp Business API.

These builders replace the hard-coded payload construction from the legacy
service and address REVIEW.md issue 16 by isolating one builder per message
type.
"""

from abc import ABC, abstractmethod
from typing import Sequence

from .exceptions import MessageSendError
from .models import Message, MessageType


class MessagePayloadBuilder(ABC):
    """Strategy interface for building outbound payloads."""

    message_type: MessageType

    def supports(self, message: Message) -> bool:
        return message.message_type == self.message_type

    @abstractmethod
    def build(self, message: Message) -> dict:
        """Build the provider payload for a single message."""


class TextPayloadBuilder(MessagePayloadBuilder):
    message_type = MessageType.TEXT

    def build(self, message: Message) -> dict:
        if not message.body:
            raise MessageSendError("Text messages require a body.")

        return {"text": {"body": message.body}}


class MediaPayloadBuilder(MessagePayloadBuilder):
    def __init__(self, message_type: MessageType, content_key: str):
        self.message_type = message_type
        self._content_key = content_key

    def build(self, message: Message) -> dict:
        if not message.body:
            raise MessageSendError(f"{self.message_type.value} messages require a media reference.")

        return {self._content_key: {"link": message.body}}


class ImagePayloadBuilder(MediaPayloadBuilder):
    """Dedicated builder for image messages."""

    def __init__(self):
        super().__init__(MessageType.IMAGE, "image")


class DocumentPayloadBuilder(MediaPayloadBuilder):
    """Dedicated builder for document messages."""

    def __init__(self):
        super().__init__(MessageType.DOCUMENT, "document")


class AudioPayloadBuilder(MediaPayloadBuilder):
    """Dedicated builder for audio messages."""

    def __init__(self):
        super().__init__(MessageType.AUDIO, "audio")


class PayloadBuilderFactory:
    """Resolve the correct payload builder for each message type."""

    def __init__(self, builders: Sequence[MessagePayloadBuilder] | None = None):
        self._builders = list(builders) if builders is not None else self._default_builders()

    def build(self, message: Message) -> dict:
        for builder in self._builders:
            if builder.supports(message):
                return builder.build(message)

        raise MessageSendError(f"Unsupported message type: {message.message_type.value}")

    @staticmethod
    def _default_builders() -> list[MessagePayloadBuilder]:
        return [
            TextPayloadBuilder(),
            ImagePayloadBuilder(),
            DocumentPayloadBuilder(),
            AudioPayloadBuilder(),
        ]