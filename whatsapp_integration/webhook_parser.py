"""Parsing utilities for WhatsApp webhook payloads."""

from dataclasses import dataclass

from .exceptions import InvalidWebhookPayloadError
from .models import MessageStatus, MessageType


@dataclass(frozen=True)
class ParsedInboundMessage:
    message_id: str
    phone_number: str
    body: str
    message_type: MessageType


@dataclass(frozen=True)
class ParsedStatusUpdate:
    message_id: str
    status: MessageStatus


class WebhookParser:
    """Validate and normalize the raw webhook payloads."""

    def parse_inbound_message(self, raw_payload: dict) -> ParsedInboundMessage:
        value = self._extract_value(raw_payload)
        raw_message = self._extract_first_item(value, "messages")

        contact = self._first_optional_item(value.get("contacts", [])) or {}
        phone_number = contact.get("wa_id") or raw_message.get("from") or value.get("metadata", {}).get(
            "phone_number_id"
        )
        if not phone_number:
            raise InvalidWebhookPayloadError("Inbound webhook is missing a contact phone number.")

        try:
            message_type = MessageType(raw_message.get("type", MessageType.TEXT.value))
        except ValueError as exc:
            raise InvalidWebhookPayloadError("Inbound webhook contains an unsupported message type.") from exc

        body = (
            raw_message.get("text", {}).get("body")
            or raw_message.get("caption")
            or raw_message.get("body")
            or raw_message.get("id", "")
        )

        return ParsedInboundMessage(
            message_id=raw_message["id"],
            phone_number=phone_number,
            body=body,
            message_type=message_type,
        )

    def parse_status_update(self, raw_payload: dict) -> ParsedStatusUpdate:
        value = self._extract_value(raw_payload)
        status_data = self._extract_first_item(value, "statuses")

        try:
            status = MessageStatus(status_data["status"])
        except ValueError as exc:
            raise InvalidWebhookPayloadError("Status webhook contains an unsupported status value.") from exc

        return ParsedStatusUpdate(message_id=status_data["id"], status=status)

    def _extract_value(self, raw_payload: dict) -> dict:
        if not isinstance(raw_payload, dict):
            raise InvalidWebhookPayloadError("Webhook payload must be a dictionary.")

        entry = self._extract_first_item(raw_payload, "entry")
        change = self._extract_first_item(entry, "changes")
        value = change.get("value")
        if not isinstance(value, dict):
            raise InvalidWebhookPayloadError("Webhook payload is missing the change value.")

        return value

    def _extract_first_item(self, payload: dict, key: str) -> dict:
        items = payload.get(key)
        item = self._first_optional_item(items)
        if item is None:
            raise InvalidWebhookPayloadError(f"Webhook payload is missing '{key}'.")
        return item

    @staticmethod
    def _first_optional_item(items: object) -> dict | None:
        if not isinstance(items, list) or not items:
            return None

        item = items[0]
        if not isinstance(item, dict):
            return None

        return item