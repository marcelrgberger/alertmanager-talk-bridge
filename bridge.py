"""Alertmanager → Nextcloud Talk webhook bridge.

Bundles all alerts from a webhook payload into a single Talk message so a burst
of N alerts produces 1 notification instead of N. Uses ThreadingHTTPServer so
the health endpoint is never blocked by an in-flight Talk POST.
"""

import json
import logging
import os
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

TALK_URL = os.environ["TALK_URL"]
TALK_TOKEN = os.environ["TALK_TOKEN"]
TALK_USER = os.environ["TALK_USER"]
TALK_PASSWORD = os.environ["TALK_PASSWORD"]
PORT = int(os.environ.get("PORT", "8080"))
MAX_DETAILS = int(os.environ.get("MAX_DETAILS", "5"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bridge")

SEVERITY_EMOJI = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}
DETAIL_LABEL_PRIORITY = ("topic", "partition", "pod", "instance", "service", "job", "container")


def alert_detail_line(alert: dict) -> str:
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    parts = []
    for key in DETAIL_LABEL_PRIORITY:
        if labels.get(key):
            parts.append(f"`{key}={labels[key]}`")
            break
    summary = annotations.get("summary") or annotations.get("description") or ""
    if summary:
        parts.append(summary[:120])
    return "- " + " — ".join(parts) if parts else "- (no details)"


def top_severity(alerts: list) -> str:
    best = "info"
    for a in alerts:
        sev = a.get("labels", {}).get("severity", "info")
        if SEVERITY_RANK.get(sev, 9) < SEVERITY_RANK.get(best, 9):
            best = sev
    return best


def build_message(payload: dict) -> str:
    alerts = payload.get("alerts", [])
    if not alerts:
        return ""

    by_status = defaultdict(list)
    for a in alerts:
        by_status[a.get("status", "firing")].append(a)

    sections = []
    for status in ("firing", "resolved"):
        group = by_status.get(status, [])
        if not group:
            continue

        if status == "resolved":
            sections.append(f"✅ {len(group)} alert(s) resolved")
        else:
            sev = top_severity(group)
            emoji = SEVERITY_EMOJI.get(sev, "⚪")
            sections.append(f"{emoji} {len(group)} alert(s) firing ({sev})")

        by_name = defaultdict(list)
        for a in group:
            by_name[a.get("labels", {}).get("alertname", "Unknown")].append(a)

        for name, items in sorted(by_name.items()):
            namespaces = sorted({i.get("labels", {}).get("namespace") for i in items if i.get("labels", {}).get("namespace")})
            ns_str = f" — {', '.join(namespaces)}" if namespaces else ""
            sections.append(f"\n**{name}** × {len(items)}{ns_str}")
            for item in items[:MAX_DETAILS]:
                sections.append(alert_detail_line(item))
            if len(items) > MAX_DETAILS:
                sections.append(f"- … +{len(items) - MAX_DETAILS} more")
        sections.append("")

    return "\n".join(sections).strip()


def send_to_talk(message: str) -> bool:
    url = f"{TALK_URL}/ocs/v2.php/apps/spreed/api/v1/chat/{TALK_TOKEN}"
    try:
        resp = requests.post(
            url,
            auth=(TALK_USER, TALK_PASSWORD),
            headers={"OCS-APIRequest": "true", "Accept": "application/json"},
            json={"message": message, "actorDisplayName": "AlertManager"},
            timeout=10,
        )
    except requests.RequestException as exc:
        log.error("Talk API request failed: %s", exc)
        return False
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

        message = build_message(payload)
        if message:
            ok = send_to_talk(message)
            log.info("Bundled %d alert(s) into 1 Talk message ok=%s", len(alerts), ok)
        else:
            log.info("Empty payload, skipping")

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):
        try:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"healthy")
        except BrokenPipeError:
            pass

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    log.info("Starting bridge on port %d → %s room %s", PORT, TALK_URL, TALK_TOKEN)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
