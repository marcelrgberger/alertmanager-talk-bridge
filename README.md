# alertmanager-talk-bridge

Lightweight webhook bridge that forwards [Prometheus Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/) notifications to [Nextcloud Talk](https://nextcloud.com/talk/) rooms.

## How it works

```
Alertmanager → POST /alerts → bridge → Nextcloud Talk API → Chat message
```

The bridge receives Alertmanager webhook payloads, formats each alert into a readable message with severity emojis, and posts it to a configured Nextcloud Talk room.

### Alert format

```
🔴 CRITICAL: KubePodCrashLooping
Pod default/my-app is crash looping (restartCount > 5)
Namespace: default

✅ RESOLVED: KubePodCrashLooping
Pod default/my-app is crash looping (restartCount > 5)
Namespace: default
```

## Deployment

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `TALK_URL` | Yes | Nextcloud base URL (e.g. `https://cloud.example.com`) |
| `TALK_TOKEN` | Yes | Talk room token (from room URL) |
| `TALK_USER` | Yes | Nextcloud username or bot account |
| `TALK_PASSWORD` | Yes | App password for the user |
| `PORT` | No | Listen port (default: `8080`) |

### Kubernetes

Deploy as a sidecar or standalone service in your monitoring namespace, then configure Alertmanager to send webhooks to it:

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
  ghcr.io/marcelrgberger/alertmanager-talk-bridge:latest
```

## Health check

```
GET / → 200 "healthy"
```

## License

MIT
