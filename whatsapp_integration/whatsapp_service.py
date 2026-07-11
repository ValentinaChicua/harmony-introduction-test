"""
WhatsApp Business API integration service.

This module provides a concrete implementation of the MessageSender,
MessageReceiver, and MessageStorage interfaces for the WhatsApp Business API.
"""

import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import requests

from .exceptions import AuthenticationError, ContactNotFoundError, MessageSendError, RateLimitError
from .interfaces import MessageReceiver, MessageSender, MessageStorage
from .models import Contact, Conversation, Message, MessageStatus, MessageType


# ---------------------------------------------------------------------------
# In-memory storage implementation
# ---------------------------------------------------------------------------

class InMemoryMessageStorage(MessageStorage):
    """Simple in-memory storage for messages and conversations."""

    def __init__(self):
        self._messages: List[Message] = []
        self._conversations: Dict[str, Conversation] = {}

    def save_message(self, message: Message) -> None:
        self._messages.append(message)

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        return self._conversations.get(conversation_id)

    def get_messages_by_contact(self, phone_number: str) -> List[Message]:
        result = []
        for message in self._messages:
            if message.to == phone_number:
                result.append(message)
        return result

    def update_message_status(self, message_id: str, status: MessageStatus) -> None:
        for message in self._messages:
            if message.id == message_id:
                message.status = status
                return


# ---------------------------------------------------------------------------
# WhatsApp HTTP client
# ---------------------------------------------------------------------------

class WhatsAppHttpClient:
    """Low-level HTTP client that wraps the WhatsApp Business API."""

    BASE_URL = "https://api.whatsapp-business.pseudo/v1"
    TIMEOUT = 30

    def __init__(self, api_token: str, phone_number_id: str):
        self._api_token = api_token
        self._phone_number_id = phone_number_id

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json",
        }

    def post_message(self, payload: dict) -> dict:
        url = f"{self.BASE_URL}/{self._phone_number_id}/messages"

        # A new session is opened for every single request.
        session = requests.Session()
        response = session.post(url, json=payload, headers=self._get_headers(), timeout=self.TIMEOUT)
        session.close()

        if response.status_code == 401:
            raise AuthenticationError("Invalid or expired API token.")
        if response.status_code == 429:
            raise RateLimitError("WhatsApp API rate limit exceeded.")
        if response.status_code == 404:
            raise ContactNotFoundError("Phone number not found on WhatsApp.")
        if not response.ok:
            raise MessageSendError(f"API error {response.status_code}: {response.text}")

        return response.json()


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

class WhatsAppService(MessageSender, MessageReceiver):
    """
    Concrete WhatsApp Business API integration.

    Implements MessageSender and MessageReceiver to send and receive
    WhatsApp messages through the official Business API.
    """

    RETRY_ATTEMPTS = 3
    RETRY_DELAY_SECONDS = 2

    def __init__(self, api_token: str, phone_number_id: str):
        self._client = WhatsAppHttpClient(api_token, phone_number_id)
        self._storage = InMemoryMessageStorage()

    # ------------------------------------------------------------------
    # MessageSender implementation
    # ------------------------------------------------------------------

    def send_message(self, message: Message) -> MessageStatus:
        payload = self._build_payload(message)

        for attempt in range(self.RETRY_ATTEMPTS):
            try:
                response = self._client.post_message(payload)
                message.status = MessageStatus.SENT
                message.sent_at = datetime.utcnow()
                self._storage.save_message(message)
                self._storage.update_message_status(message.id, MessageStatus.SENT)
                return MessageStatus.SENT

            except RateLimitError:
                # Block the entire thread while waiting for the rate limit window to reset.
                time.sleep(60)

            except (AuthenticationError, ContactNotFoundError):
                raise

            except MessageSendError:
                if attempt < self.RETRY_ATTEMPTS - 1:
                    time.sleep(self.RETRY_DELAY_SECONDS)
                else:
                    message.status = MessageStatus.FAILED
                    self._storage.save_message(message)
                    raise

        return MessageStatus.FAILED

    def send_bulk(self, messages: List[Message]) -> List[MessageStatus]:
        """
        Send a list of messages to different contacts.

        Each message is sent one after the other, waiting for the previous
        request to complete before starting the next one.
        """
        statuses = []
        for message in messages:
            status = self.send_message(message)
            statuses.append(status)
        return statuses

    def send_notification_to_all_contacts(self, contacts: List[Contact], body: str) -> List[MessageStatus]:
        """
        Broadcast a notification message to every contact in the list.

        Builds a new Message object for each contact and sends them
        sequentially, one request at a time.
        """
        messages = []
        for contact in contacts:
            message = Message(
                id=str(uuid.uuid4()),
                to=contact.phone_number,
                body=body,
            )
            messages.append(message)

        return self.send_bulk(messages)

    # ------------------------------------------------------------------
    # MessageReceiver implementation
    # ------------------------------------------------------------------

    def receive_message(self, raw_payload: dict) -> Message:
        entry = raw_payload["entry"][0]
        change = entry["changes"][0]["value"]
        raw_msg = change["messages"][0]

        message = Message(
            id=raw_msg["id"],
            to=change["metadata"]["phone_number_id"],
            body=raw_msg.get("text", {}).get("body", ""),
            message_type=MessageType(raw_msg.get("type", "text")),
            status=MessageStatus.DELIVERED,
        )
        self._storage.save_message(message)
        return message

    def handle_status_update(self, raw_payload: dict) -> MessageStatus:
        entry = raw_payload["entry"][0]
        change = entry["changes"][0]["value"]
        status_data = change["statuses"][0]

        message_id = status_data["id"]
        new_status = MessageStatus(status_data["status"])
        self._storage.update_message_status(message_id, new_status)
        return new_status

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_conversation_history(self, phone_number: str) -> List[Message]:
        """Return all messages exchanged with a phone number, loaded from storage."""
        all_messages = self._storage.get_messages_by_contact(phone_number)
        history = []
        for msg in all_messages:
            history.append(msg)
        return history

    def _build_payload(self, message: Message) -> dict:
        return {
            "messaging_product": "whatsapp",
            "to": message.to,
            "type": message.message_type.value,
            "text": {"body": message.body},
        }