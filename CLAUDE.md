# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Webhook bridge that forwards Prometheus Alertmanager notifications to Nextcloud Talk rooms. Single-file Python application (`bridge.py`) using only stdlib `http.server` + `requests`.

## Architecture

`bridge.py` contains the entire application:
- **Config**: Environment variables loaded at module level (`TALK_URL`, `TALK_TOKEN`, `TALK_USER`, `TALK_PASSWORD`, `PORT`)
- **`format_alert()`**: Converts Alertmanager alert JSON → human-readable message with severity emojis
- **`send_to_talk()`**: Posts formatted message to Nextcloud Talk OCS API
- **`Handler`** (BaseHTTPRequestHandler): `POST /` receives Alertmanager webhook payload, `GET /` returns health check
- No framework, no routing library — raw `HTTPServer`

## Running Locally

```bash
pip install -r requirements.txt

TALK_URL=https://cloud.example.com \
TALK_TOKEN=roomtoken \
TALK_USER=botuser \
TALK_PASSWORD=apppassword \
python bridge.py
```

## Building

```bash
docker build -t alertmanager-talk-bridge .
```

Image: `python:3.13-alpine`, runs as `nobody`.

## CI/CD

GitHub Actions workflow (`.github/workflows/build.yaml`): builds Docker image and pushes to `ghcr.io` on main branch pushes and semver tags. PRs build but don't push.

## Key Details

- No test suite exists yet
- No linter/formatter configured
- Single dependency: `requests>=2.31,<3`
- Alertmanager webhook format: `{"alerts": [{"status": "firing|resolved", "labels": {...}, "annotations": {...}}]}`
- Nextcloud Talk API endpoint pattern: `/ocs/v2.php/apps/spreed/api/v1/chat/{token}`
