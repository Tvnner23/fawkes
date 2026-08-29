from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
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

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".txt",
                delete=False,
            ) as temp_file:
                temp_file.write(conversation)
                temp_path = Path(temp_file.name)

            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SRC / "capture_conversation.py"),
                        str(temp_path),
                        title,
                    ],
                    capture_output=True,
                    text=True,
                )
            finally:
                temp_path.unlink(missing_ok=True)

            response = {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

            encoded = json.dumps(response).encode("utf-8")

            self.send_response(200 if result.returncode == 0 else 500)
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

    def log_message(self, format, *args):
        return


def main():
    server = HTTPServer((HOST, PORT), CaptureHandler)

    print(f"Fawkes capture receiver listening on http://{HOST}:{PORT}")
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
