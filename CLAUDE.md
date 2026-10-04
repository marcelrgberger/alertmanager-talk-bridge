# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Webhook bridge that forwards Prometheus Alertmanager notifications to Nextcloud Talk rooms. Single-file Python application (`bridge.py`) using only stdlib `http.server` + `requests`.

## Architecture

`bridge.py` contains the entire application:
- **Config**: Environment variables loaded at module level (`TALK_URL`, `TALK_TOKEN`, `TALK_USER`, `TALK_PASSWORD`, `PORT`)
- **`build_message()`**: Bundles all alerts of one webhook payload into one human-readable message with severity emojis
- **`send_to_talk()`**: Posts the message to the Nextcloud Talk OCS API and returns `DELIVERED`, `RETRY` (Talk 5xx/408/429, network error) or `FAILED` (other 4xx)
- **`Handler`** (BaseHTTPRequestHandler): `POST /` answers `200` / `503` / `424` per outcome, so Alertmanager retries only what a retry can fix; `GET /` returns health check
- No framework, no routing library — raw `ThreadingHTTPServer`
- Log contract: `ok=False` is logged only for a lost message (platform-ops Cluster Watch greps for it); a retryable failure logs `deferred`

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

- Tests: `python -m unittest discover -s tests -v` (fake Talk server, no extra dependencies); CI runs them before the image build
- No linter/formatter configured
- Single dependency: `requests>=2.31,<3`
- Alertmanager webhook format: `{"alerts": [{"status": "firing|resolved", "labels": {...}, "annotations": {...}}]}`
- Nextcloud Talk API endpoint pattern: `/ocs/v2.php/apps/spreed/api/v1/chat/{token}`
