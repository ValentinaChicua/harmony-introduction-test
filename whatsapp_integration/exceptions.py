class WhatsAppError(Exception):
    """Base exception for all WhatsApp integration errors."""


class MessageSendError(WhatsAppError):
    """Raised when a message cannot be delivered to the API."""


class AuthenticationError(WhatsAppError):
    """Raised when the API token is invalid or expired."""


class RateLimitError(WhatsAppError):
    """Raised when the API rate limit is exceeded."""

    def __init__(self, message: str, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ContactNotFoundError(WhatsAppError):
    """Raised when the target phone number is not registered on WhatsApp."""


class InvalidWebhookPayloadError(WhatsAppError):
    """Raised when an inbound webhook payload does not match the expected shape."""
