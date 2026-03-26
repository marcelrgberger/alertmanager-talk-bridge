"""Alertmanager → Nextcloud Talk webhook bridge."""

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

TALK_URL = os.environ["TALK_URL"]  # https://cloud.example.com
TALK_TOKEN = os.environ["TALK_TOKEN"]  # Room token
TALK_USER = os.environ["TALK_USER"]  # Bot or user account
TALK_PASSWORD = os.environ["TALK_PASSWORD"]  # App password
PORT = int(os.environ.get("PORT", "8080"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bridge")

SEVERITY_EMOJI = {"critical": "🔴", "warning": "🟡", "info": "🔵"}


def format_alert(alert: dict) -> str:
    status = alert.get("status", "unknown")
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    name = labels.get("alertname", "Unknown")
    severity = labels.get("severity", "info")
    namespace = labels.get("namespace", "")
    emoji = SEVERITY_EMOJI.get(severity, "⚪")

    if status == "resolved":
        header = f"✅ RESOLVED: {name}"
    else:
        header = f"{emoji} {severity.upper()}: {name}"

    lines = [header]
    if annotations.get("summary"):
        lines.append(annotations["summary"])
    if annotations.get("description"):
        lines.append(annotations["description"])
    if namespace:
        lines.append(f"Namespace: {namespace}")

    return "\n".join(lines)


def send_to_talk(message: str) -> bool:
    url = f"{TALK_URL}/ocs/v2.php/apps/spreed/api/v1/chat/{TALK_TOKEN}"
    resp = requests.post(
        url,
        auth=(TALK_USER, TALK_PASSWORD),
        headers={"OCS-APIRequest": "true", "Accept": "application/json"},
        json={"message": message, "actorDisplayName": "AlertManager"},
        timeout=10,
    )
    if resp.status_code == 201:
        return True
    log.error("Talk API error %d: %s", resp.status_code, resp.text[:200])
    return False


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        alerts = payload.get("alerts", [])
        log.info("Received %d alert(s)", len(alerts))

        for alert in alerts:
            message = format_alert(alert)
            ok = send_to_talk(message)
            log.info("Sent alert=%s status=%s ok=%s", alert.get("labels", {}).get("alertname"), alert.get("status"), ok)

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"healthy")

    def log_message(self, format, *args):
        pass  # Suppress default access logs


if __name__ == "__main__":
    log.info("Starting bridge on port %d → %s room %s", PORT, TALK_URL, TALK_TOKEN)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
