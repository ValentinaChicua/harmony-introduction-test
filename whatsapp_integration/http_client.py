"""HTTP client for the WhatsApp Business API.

This module replaces the per-request session creation from the legacy service
and centralizes the fixes for REVIEW.md issues 4 and 6.
"""

import logging
import threading

import requests

from .config import WhatsAppConfig
from .exceptions import AuthenticationError, ContactNotFoundError, MessageSendError, RateLimitError


class WhatsAppHttpClient:
    """Low-level synchronous client for WhatsApp Business API calls."""

    def __init__(self, config: WhatsAppConfig, logger: logging.Logger | None = None):
        self._config = config
        self._logger = logger or logging.getLogger(__name__)
        self._session_local = threading.local()

    def close(self) -> None:
        session = getattr(self._session_local, "session", None)
        if session is not None:
            session.close()
            delattr(self._session_local, "session")

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._config.api_token}",
            "Content-Type": "application/json",
        }

    def _get_session(self) -> requests.Session:
        session = getattr(self._session_local, "session", None)
        if session is None:
            session = requests.Session()
            self._session_local.session = session
        return session

    @staticmethod
    def _retry_after_seconds(response: requests.Response) -> int | None:
        retry_after = response.headers.get("Retry-After")
        if retry_after is None:
            return None

        try:
            return int(retry_after)
        except ValueError:
            return None

    def post_message(self, payload: dict) -> dict:
        url = f"{self._config.base_url}/{self._config.phone_number_id}/messages"
        session = self._get_session()

        try:
            response = session.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=self._config.timeout,
            )
        except requests.RequestException as exc:
            raise MessageSendError(f"Network error while sending WhatsApp message: {exc}") from exc

        if response.status_code == 401:
            raise AuthenticationError("Invalid or expired API token.")
        if response.status_code == 429:
            raise RateLimitError("WhatsApp API rate limit exceeded.", self._retry_after_seconds(response))
        if response.status_code == 404:
            raise ContactNotFoundError("Phone number not found on WhatsApp.")
        if not response.ok:
            raise MessageSendError(f"API error {response.status_code}: {response.text}")

        try:
            return response.json()
        except ValueError as exc:
            raise MessageSendError("The API returned an invalid JSON response.") from exc