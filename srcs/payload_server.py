import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

import bs4

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8089

OTPS = {}


class PayloadHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._send_json(200, {"ok": True, "message": "Payload received"})

    def do_POST(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length) if content_length > 0 else b""
            payload = json.loads(raw_body.decode("utf-8"))

            content = payload.get("content")
            from_email = payload.get("from")
            to_email = payload.get("to")

            soup = bs4.BeautifulSoup(content or "", "html.parser")
            text = soup.get_text(" ", strip=True)
            match = re.search(r"\b(\d{6})\b", text)
            otp = match.group(1) if match else None

            if otp and to_email:
                OTPS[to_email] = otp

            print("=== Incoming payload ===")
            print(f"from: {from_email}")
            print(f"to: {to_email}")
            print(f"otp: {otp}")
            print(f"stored_for_to_email: {to_email in OTPS if to_email else False}")
            print("========================")

            self._send_json(200, {"ok": True, "message": "Payload received"})
        except Exception as e:
            print(f"Error processing payload: {e}")
            self._send_json(500, {"ok": False, "error": str(e)})


def run_payload_http_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    server = HTTPServer((host, port), PayloadHandler)
    print(f"[payload-server] listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[payload-server] shutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    run_payload_http_server()
