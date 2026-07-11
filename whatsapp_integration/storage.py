"""Thread-safe in-memory storage for WhatsApp messages and conversations.

This replaces the list-based storage from the legacy service and directly
addresses the scalability and consistency problems described in REVIEW.md:
issue 1 (contact lookup), issue 2 (status updates), issue 3 (conversation
management), and issue 18 (multi-thread safety).
"""

from threading import Lock
from typing import Dict, List, Optional

from .interfaces import MessageStorage
from .models import Contact, Conversation, Message, MessageStatus


class InMemoryMessageStorage(MessageStorage):
    """Simple in-memory repository with O(1) message lookup by id."""

    def __init__(self):
        self._lock = Lock()
        self._messages_by_id: Dict[str, Message] = {}
        self._messages_by_remote_id: Dict[str, Message] = {}
        self._message_ids_by_contact: Dict[str, List[str]] = {}
        self._conversations: Dict[str, Conversation] = {}

    def save_message(self, message: Message) -> None:
        with self._lock:
            previous_message = self._messages_by_id.get(message.id)
            self._messages_by_id[message.id] = message

            if previous_message is not None and previous_message.remote_message_id:
                self._messages_by_remote_id.pop(previous_message.remote_message_id, None)

            if message.remote_message_id:
                self._messages_by_remote_id[message.remote_message_id] = message

            contact_message_ids = self._message_ids_by_contact.setdefault(message.to, [])
            if previous_message is None:
                contact_message_ids.append(message.id)

            conversation = self._conversations.get(message.to)
            if conversation is None:
                conversation = Conversation(
                    id=message.to,
                    contact=Contact(phone_number=message.to, name=message.to),
                    messages=[],
                )
                self._conversations[message.to] = conversation

            if previous_message is None:
                conversation.messages.append(message)

            conversation.last_activity = message.sent_at or message.created_at

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        with self._lock:
            return self._conversations.get(conversation_id)

    def get_messages_by_contact(self, phone_number: str) -> List[Message]:
        with self._lock:
            message_ids = list(self._message_ids_by_contact.get(phone_number, []))
            return [self._messages_by_id[message_id] for message_id in message_ids if message_id in self._messages_by_id]

    def update_message_status(self, message_id: str, status: MessageStatus) -> None:
        with self._lock:
            message = self._messages_by_id.get(message_id) or self._messages_by_remote_id.get(message_id)
            if message is None:
                return

            message.status = status
            self._messages_by_id[message.id] = message
            if message.remote_message_id:
                self._messages_by_remote_id[message.remote_message_id] = message