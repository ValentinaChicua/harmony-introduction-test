"""Configuration helpers for the WhatsApp integration."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class WhatsAppConfig:
    """Runtime configuration for the WhatsApp API client."""

    api_token: str
    phone_number_id: str
    base_url: str = "https://api.whatsapp-business.pseudo/v1"
    timeout: int = 30

    @classmethod
    def from_env(cls) -> "WhatsAppConfig":
        """Build a config object from environment variables."""

        api_token = os.getenv("WHATSAPP_API_TOKEN")
        phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

        if not api_token:
            raise ValueError("WHATSAPP_API_TOKEN environment variable is required.")
        if not phone_number_id:
            raise ValueError("WHATSAPP_PHONE_NUMBER_ID environment variable is required.")

        base_url = os.getenv("WHATSAPP_API_BASE_URL", cls.base_url)
        timeout_raw = os.getenv("WHATSAPP_API_TIMEOUT", str(cls.timeout))

        try:
            timeout = int(timeout_raw)
        except ValueError as exc:
            raise ValueError("WHATSAPP_API_TIMEOUT must be an integer.") from exc

        return cls(
            api_token=api_token,
            phone_number_id=phone_number_id,
            base_url=base_url,
            timeout=timeout,
        )