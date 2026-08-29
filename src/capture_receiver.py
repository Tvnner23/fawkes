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

    def do_POST(self):
        if self.path != "/capture":
            self.send_json(404, {"error": "Not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            payload = json.loads(body.decode("utf-8"))

            title = payload["title"]
            conversation = payload["conversation"]

            if not isinstance(title, str) or not isinstance(conversation, str):
                raise ValueError("title and conversation must be strings")

            source = payload.get("source", "unknown")
            capture_type = payload.get("capture_type", "unknown")
            encoding = payload.get("encoding", "utf-8")

            if not isinstance(source, str):
                raise ValueError("source must be a string")

            if not isinstance(capture_type, str):
                raise ValueError("capture_type must be a string")

            if encoding is not None and not isinstance(encoding, str):
                raise ValueError("encoding must be a string or null")

            metadata = ingest_bytes(
                conversation.encode("utf-8"),
                title,
                source=source,
                capture_type=capture_type,
                encoding=encoding,
            )

            self.send_json(
                200,
                {
                    "returncode": 0,
                    "archive_id": metadata["archive_id"],
                    "sha256": metadata["sha256"],
                    "source": metadata["ingest_method"],
                    "capture_type": metadata["capture_type"],
                },
            )

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
