"""Thin Twilio SMS delivery binding for Rider notification projections."""

from dataclasses import dataclass
from urllib import parse, request
import base64
import os


TWILIO_ENVIRONMENT_VARIABLES = (
    "FAWKES_TWILIO_ACCOUNT_SID",
    "FAWKES_TWILIO_AUTH_TOKEN",
    "FAWKES_TWILIO_FROM_NUMBER",
    "FAWKES_TANNER_PHONE_NUMBER",
)
MAX_SMS_CHARACTERS = 480


@dataclass(frozen=True)
class TwilioSmsConfiguration:
    account_sid: str
    auth_token: str
    from_number: str
    tanner_number: str

    @classmethod
    def from_environment(cls, environment=None):
        values = environment or os.environ
        missing = [name for name in TWILIO_ENVIRONMENT_VARIABLES if not values.get(name)]
        if missing:
            raise RuntimeError("Twilio configuration is incomplete: " + ", ".join(missing))
        return cls(*(values[name] for name in TWILIO_ENVIRONMENT_VARIABLES))


class TwilioSmsSender:
    """Callable sender compatible with RiderNotificationStore.deliver."""

    def __init__(self, configuration, *, opener=None):
        self.configuration = configuration
        self.opener = opener or request.urlopen

    def __call__(self, message):
        if not isinstance(message, str) or not message.strip() or len(message) > MAX_SMS_CHARACTERS:
            raise ValueError("SMS body must be nonempty and sanitized/bounded")
        config = self.configuration
        url = (f"https://api.twilio.com/2010-04-01/Accounts/"
               f"{parse.quote(config.account_sid, safe='')}/Messages.json")
        body = parse.urlencode({"To": config.tanner_number, "From": config.from_number,
                                "Body": message}).encode("utf-8")
        token = base64.b64encode(f"{config.account_sid}:{config.auth_token}".encode()).decode()
        outbound = request.Request(url, data=body, method="POST",
            headers={"Authorization": f"Basic {token}",
                     "Content-Type": "application/x-www-form-urlencoded"})
        with self.opener(outbound, timeout=20) as response:
            import json
            result = json.loads(response.read().decode("utf-8"))
        sid = result.get("sid")
        status = result.get("status")
        if not isinstance(sid, str) or not sid:
            raise RuntimeError("Twilio response did not contain a message identity")
        # Never retain credentials, numbers, or the provider response body.
        return {"provider": "twilio", "message_sid": sid, "provider_status": status}
