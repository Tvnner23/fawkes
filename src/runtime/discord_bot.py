"""Bounded two-way Discord DM transport for Fawkes conversation turns.

Discord identity selects a locally allowlisted conversation participant. It
never grants Development, promotion, spending, deletion, or Rider authority.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import random
import re
import struct
import threading
import time
import uuid
from urllib import error, parse, request


DISCORD_API_ROOT = "https://discord.com/api/v10"
DISCORD_GATEWAY_FALLBACK = "wss://gateway.discord.gg/?v=10&encoding=json"
MAX_DISCORD_MESSAGE_CHARACTERS = 1_900
DIRECT_MESSAGE_INTENTS = (1 << 12) | (1 << 15)
TANNER_DM_BOOTSTRAP_MESSAGE = (
    "Fawkes here. Our private Discord connection is ready. Reply to this "
    "message to test the full conversational path."
)


class DiscordBotConfigurationError(RuntimeError):
    pass


class DiscordBotTransportError(RuntimeError):
    def __init__(self, message, *, stage=None, category="transport", provider_code=None,
                 fatal=False):
        super().__init__(message)
        self.stage = stage
        self.category = category
        self.provider_code = provider_code
        self.fatal = fatal


class DiscordGatewayClosed(DiscordBotTransportError):
    pass


class DiscordIdentityError(PermissionError):
    pass


class DiscordConversationProcessingError(RuntimeError):
    pass


class DiscordReplyDeliveryError(RuntimeError):
    pass


def _user_id(value, variable, *, required=True):
    if value is None or value == "":
        if required:
            raise DiscordBotConfigurationError(f"Discord configuration is incomplete: {variable}")
        return None
    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        raise DiscordBotConfigurationError(f"Discord identity is invalid: {variable}")
    return value


def _enabled(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_exception_detail(exception, *, secrets=()):
    """Retain useful local diagnostics without credential-bearing endpoints."""
    detail = "".join(character for character in str(exception)[:240]
                     if character.isprintable())
    for secret in secrets:
        if secret:
            detail = detail.replace(secret, "<redacted>")
    detail = re.sub(r"(?:https?|wss?)://\S+", "<redacted-endpoint>", detail,
                    flags=re.IGNORECASE)
    detail = re.sub(r"(?i)(authorization\s*[:=]\s*)\S+", r"\1<redacted>", detail)
    return detail or "no safe message supplied"


@dataclass(frozen=True, repr=False)
class DiscordRecipient:
    user_id: str
    identity: str
    rider_identity: bool
    opted_in: bool


class DiscordBotConfiguration:
    """Local credential and explicit identity binding; token repr is redacted."""

    __slots__ = ("_bot_token", "tanner", "emily")

    def __init__(self, bot_token, tanner_user_id, *, emily_user_id=None, emily_opted_in=False):
        if not isinstance(bot_token, str) or not bot_token.strip():
            raise DiscordBotConfigurationError(
                "Discord configuration is incomplete: FAWKES_DISCORD_BOT_TOKEN"
            )
        tanner = _user_id(tanner_user_id, "FAWKES_DISCORD_TANNER_USER_ID")
        emily = _user_id(emily_user_id, "FAWKES_DISCORD_EMILY_USER_ID", required=False)
        if emily is not None and emily == tanner:
            raise DiscordBotConfigurationError("Tanner and Emily Discord identities must be distinct")
        self._bot_token = bot_token
        self.tanner = DiscordRecipient(tanner, "tanner", True, True)
        self.emily = (DiscordRecipient(emily, "emily", False, bool(emily_opted_in))
                      if emily is not None else None)

    @classmethod
    def from_environment(cls, environment=None):
        values = os.environ if environment is None else environment
        return cls(
            values.get("FAWKES_DISCORD_BOT_TOKEN"),
            values.get("FAWKES_DISCORD_TANNER_USER_ID"),
            emily_user_id=values.get("FAWKES_DISCORD_EMILY_USER_ID"),
            emily_opted_in=_enabled(values.get("FAWKES_DISCORD_EMILY_OPTED_IN")),
        )

    @property
    def bot_token(self):
        return self._bot_token

    def __repr__(self):
        return ("DiscordBotConfiguration(bot_token=<redacted>, "
                f"tanner_user_id={self.tanner.user_id!r}, "
                f"emily_user_id={self.emily.user_id if self.emily else None!r})")

    def recipient(self, user_id, *, require_opt_in=True):
        candidate = str(user_id)
        for recipient in (self.tanner, self.emily):
            if recipient is not None and recipient.user_id == candidate:
                if require_opt_in and not recipient.opted_in:
                    raise DiscordIdentityError("Discord recipient has not explicitly opted in")
                return recipient
        raise DiscordIdentityError("Discord user is not allowlisted")

    def recipient_identity(self, identity, *, require_opt_in=True):
        if identity == "tanner":
            recipient = self.tanner
        elif identity == "emily":
            recipient = self.emily
        else:
            raise DiscordIdentityError("Discord recipient identity is not allowlisted")
        if recipient is None:
            raise DiscordIdentityError("Discord recipient identity is not configured")
        if require_opt_in and not recipient.opted_in:
            raise DiscordIdentityError("Discord recipient has not explicitly opted in")
        return recipient


class DiscordBotHttpClient:
    """Discord HTTP API client with sanitized failures and body-free receipts."""

    def __init__(self, configuration, *, opener=None):
        self.configuration = configuration
        self.opener = opener or request.urlopen

    def _request(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        outbound = request.Request(
            DISCORD_API_ROOT + path, data=body, method=method,
            headers={"Authorization": f"Bot {self.configuration.bot_token}",
                     "Content-Type": "application/json", "User-Agent": "Fawkes/1"},
        )
        try:
            with self.opener(outbound, timeout=20) as response:
                raw = response.read()
                status = getattr(response, "status", 200)
        except error.HTTPError as exc:
            # HTTPError URLs can contain sensitive provider endpoints. Retain
            # only Discord's numeric status and bounded JSON error identity.
            try:
                failure = json.loads(exc.read().decode("utf-8"))
                provider_code = failure.get("code")
                provider_message = failure.get("message")
            except Exception:
                provider_code = provider_message = None
            detail = f"status={exc.code}"
            if isinstance(provider_code, int):
                detail += f", code={provider_code}"
            if isinstance(provider_message, str):
                safe = "".join(character for character in provider_message[:160]
                               if character.isprintable())
                detail += f", message={safe}"
            raise DiscordBotTransportError(f"Discord bot HTTP request failed: {detail}") from None
        except Exception:
            raise DiscordBotTransportError("Discord bot HTTP delivery failed") from None
        if status < 200 or status >= 300:
            raise DiscordBotTransportError("Discord bot HTTP delivery failed")
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise DiscordBotTransportError("Discord bot returned malformed data") from None

    def send_dm(self, recipient_id, message):
        recipient = self.configuration.recipient(recipient_id)
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Discord DM must be nonempty and sanitized/bounded")
        if recipient.identity == "emily" and not message.lstrip().lower().startswith("fawkes"):
            message = "Fawkes: " + message
        if len(message) > MAX_DISCORD_MESSAGE_CHARACTERS:
            raise ValueError("Discord DM must be nonempty and sanitized/bounded")
        channel = self._request("POST", "/users/@me/channels", {"recipient_id": recipient.user_id})
        channel_id = channel.get("id")
        if not isinstance(channel_id, str) or not channel_id.isdigit():
            raise DiscordBotTransportError("Discord bot did not return a DM channel identity")
        result = self._request("POST", f"/channels/{parse.quote(channel_id, safe='')}/messages",
                               {"content": message, "allowed_mentions": {"parse": []}})
        message_id = result.get("id")
        if not isinstance(message_id, str) or not message_id.isdigit():
            raise DiscordBotTransportError("Discord bot did not return a message identity")
        return {"provider": "discord_bot", "message_id": message_id,
                "channel_id": channel_id, "recipient_identity": recipient.identity,
                "creates_authority": False}

    def gateway_url(self):
        result = self._request("GET", "/gateway/bot")
        url = result.get("url")
        if not isinstance(url, str) or not url.startswith("wss://"):
            raise DiscordBotTransportError("Discord bot did not return a secure Gateway URL")
        return url.rstrip("/") + "/?v=10&encoding=json"

    def dm_channel(self, recipient):
        result = self._request("POST", "/users/@me/channels", {"recipient_id": recipient.user_id})
        channel_id = result.get("id")
        if not isinstance(channel_id, str) or not channel_id.isdigit():
            raise DiscordBotTransportError("Discord bot did not return a DM channel identity")
        return channel_id

    def messages_after(self, recipient, after_message_id, *, limit=100):
        channel_id = self.dm_channel(recipient)
        query = {"limit": min(max(int(limit), 1), 100)}
        if after_message_id:
            query["after"] = after_message_id
        path = f"/channels/{parse.quote(channel_id, safe='')}/messages?{parse.urlencode(query)}"
        result = self._request("GET", path)
        if not isinstance(result, list):
            raise DiscordBotTransportError("Discord bot returned malformed DM history")
        return sorted(result, key=lambda item: int(item.get("id", "0")))


class DiscordMessageCursorStore:
    """Per-recipient durable cursor; message bodies are never retained here."""

    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _load(self):
        if not self.path.exists():
            return {"schema_version": 1, "cursors": {}}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        claimed = value.pop("record_sha256", None)
        actual = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if (value.get("schema_version") != 1 or not isinstance(value.get("cursors"), dict)
                or claimed != actual):
            raise DiscordBotTransportError("Discord cursor state is invalid", fatal=True)
        return value

    def get(self, identity):
        with self._lock:
            return self._load()["cursors"].get(identity)

    def advance(self, identity, message_id):
        if not isinstance(message_id, str) or not message_id.isdigit():
            raise DiscordBotTransportError("Discord message identity is invalid")
        with self._lock:
            value = self._load()
            current = value["cursors"].get(identity)
            if current is not None and int(message_id) <= int(current):
                return False
            value["cursors"][identity] = message_id
            value["updated_at"] = datetime.now(timezone.utc).isoformat()
            value["record_sha256"] = hashlib.sha256(
                json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
            temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.chmod(temporary, 0o600)
            temporary.replace(self.path)
            return True


def bootstrap_tanner_dm(configuration, http_client):
    """Send the explicit one-shot bootstrap only to the configured Rider."""
    receipt = http_client.send_dm(
        configuration.tanner.user_id,
        TANNER_DM_BOOTSTRAP_MESSAGE,
    )
    return {
        "status": "delivered",
        "recipient_identity": receipt["recipient_identity"],
        "creates_authority": False,
    }


@dataclass(frozen=True)
class DiscordOutboundAuthorization:
    """Explicit permission evidence for a non-reply Discord communication."""

    recipient_identity: str
    purpose: str
    authorization_reference: str

    def __post_init__(self):
        if self.recipient_identity not in {"tanner", "emily"}:
            raise DiscordIdentityError("Discord recipient identity is not allowlisted")
        if not isinstance(self.purpose, str) or not self.purpose.strip():
            raise PermissionError("Discord outbound communication requires an authorized purpose")
        if (not isinstance(self.authorization_reference, str)
                or not self.authorization_reference.strip()):
            raise PermissionError("Discord outbound communication requires authorization evidence")


class DiscordOutboundBridge:
    """Resolve symbolic recipients for replies or explicitly authorized outreach."""

    def __init__(self, configuration, http_client):
        self.configuration = configuration
        self.http_client = http_client

    def send_conversation_reply(self, recipient, message):
        resolved = self.configuration.recipient(recipient.user_id)
        if resolved != recipient:
            raise DiscordIdentityError("Discord conversation recipient binding changed")
        return self.http_client.send_dm(resolved.user_id, message)

    def send_authorized(self, authorization, message):
        if not isinstance(authorization, DiscordOutboundAuthorization):
            raise PermissionError("Discord outbound communication requires explicit authorization")
        recipient = self.configuration.recipient_identity(authorization.recipient_identity)
        receipt = self.http_client.send_dm(recipient.user_id, message)
        return {**receipt, "authorization_reference": authorization.authorization_reference,
                "purpose": authorization.purpose, "creates_authority": False}


class DiscordConversationBridge:
    """Validate an inbound DM before handing exact text to normal Chat."""

    def __init__(self, configuration, *, chat_service, http_client, outbound_bridge=None,
                 cursor_store=None):
        self.configuration = configuration
        self.chat_service = chat_service
        self.http_client = http_client
        self.outbound_bridge = outbound_bridge or DiscordOutboundBridge(configuration, http_client)
        self.cursor_store = cursor_store

    def handle_dispatch(self, event):
        if event.get("t") != "MESSAGE_CREATE":
            return {"status": "ignored", "creates_authority": False}
        message = event.get("d") or {}
        if message.get("guild_id") is not None:
            return {"status": "ignored", "creates_authority": False}
        author = message.get("author") or {}
        if author.get("bot"):
            return {"status": "ignored", "creates_authority": False}
        recipient = self.configuration.recipient(author.get("id"))
        if not recipient.rider_identity:
            # Social-contact conversation needs its separately authorized
            # principal boundary; opt-in alone must never become Rider status.
            raise DiscordIdentityError("Social contact is not a Rider conversational principal")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            return {"status": "ignored", "creates_authority": False}
        message_id = message.get("id")
        if self.cursor_store is not None:
            current = self.cursor_store.get(recipient.identity)
            if current is not None and isinstance(message_id, str) and message_id.isdigit() \
                    and int(message_id) <= int(current):
                return {"status": "duplicate", "creates_authority": False}
        try:
            result = self.chat_service.send(content, source="discord_dm")
        except Exception as exc:
            detail = _safe_exception_detail(exc)
            raise DiscordConversationProcessingError(
                f"Fawkes ChatService failed while processing Discord DM: "
                f"{type(exc).__name__}: {detail}"
            ) from None
        reply = result["message"]["content"]
        # ChatService has durably archived the accepted inbound turn and Fawkes
        # response at this point. Commit the inbound cursor before transport
        # delivery so a reconnect cannot generate a second Phoenix turn/reply.
        if self.cursor_store is not None:
            self.cursor_store.advance(recipient.identity, message_id)
        try:
            receipt = self.outbound_bridge.send_conversation_reply(recipient, reply)
        except Exception as exc:
            detail = _safe_exception_detail(exc, secrets=(self.configuration.bot_token,))
            raise DiscordReplyDeliveryError(
                f"Discord DM reply delivery failed: {type(exc).__name__}: {detail}"
            ) from None
        return {"status": "replied", "inbound_message_id": message.get("id"),
                "archive_source": "discord_dm", "delivery_receipt": receipt,
                "principal": "discord-conversational:tanner", "rider_commands_authorized": False,
                "development_authority": False, "creates_authority": False}

    def backfill(self):
        """Recover only post-cursor allowlisted DMs in chronological order."""
        if self.cursor_store is None:
            return []
        results = []
        for recipient in (self.configuration.tanner, self.configuration.emily):
            if recipient is None or not recipient.opted_in:
                continue
            # Emily requires a separately authorized social principal boundary;
            # the existing Rider ChatService must never expose Tanner context.
            if not recipient.rider_identity:
                continue
            cursor = self.cursor_store.get(recipient.identity)
            if cursor is None:
                # Initialization is an explicit pre-start action. Silently
                # choosing a historical boundary here could swallow a message
                # that arrived between READY and this query.
                continue
            for message in self.http_client.messages_after(recipient, cursor):
                results.append(self.handle_dispatch({"op": 0, "t": "MESSAGE_CREATE", "d": message}))
        return results


class DiscordGatewayRunner:
    """Minimal Gateway v10 loop for inbound direct-message dispatch events."""

    def __init__(self, configuration, bridge, *, http_client=None, websocket_factory=None,
                 on_ready=None, on_message_failure=None, on_lifecycle=None,
                 max_reconnect_attempts=0, sleep=time.sleep, random_source=random.random):
        self.configuration = configuration
        self.bridge = bridge
        self.http_client = http_client or DiscordBotHttpClient(configuration)
        self.websocket_factory = websocket_factory
        self.on_ready = on_ready
        self.on_message_failure = on_message_failure
        self.on_lifecycle = on_lifecycle
        self.max_reconnect_attempts = max_reconnect_attempts
        self.sleep = sleep
        self.random_source = random_source
        self._stop = threading.Event()
        self.session_id = None
        self.resume_gateway_url = None
        self.sequence = None

    def stop(self):
        self._stop.set()

    def _lifecycle(self, state, **detail):
        if self.on_lifecycle is not None:
            self.on_lifecycle(state, detail)

    @staticmethod
    def _receive(socket, timeout_errors):
        try:
            if hasattr(socket, "recv_data"):
                opcode, data = socket.recv_data(control_frame=True)
                if opcode == 8:
                    raw = data if isinstance(data, bytes) else str(data).encode("utf-8")
                    code = struct.unpack("!H", raw[:2])[0] if len(raw) >= 2 else 1005
                    reason = raw[2:].decode("utf-8", errors="replace")
                    safe = "".join(character for character in reason[:160]
                                   if character.isprintable())
                    fatal = code in {4004, 4010, 4011, 4012, 4013, 4014}
                    raise DiscordGatewayClosed(
                        f"Discord Gateway closed: code={code}, message={safe or 'no reason supplied'}",
                        stage="receive", category="gateway_close", provider_code=code,
                        fatal=fatal,
                    )
                if opcode not in {1, 2}:
                    return None
                raw = data.decode("utf-8") if isinstance(data, bytes) else data
            else:
                raw = socket.recv()
            return json.loads(raw)
        except timeout_errors:
            return None
        except DiscordBotTransportError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            raise DiscordBotTransportError("Discord Gateway returned malformed data") from None

    def _run_connection(self, gateway_url, timeout_errors, *, resume):
        socket = None
        stage = "connect"
        reconnect = False
        identify_fallback = False
        try:
            socket = self.websocket_factory(gateway_url, timeout=30)
            stage = "hello"
            hello = self._receive(socket, timeout_errors)
            if not isinstance(hello, dict) or hello.get("op") != 10:
                raise DiscordBotTransportError("Discord Gateway did not send HELLO")
            interval = max(1.0, float(hello["d"]["heartbeat_interval"]) / 1000)
            stage = "resume" if resume else "identify"
            if resume:
                socket.send(json.dumps({"op": 6, "d": {
                    "token": self.configuration.bot_token,
                    "session_id": self.session_id,
                    "seq": self.sequence,
                }}))
                self._lifecycle("RESUME_ATTEMPT")
            else:
                socket.send(json.dumps({"op": 2, "d": {
                    "token": self.configuration.bot_token,
                    "intents": DIRECT_MESSAGE_INTENTS,
                    "properties": {"os": "linux", "browser": "fawkes", "device": "fawkes"},
                }}))
            last_heartbeat = time.monotonic()
            heartbeat_acknowledged = True
            ready = False
            stage = "ready"
            while not self._stop.is_set():
                if time.monotonic() - last_heartbeat >= interval:
                    if not heartbeat_acknowledged:
                        raise DiscordBotTransportError(
                            "Discord Gateway heartbeat was not acknowledged",
                            stage="heartbeat", category="heartbeat_timeout",
                        )
                    stage = "heartbeat"
                    socket.send(json.dumps({"op": 1, "d": self.sequence}))
                    heartbeat_acknowledged = False
                    last_heartbeat = time.monotonic()
                    stage = "receive"
                payload = self._receive(socket, timeout_errors)
                if payload is None:
                    continue
                if payload.get("s") is not None:
                    self.sequence = payload["s"]
                operation = payload.get("op")
                if operation == 11:
                    heartbeat_acknowledged = True
                    continue
                if operation == 1:
                    socket.send(json.dumps({"op": 1, "d": self.sequence}))
                    heartbeat_acknowledged = False
                    last_heartbeat = time.monotonic()
                    continue
                if operation == 7:
                    self._lifecycle("RECONNECT_REQUESTED", provider_code=7)
                    return {"reconnect": True, "resume": True}
                if operation == 9:
                    resumable = payload.get("d") is True
                    self._lifecycle("INVALID_SESSION", resumable=resumable)
                    if not resumable:
                        self.session_id = self.resume_gateway_url = self.sequence = None
                    return {"reconnect": True, "resume": resumable, "identify_fallback": not resumable}
                if operation != 0:
                    continue
                event_type = payload.get("t")
                if event_type == "READY":
                    data = payload.get("d") or {}
                    self.session_id = data.get("session_id")
                    self.resume_gateway_url = data.get("resume_gateway_url")
                    ready = True
                    self._lifecycle("READY")
                    if self.on_ready is not None:
                        self.on_ready()
                    try:
                        self.bridge.backfill()
                    except (DiscordConversationProcessingError, DiscordReplyDeliveryError,
                            DiscordIdentityError) as exc:
                        if self.on_message_failure is None:
                            raise
                        self.on_message_failure(exc)
                    stage = "receive"
                    continue
                if event_type == "RESUMED":
                    ready = True
                    self._lifecycle("RESUMED")
                    if self.on_ready is not None:
                        self.on_ready()
                    try:
                        self.bridge.backfill()
                    except (DiscordConversationProcessingError, DiscordReplyDeliveryError,
                            DiscordIdentityError) as exc:
                        if self.on_message_failure is None:
                            raise
                        self.on_message_failure(exc)
                    stage = "receive"
                    continue
                if not ready:
                    raise DiscordBotTransportError("Discord Gateway dispatched an event before READY")
                stage = "message_dispatch"
                try:
                    self.bridge.handle_dispatch(payload)
                except (DiscordConversationProcessingError, DiscordReplyDeliveryError,
                        DiscordIdentityError) as exc:
                    if self.on_message_failure is None:
                        raise
                    self.on_message_failure(exc)
                stage = "receive"
            return {"reconnect": False, "resume": False}
        except DiscordGatewayClosed:
            raise
        except DiscordBotTransportError as exc:
            if exc.stage is None:
                exc.stage = stage
            raise
        except Exception as exc:
            detail = _safe_exception_detail(exc, secrets=(self.configuration.bot_token,))
            raise DiscordBotTransportError(
                f"{type(exc).__name__}: {detail}", stage=stage,
                category="local_transport",
            ) from None
        finally:
            if socket is not None:
                try:
                    socket.close()
                except Exception:
                    pass

    def run(self):
        timeout_errors = (TimeoutError,)
        if self.websocket_factory is None:
            try:
                import websocket
            except ImportError:
                raise DiscordBotTransportError("websocket-client dependency is unavailable") from None
            self.websocket_factory = websocket.create_connection
            timeout_errors = (TimeoutError, websocket.WebSocketTimeoutException)
        stage = "gateway_url"
        try:
            gateway_url = self.http_client.gateway_url()
            attempt = 0
            resume = False
            while not self._stop.is_set():
                selected_url = (self.resume_gateway_url.rstrip("/") + "/?v=10&encoding=json"
                                if resume and self.resume_gateway_url else gateway_url)
                try:
                    outcome = self._run_connection(selected_url, timeout_errors, resume=resume)
                    if not outcome["reconnect"]:
                        return
                    resume = outcome["resume"] and bool(self.session_id)
                except DiscordGatewayClosed as exc:
                    if exc.fatal:
                        raise
                    if self.max_reconnect_attempts == 0:
                        raise
                    resume = bool(self.session_id and self.sequence is not None)
                    self._lifecycle("RECONNECTING", provider_code=exc.provider_code)
                except DiscordBotTransportError as exc:
                    if exc.fatal:
                        raise
                    if self.max_reconnect_attempts == 0:
                        raise
                    resume = bool(self.session_id and self.sequence is not None)
                    self._lifecycle("RECONNECTING", category=exc.category)
                attempt += 1
                if self.max_reconnect_attempts is not None and attempt > self.max_reconnect_attempts:
                    raise DiscordBotTransportError(
                        "Discord Gateway reconnect limit exceeded", stage="reconnect",
                        category="reconnect_exhausted",
                    )
                delay = min(60.0, 1.0 * (2 ** min(attempt - 1, 6)))
                delay += delay * 0.25 * self.random_source()
                self.sleep(delay)
        except (DiscordConversationProcessingError, DiscordReplyDeliveryError):
            raise
        except DiscordBotTransportError as exc:
            failure_stage = exc.stage or stage
            raise DiscordBotTransportError(
                f"Discord Gateway failure at stage={failure_stage}: {exc}",
                stage=failure_stage, category=exc.category,
                provider_code=exc.provider_code, fatal=exc.fatal,
            ) from None
        except Exception as exc:
            detail = _safe_exception_detail(exc, secrets=(self.configuration.bot_token,))
            raise DiscordBotTransportError(
                f"Discord Gateway failure at stage={stage}: "
                f"{type(exc).__name__}: {detail}"
            ) from None
