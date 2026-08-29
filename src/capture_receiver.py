from http.server import BaseHTTPRequestHandler, HTTPServer
import json

from ingest import ingest_bytes


HOST = "127.0.0.1"
PORT = 8765


class CaptureHandler(BaseHTTPRequestHandler):
    def send_json(self, status_code: int, payload: dict):
        encoded = json.dumps(payload).encode("utf-8")

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def read_payload(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        return json.loads(body.decode("utf-8"))

    def handle_snapshot_capture(self, payload: dict):
        title = payload["title"]
        conversation = payload["conversation"]

        if not isinstance(title, str) or not isinstance(conversation, str):
            raise ValueError("title and conversation must be strings")

        source = payload.get("source", "unknown")
        capture_type = payload.get("capture_type", "unknown")
        encoding = payload.get("encoding", "utf-8")
        instance_id = payload.get("instance_id")
        conversation_id = payload.get("conversation_id")

        if not isinstance(source, str):
            raise ValueError("source must be a string")

        if not isinstance(capture_type, str):
            raise ValueError("capture_type must be a string")

        if encoding is not None and not isinstance(encoding, str):
            raise ValueError("encoding must be a string or null")

        if instance_id is not None and not isinstance(instance_id, str):
            raise ValueError("instance_id must be a string or null")

        if conversation_id is not None and not isinstance(conversation_id, str):
            raise ValueError("conversation_id must be a string or null")

        metadata = ingest_bytes(
            conversation.encode("utf-8"),
            title,
            source=source,
            capture_type=capture_type,
            encoding=encoding,
            instance_id=instance_id,
            conversation_id=conversation_id,
        )

        self.send_json(
            200,
            {
                "returncode": 0,
                "archive_id": metadata["archive_id"],
                "sha256": metadata["sha256"],
                "source": metadata["ingest_method"],
                "capture_type": metadata["capture_type"],
                "instance_id": metadata["instance_id"],
                "conversation_id": metadata["conversation_id"],
            },
        )

    def handle_message_capture(self, payload: dict):
        title = payload["title"]
        conversation_id = payload["conversation_id"]
        message_id = payload["message_id"]
        role = payload["role"]
        text = payload["text"]

        model_slug = payload.get("model_slug")
        instance_id = payload.get("instance_id")

        for name, value in {
            "title": title,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "role": role,
            "text": text,
        }.items():
            if not isinstance(value, str):
                raise ValueError(f"{name} must be a string")

        if model_slug is not None and not isinstance(model_slug, str):
            raise ValueError("model_slug must be a string or null")

        if instance_id is not None and not isinstance(instance_id, str):
            raise ValueError("instance_id must be a string or null")

        message_record = {
            "schema_version": 1,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "role": role,
            "model_slug": model_slug,
            "text": text,
        }

        raw_bytes = (
            json.dumps(
                message_record,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")

        metadata = ingest_bytes(
            raw_bytes,
            f"{title} [{role} message]",
            source="browser_live",
            capture_type="message_state",
            encoding="utf-8",
            instance_id=instance_id,
            conversation_id=conversation_id,
        )

        self.send_json(
            200,
            {
                "returncode": 0,
                "archive_id": metadata["archive_id"],
                "sha256": metadata["sha256"],
                "source": metadata["ingest_method"],
                "capture_type": metadata["capture_type"],
                "instance_id": metadata["instance_id"],
                "conversation_id": metadata["conversation_id"],
                "message_id": message_id,
            },
        )

    def do_POST(self):
        try:
            payload = self.read_payload()

            if self.path == "/capture":
                self.handle_snapshot_capture(payload)
                return

            if self.path == "/capture-message":
                self.handle_message_capture(payload)
                return

            self.send_json(404, {"error": "Not found"})

        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            self.send_json(400, {"error": str(exc)})

        except Exception as exc:
            self.send_json(
                500,
                {"error": f"Capture failed: {exc}"},
            )

    def log_message(self, format, *args):
        return


def main():
    server = HTTPServer((HOST, PORT), CaptureHandler)

    print(
        f"Fawkes capture receiver listening on "
        f"http://{HOST}:{PORT}"
    )
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print("Capture receiver stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
