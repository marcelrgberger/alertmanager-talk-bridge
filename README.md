# alertmanager-talk-bridge

Lightweight webhook bridge that forwards [Prometheus Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/) notifications to [Nextcloud Talk](https://nextcloud.com/talk/) rooms.

## How it works

```
Alertmanager → POST /alerts → bridge → Nextcloud Talk API → 1 chat message per webhook payload
```

The bridge receives Alertmanager webhook payloads and consolidates **all alerts in a single payload** into **one** Talk message — grouped by status (firing/resolved) and alertname, with summary lines per alert and `+N more` overflow. A burst of 159 alerts produces 1 notification, not 159.

### Message format

```
🔴 2 alert(s) firing (critical)

**PodCrashLooping** × 1 — monitoring
- `pod=alertmanager-talk-bridge-xxx` — Pod is crash looping

**TargetDown** × 1 — doku-ai
- `service=doku-ai-api-service` — One or more targets are unreachable.

✅ 159 alert(s) resolved

**KafkaUnderReplicatedPartitions** × 159 — monitoring
- `topic=sommelio.image-uploaded` — Kafka has under-replicated partitions
- `topic=sommelio.extraction-completed` — Kafka has under-replicated partitions
- `topic=dokuai-report-status-update` — Kafka has under-replicated partitions
- `topic=dokuai-report-status` — Kafka has under-replicated partitions
- `topic=dokuai-process-image-files` — Kafka has under-replicated partitions
- … +154 more
```

### Behaviour

- **Bundling:** the entire webhook payload becomes one Talk message. Alertmanager's `group_by` / `group_interval` / `repeat_interval` decide how often a payload arrives — the bridge does not throttle further.
- **Detail rows:** for each alertname the first `MAX_DETAILS` (default 5) alerts are shown with a distinguishing label (`topic`, `partition`, `pod`, `instance`, `service`, `job`, `container` — first that matches) plus `summary`/`description` (truncated to 120 chars). Remaining alerts collapse into `… +N more`.
- **Severity:** the firing section header shows the highest severity present (`critical` > `warning` > `info`).
- **Threading:** uses `ThreadingHTTPServer` so the `GET /` health endpoint responds immediately even while a Talk POST is in flight. Liveness/readiness probes are never blocked by webhook handling.
- **Delivery and retries:** the webhook answer tells Alertmanager whether the message arrived. Alertmanager retries a webhook on 5xx (exponential backoff, for up to its `group_interval`) and treats 4xx as final.

  | Talk answer | Bridge answers | Alertmanager | Log line |
  |---|---|---|---|
  | 2xx | `200` | done | `… ok=True` |
  | 5xx, 408, 429, connection error or timeout | `503` | retries | `… deferred, answering 503 so the sender retries` |
  | any other 4xx (credentials, room token, message too large) | `424` | stops, counts `alertmanager_notifications_failed_total` | `… ok=False, answering 424, retrying cannot help` |

  `ok=False` therefore always means a lost message; monitoring can grep for it. A message lost after Alertmanager gave up retrying shows in `alertmanager_notifications_failed_total{integration="webhook"}`. A retry after a timeout can post a message twice if Talk stored it but the answer never arrived.

## Deployment

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TALK_URL` | Yes | — | Nextcloud base URL (e.g. `https://cloud.example.com`) |
| `TALK_TOKEN` | Yes | — | Talk room token (from room URL) |
| `TALK_USER` | Yes | — | Nextcloud username or bot account |
| `TALK_PASSWORD` | Yes | — | App password for the user |
| `PORT` | No | `8080` | Listen port |
| `MAX_DETAILS` | No | `5` | How many detail rows per alertname before collapsing into `+N more` |

### Kubernetes

Deploy as a service in your monitoring namespace, then configure Alertmanager to send webhooks to it:

```yaml
# Alertmanager config
receivers:
  - name: talk
    webhook_configs:
      - url: "http://alertmanager-talk-bridge:8080"
        send_resolved: true
```

### Docker

```bash
docker run -d \
  -e TALK_URL=https://cloud.example.com \
  -e TALK_TOKEN=abc123 \
  -e TALK_USER=alertbot \
  -e TALK_PASSWORD=app-password \
  -p 8080:8080 \
  ghcr.io/marcelrgberger/internal-docker-repo/alertmanager-talk-bridge:latest
```

## Health check

```
GET / → 200 "healthy"
```

Always non-blocking. Safe for low-timeout liveness probes.

## Tests

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

`tests/test_bridge.py` runs the bridge against a fake Talk server and checks the webhook status and log line for every Talk outcome. CI runs it before building the image.

## Versioning

| Tag | Notes |
|---|---|
| `1.3.0` | Answer `503` on retryable Talk failures so Alertmanager retries, `424` on permanent ones; `ok=False` only for lost messages. Until 1.2.0 the bridge answered `200` even when Talk rejected the message, so a Nextcloud `502` silently lost the alert. |
| `1.2.0` | Bundle alerts per webhook into one Talk message; `ThreadingHTTPServer` so health endpoint never blocks. |
| `1.1.0` | Posted each alert in a payload as a separate Talk message — caused spam loops on bursts and blocked the health endpoint (do not use). |

## License

MIT
