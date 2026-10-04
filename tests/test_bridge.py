"""Delivery semantics of the bridge against a fake Nextcloud Talk.

Alertmanager retries a webhook on 5xx and treats 4xx as final. The bridge must
answer 200 only when Talk accepted the message, 503 when Talk failed in a way
a retry can fix, and 424 when it cannot.
"""

import http.client
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("TALK_TOKEN", "room")
os.environ.setdefault("TALK_USER", "bot")
os.environ.setdefault("TALK_PASSWORD", "secret")


class FakeTalk(BaseHTTPRequestHandler):
    statuses = []  # status codes to answer with, one per request; last one repeats
    received = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        FakeTalk.received.append(json.loads(body))
        status = FakeTalk.statuses.pop(0) if len(FakeTalk.statuses) > 1 else FakeTalk.statuses[0]
        self.send_response(status)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


def serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


TALK = serve(FakeTalk)
os.environ["TALK_URL"] = f"http://127.0.0.1:{TALK.server_address[1]}"

import bridge  # noqa: E402  (needs the environment above)

BRIDGE = serve(bridge.Handler)

PAYLOAD = {"alerts": [{"status": "firing",
                       "labels": {"alertname": "NodeNotReady", "severity": "critical"},
                       "annotations": {"summary": "node down"}}]}


def post(body):
    conn = http.client.HTTPConnection("127.0.0.1", BRIDGE.server_address[1], timeout=15)
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    conn.request("POST", "/", body=raw, headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    resp.read()
    return resp.status


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        FakeTalk.received = []

    def answer(self, *statuses):
        FakeTalk.statuses = list(statuses)

    def test_delivered_message_answers_200(self):
        self.answer(201)
        self.assertEqual(post(PAYLOAD), 200)
        self.assertEqual(len(FakeTalk.received), 1)
        self.assertIn("NodeNotReady", FakeTalk.received[0]["message"])

    def test_talk_server_error_asks_alertmanager_to_retry(self):
        for status in (500, 502, 503, 504):
            with self.subTest(talk=status):
                self.answer(status)
                self.assertEqual(post(PAYLOAD), 503)

    def test_rate_limit_and_timeout_status_are_retryable(self):
        for status in (408, 429):
            with self.subTest(talk=status):
                self.answer(status)
                self.assertEqual(post(PAYLOAD), 503)

    def test_permanent_talk_error_is_final(self):
        for status in (400, 401, 403, 404, 413):
            with self.subTest(talk=status):
                self.answer(status)
                self.assertEqual(post(PAYLOAD), 424)

    def test_unreachable_talk_is_retryable(self):
        original = bridge.TALK_URL
        bridge.TALK_URL = "http://127.0.0.1:9"  # discard port, connection refused
        try:
            self.assertEqual(post(PAYLOAD), 503)
        finally:
            bridge.TALK_URL = original

    def test_retry_after_failure_delivers(self):
        self.answer(502, 201)
        self.assertEqual(post(PAYLOAD), 503)
        self.assertEqual(post(PAYLOAD), 200)
        self.assertEqual(len(FakeTalk.received), 2)

    def test_empty_payload_is_accepted_without_talk_call(self):
        self.answer(201)
        self.assertEqual(post({"alerts": []}), 200)
        self.assertEqual(FakeTalk.received, [])

    def test_invalid_json_is_rejected(self):
        self.assertEqual(post(b"not json"), 400)


class LogTest(unittest.TestCase):
    """Cluster Watch greps the log for ok=False: it must mean a lost message."""

    def run_with(self, *statuses):
        FakeTalk.statuses = list(statuses)
        with self.assertLogs("bridge", level="INFO") as logs:
            post(PAYLOAD)
        return "\n".join(logs.output)

    def test_retryable_failure_is_not_logged_as_lost(self):
        out = self.run_with(502)
        self.assertNotIn("ok=False", out)
        self.assertIn("deferred", out)

    def test_final_failure_is_logged_as_lost(self):
        self.assertIn("ok=False", self.run_with(401))

    def test_delivery_is_logged_as_ok(self):
        self.assertIn("ok=True", self.run_with(201))


if __name__ == "__main__":
    unittest.main()
