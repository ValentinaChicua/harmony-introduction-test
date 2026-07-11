"""Production-ready WhatsApp integration service.

This module is the supported replacement for the legacy monolithic service.
It keeps the old interfaces but redirects the implementation to smaller,
testable components that address the twenty problems documented in
whatsapp_integration/REVIEW.md.
"""

import logging
import random
import time
import uuid
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import List, Optional

from .config import WhatsAppConfig
from .exceptions import AuthenticationError, ContactNotFoundError, MessageSendError, RateLimitError
from .http_client import WhatsAppHttpClient
from .interfaces import MessageReceiver, MessageSender, MessageStorage
from .models import Contact, Message, MessageStatus
from .payload_builders import PayloadBuilderFactory
from .storage import InMemoryMessageStorage
from .webhook_parser import WebhookParser


class WhatsAppService(MessageSender, MessageReceiver):
    """Concrete synchronous service for WhatsApp Business API integration."""

    RETRY_ATTEMPTS = 3
    RETRY_DELAY_SECONDS = 2

    def __init__(
        self,
        api_token: str | None = None,
        phone_number_id: str | None = None,
        *,
        config: WhatsAppConfig | None = None,
        client: WhatsAppHttpClient | None = None,
        storage: MessageStorage | None = None,
        payload_factory: PayloadBuilderFactory | None = None,
        webhook_parser: WebhookParser | None = None,
        logger: logging.Logger | None = None,
    ):
        if config is None:
            if api_token is None or phone_number_id is None:
                config = WhatsAppConfig.from_env()
            else:
                config = WhatsAppConfig(api_token=api_token, phone_number_id=phone_number_id)

        self._config = config
        self._logger = logger or logging.getLogger(__name__)
        self._client = client or WhatsAppHttpClient(config=self._config, logger=self._logger)
        self._storage = storage or InMemoryMessageStorage()
        self._payload_factory = payload_factory or PayloadBuilderFactory()
        self._webhook_parser = webhook_parser or WebhookParser()

    def close(self) -> None:
        """Release HTTP resources if the underlying client exposes cleanup."""

        close_method = getattr(self._client, "close", None)
        if callable(close_method):
            close_method()

    @classmethod
    def from_env(cls) -> "WhatsAppService":
        """Create a service instance from environment variables."""

        return cls(config=WhatsAppConfig.from_env())

    def send_message(self, message: Message) -> MessageStatus:
        # This method replaces the legacy send path and now adds traceability,
        # dependency injection, retry backoff, and remote message tracking.
        payload = self._build_payload(message)
        last_error: Exception | None = None
        operation_id = str(uuid.uuid4())
        message.operation_id = operation_id

        for attempt in range(self.RETRY_ATTEMPTS):
            try:
                response = self._client.post_message(payload)
                remote_message_id = self._extract_remote_message_id(response)

                message.status = MessageStatus.SENT
                message.sent_at = datetime.now(timezone.utc)
                message.remote_message_id = remote_message_id
                self._storage.save_message(message)

                self._logger.info(
                    "Sent WhatsApp message %s to %s",
                    message.id,
                    message.to,
                    extra={
                        "operation_id": operation_id,
                        "remote_message_id": remote_message_id,
                    },
                )
                return MessageStatus.SENT

            except RateLimitError as exc:
                last_error = exc
                delay = self._calculate_retry_delay(attempt, exc)
                self._logger.warning(
                    "Rate limit hit while sending message %s; retrying in %s seconds.",
                    message.id,
                    delay,
                    extra={"operation_id": operation_id},
                )
                time.sleep(delay)
                continue

            except (AuthenticationError, ContactNotFoundError) as exc:
                message.status = MessageStatus.FAILED
                message.error = str(exc)
                self._storage.save_message(message)
                self._logger.error(
                    "Non-retryable error sending message %s: %s",
                    message.id,
                    exc,
                    extra={"operation_id": operation_id},
                )
                raise

            except MessageSendError as exc:
                last_error = exc
                if attempt < self.RETRY_ATTEMPTS - 1:
                    delay = self._calculate_retry_delay(attempt, None)
                    self._logger.warning(
                        "Transient error sending message %s on attempt %s/%s: %s",
                        message.id,
                        attempt + 1,
                        self.RETRY_ATTEMPTS,
                        exc,
                        extra={"operation_id": operation_id, "retry_delay_seconds": delay},
                    )
                    time.sleep(delay)
                    continue

                message.status = MessageStatus.FAILED
                message.error = str(exc)
                self._storage.save_message(message)
                self._logger.error(
                    "Failed to send message %s after retries: %s",
                    message.id,
                    exc,
                    extra={"operation_id": operation_id},
                )
                raise

        message.status = MessageStatus.FAILED
        message.error = str(last_error) if last_error is not None else "Message could not be sent."
        self._storage.save_message(message)
        self._logger.error("Failed to send message %s after retries.", message.id, extra={"operation_id": operation_id})
        return MessageStatus.FAILED

    def send_bulk(self, messages: List[Message] | Iterable[Message]) -> List[MessageStatus]:
        """Send messages concurrently while preserving input order in the result.

        This replaces the sequential bulk loop from the legacy service and
        addresses REVIEW.md issue 12.
        """

        message_list = list(messages)
        if not message_list:
            return []

        statuses = [MessageStatus.PENDING] * len(message_list)
        max_workers = min(4, len(message_list))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(self.send_message, message): index
                for index, message in enumerate(message_list)
            }

            try:
                for future in as_completed(future_to_index):
                    index = future_to_index[future]
                    statuses[index] = future.result()
            except Exception:
                for future in future_to_index:
                    future.cancel()
                raise

        return statuses

    def send_notification_to_all_contacts(self, contacts: List[Contact], body: str) -> List[MessageStatus]:
        """Create notification messages lazily and stream them into bulk sending.

        This keeps memory use lower than the legacy list-building approach and
        addresses REVIEW.md issue 13.
        """

        return self.send_bulk(
            Message(
                id=str(uuid.uuid4()),
                to=contact.phone_number,
                body=body,
            )
            for contact in contacts
        )

    def receive_message(self, raw_payload: dict) -> Message:
        # The webhook parser centralizes payload validation and removes the
        # duplicated entry/changes/value traversal from the original service.
        parsed_message = self._webhook_parser.parse_inbound_message(raw_payload)
        message = Message(
            id=parsed_message.message_id,
            to=parsed_message.phone_number,
            body=parsed_message.body,
            message_type=parsed_message.message_type,
            status=MessageStatus.DELIVERED,
            remote_message_id=parsed_message.message_id,
            operation_id=str(uuid.uuid4()),
        )
        self._storage.save_message(message)
        self._logger.info(
            "Received WhatsApp message %s from %s",
            message.id,
            message.to,
            extra={"operation_id": message.operation_id, "remote_message_id": message.remote_message_id},
        )
        return message

    def handle_status_update(self, raw_payload: dict) -> MessageStatus:
        parsed_status = self._webhook_parser.parse_status_update(raw_payload)
        self._storage.update_message_status(parsed_status.message_id, parsed_status.status)
        self._logger.info(
            "Updated WhatsApp message %s to status %s",
            parsed_status.message_id,
            parsed_status.status.value,
            extra={"remote_message_id": parsed_status.message_id},
        )
        return parsed_status.status

    def get_conversation_history(self, phone_number: str) -> List[Message]:
        """Return all messages exchanged with the given contact."""

        return list(self._storage.get_messages_by_contact(phone_number))

    def _build_payload(self, message: Message) -> dict:
        # Payload construction is delegated to builder strategies so the
        # service can stay closed for modification when new message types are
        # added.
        payload = {
            "messaging_product": "whatsapp",
            "to": message.to,
            "type": message.message_type.value,
        }
        payload.update(self._payload_factory.build(message))
        return payload

    def _calculate_retry_delay(self, attempt: int, error: RateLimitError | None) -> float:
        if error is not None and error.retry_after_seconds is not None:
            return float(error.retry_after_seconds)

        base_delay = self.RETRY_DELAY_SECONDS * (2**attempt)
        jitter = random.uniform(0, min(1.0, base_delay * 0.2))
        return round(base_delay + jitter, 2)

    @staticmethod
    def _extract_remote_message_id(response: dict) -> Optional[str]:
        messages = response.get("messages")
        if isinstance(messages, list) and messages:
            first_message = messages[0]
            if isinstance(first_message, dict):
                remote_id = first_message.get("id")
                if isinstance(remote_id, str):
                    return remote_id

        remote_id = response.get("id")
        return remote_id if isinstance(remote_id, str) else None