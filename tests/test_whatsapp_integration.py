import os
import unittest
from unittest.mock import patch

from whatsapp_integration import Contact, Message, MessageStatus, MessageType, WhatsAppService
from whatsapp_integration.config import WhatsAppConfig
from whatsapp_integration.exceptions import InvalidWebhookPayloadError, RateLimitError
from whatsapp_integration.http_client import WhatsAppHttpClient
from whatsapp_integration.storage import InMemoryMessageStorage
from whatsapp_integration.webhook_parser import WebhookParser


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_message(self, payload):
        self.calls.append(payload)
        return self.response


class RateLimitClient:
    def __init__(self):
        self.calls = 0

    def post_message(self, payload):
        self.calls += 1
        raise RateLimitError("WhatsApp API rate limit exceeded.", retry_after_seconds=5)


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"messages": [{"id": "remote-123"}]}
        self.ok = status_code < 400
        self.text = "ok"
        self.headers = {}

    def json(self):
        return self._payload


class CountingSession:
    instances = 0
    posts = 0

    def __init__(self):
        CountingSession.instances += 1

    def post(self, *args, **kwargs):
        CountingSession.posts += 1
        return FakeResponse()

    def close(self):
        return None


class WhatsAppIntegrationTests(unittest.TestCase):
    def setUp(self):
        os.environ["WHATSAPP_API_TOKEN"] = "token"
        os.environ["WHATSAPP_PHONE_NUMBER_ID"] = "phone-id"

    def tearDown(self):
        os.environ.pop("WHATSAPP_API_TOKEN", None)
        os.environ.pop("WHATSAPP_PHONE_NUMBER_ID", None)
        os.environ.pop("WHATSAPP_API_BASE_URL", None)
        os.environ.pop("WHATSAPP_API_TIMEOUT", None)

    def test_send_message_uses_injected_client_and_persists_message(self):
        storage = InMemoryMessageStorage()
        client = FakeClient({"messages": [{"id": "remote-123"}]})
        service = WhatsAppService(client=client, storage=storage)

        message = Message(id="local-1", to="573001112233", body="Hola")

        status = service.send_message(message)

        self.assertEqual(status, MessageStatus.SENT)
        self.assertEqual(client.calls[0]["to"], "573001112233")
        self.assertEqual(client.calls[0]["text"]["body"], "Hola")
        self.assertEqual(storage.get_messages_by_contact("573001112233")[0].id, "local-1")
        self.assertEqual(storage.get_messages_by_contact("573001112233")[0].remote_message_id, "remote-123")
        self.assertIsNotNone(storage.get_messages_by_contact("573001112233")[0].operation_id)

    def test_storage_indexes_messages_and_conversations(self):
        storage = InMemoryMessageStorage()
        message = Message(id="local-idx", to="573001112233", body="Hola", remote_message_id="remote-idx")

        storage.save_message(message)
        storage.update_message_status("remote-idx", MessageStatus.READ)

        history = storage.get_messages_by_contact("573001112233")
        conversation = storage.get_conversation("573001112233")

        self.assertEqual([item.id for item in history], ["local-idx"])
        self.assertEqual(history[0].status, MessageStatus.READ)
        self.assertIsNotNone(conversation)
        self.assertEqual(conversation.messages[0].id, "local-idx")

    def test_receive_message_valid_payload_creates_message(self):
        service = WhatsAppService(
            client=FakeClient({"messages": [{"id": "remote-123"}]}),
            storage=InMemoryMessageStorage(),
        )

        raw_payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "business-id"},
                                "contacts": [{"wa_id": "573001112233", "profile": {"name": "Ana"}}],
                                "messages": [
                                    {
                                        "id": "inbound-1",
                                        "type": "text",
                                        "from": "573001112233",
                                        "text": {"body": "Hola"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }

        message = service.receive_message(raw_payload)

        self.assertEqual(message.id, "inbound-1")
        self.assertEqual(message.to, "573001112233")
        self.assertEqual(message.body, "Hola")
        self.assertEqual(message.status, MessageStatus.DELIVERED)

    def test_invalid_webhook_payload_raises_domain_error(self):
        parser = WebhookParser()

        with self.assertRaises(InvalidWebhookPayloadError):
            parser.parse_inbound_message({"entry": []})

    def test_send_notification_to_all_contacts_builds_messages_sequentially(self):
        storage = InMemoryMessageStorage()
        client = FakeClient({"messages": [{"id": "remote-123"}]})
        service = WhatsAppService(client=client, storage=storage)

        statuses = service.send_notification_to_all_contacts(
            (Contact(phone_number=phone_number, name=name) for phone_number, name in [("573001112233", "Ana"), ("573101112233", "Luis")]),
            "Aviso",
        )

        self.assertEqual(statuses, [MessageStatus.SENT, MessageStatus.SENT])
        self.assertEqual(len(client.calls), 2)

    def test_send_message_marks_failed_after_exhausting_rate_limit_retries(self):
        storage = InMemoryMessageStorage()
        service = WhatsAppService(client=RateLimitClient(), storage=storage)

        with patch("whatsapp_integration.whatsapp_service_v2.time.sleep"):
            status = service.send_message(Message(id="local-2", to="573001112233", body="Hola"))

        self.assertEqual(status, MessageStatus.FAILED)
        self.assertEqual(storage.get_messages_by_contact("573001112233")[0].status, MessageStatus.FAILED)
        self.assertGreaterEqual(len(storage.get_messages_by_contact("573001112233")), 1)

    def test_http_client_reuses_session_within_the_same_thread(self):
        CountingSession.instances = 0
        CountingSession.posts = 0

        with patch("whatsapp_integration.http_client.requests.Session", CountingSession):
            client = WhatsAppHttpClient(
                config=WhatsAppConfig(api_token="token", phone_number_id="phone-id", base_url="https://example", timeout=1)
            )

            client.post_message({"to": "573001112233", "type": "text", "text": {"body": "hola"}})
            client.post_message({"to": "573001112233", "type": "text", "text": {"body": "hola 2"}})

        self.assertEqual(CountingSession.instances, 1)
        self.assertEqual(CountingSession.posts, 2)

    def test_rate_limit_error_uses_retry_after_delay(self):
        storage = InMemoryMessageStorage()
        service = WhatsAppService(client=RateLimitClient(), storage=storage)

        with patch("whatsapp_integration.whatsapp_service_v2.time.sleep") as mock_sleep:
            service.send_message(Message(id="local-3", to="573001112233", body="Hola"))

        self.assertEqual(mock_sleep.call_args_list[0].args[0], 5)


if __name__ == "__main__":
    unittest.main()
