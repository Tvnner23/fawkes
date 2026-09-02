"""Thin Discord webhook binding for Rider notification projections."""

import json
import os
from urllib import request


DISCORD_WEBHOOK_ENVIRONMENT_VARIABLE = "FAWKES_DISCORD_WEBHOOK_URL"
MAX_DISCORD_MESSAGE_CHARACTERS = 480


class DiscordWebhookConfiguration:
    """Credential-bound configuration whose representation never exposes its URL."""

    __slots__ = ("_webhook_url",)

    def __init__(self, webhook_url):
        if not isinstance(webhook_url, str) or not webhook_url.strip():
            raise RuntimeError(
                f"Discord configuration is incomplete: {DISCORD_WEBHOOK_ENVIRONMENT_VARIABLE}"
            )
        self._webhook_url = webhook_url

    @property
    def webhook_url(self):
        return self._webhook_url

    @classmethod
    def from_environment(cls, environment=None):
        values = os.environ if environment is None else environment
        return cls(values.get(DISCORD_WEBHOOK_ENVIRONMENT_VARIABLE))

    def __repr__(self):
        return "DiscordWebhookConfiguration(webhook_url=<redacted>)"


class DiscordDeliveryError(RuntimeError):
    """Sanitized provider failure that cannot carry the credential-bearing URL."""


class DiscordWebhookSender:
    """Callable sender compatible with RiderNotificationStore.deliver."""

    def __init__(self, configuration, *, opener=None):
        self.configuration = configuration
        self.opener = opener or request.urlopen

    def __call__(self, message):
        if (not isinstance(message, str) or not message.strip()
                or len(message) > MAX_DISCORD_MESSAGE_CHARACTERS):
            raise ValueError("Discord notification must be nonempty and sanitized/bounded")
        body = json.dumps({"content": message, "allowed_mentions": {"parse": []}}).encode("utf-8")
        outbound = request.Request(
            self.configuration.webhook_url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "Fawkes-Mobile/1"},
        )
        try:
            with self.opener(outbound, timeout=20) as response:
                status = getattr(response, "status", 204)
        except Exception:
            # Suppress the provider exception context because urllib failures may
            # embed the credential-bearing webhook URL in their text.
            raise DiscordDeliveryError("Discord webhook delivery failed") from None
        if status not in {200, 204}:
            raise DiscordDeliveryError("Discord webhook delivery failed")
        return {"provider": "discord", "provider_status": "delivered", "http_status": status}
