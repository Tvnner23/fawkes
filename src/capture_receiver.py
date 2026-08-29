from http.server import BaseHTTPRequestHandler, HTTPServer
import json

from ingest import ingest_bytes


HOST = "127.0.0.1"
PORT = 8765


class CaptureHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/capture":
            self.send_response(404)
            self.end_headers()
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            payload = json.loads(body.decode("utf-8"))

            title = payload["title"]
            conversation = payload["conversation"]

            if not isinstance(title, str) or not isinstance(conversation, str):
                raise ValueError("title and conversation must be strings")

            metadata = ingest_bytes(
                conversation.encode("utf-8"),
                title,
                source="browser_live",
                capture_type="near_live",
                encoding="utf-8",
            )

            response = {
                "returncode": 0,
                "archive_id": metadata["archive_id"],
                "stdout": (
                    f"Archived: {metadata['archive_id']}\n"
                    f"SHA-256: {metadata['sha256']}\n"
                ),
                "stderr": "",
            }

            encoded = json.dumps(response).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            encoded = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        except Exception as exc:
            encoded = json.dumps({
                "error": f"Capture failed: {exc}"
            }).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

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
