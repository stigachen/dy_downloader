# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

dy_downloader is a Douyin (Chinese TikTok) watermark-free video downloader. It provides both a CLI tool and a FastAPI web server with an embedded web UI. Python 3.10+, async-first using `httpx`.

## Commands

```bash
# Install dependencies (uv preferred, pip also works)
uv pip install -r requirements.txt
uv pip install -r requirements-dev.txt  # for testing (pytest, pytest-asyncio)

# CLI usage
python cli.py "分享文本或链接"
python cli.py "https://v.douyin.com/xxx/" -o ./videos
python cli.py "https://v.douyin.com/xxx/" --parse-only --json

# Web server (default: http://0.0.0.0:8000)
python server.py
python server.py --port 8080 --host 127.0.0.1

# Testing
pytest tests/ -v                        # all tests
pytest tests/test_api.py -v             # single test file
pytest tests/test_api.py::test_parse_success -v  # single test
pytest -k "test_extract" -v             # pattern match

# Docker
docker build -t stigachen/dy-downloader:latest .
docker run -d -p 8000:8000 --name dy-downloader stigachen/dy-downloader:latest

# Docker multi-arch build & push
docker buildx build --platform linux/amd64,linux/arm64 \
  -t stigachen/dy-downloader:latest --push .
```

## Architecture

Three-module design with shared core logic:

- **douyin_core.py** — Core extraction and download logic. Fetches the iesdouyin.com sharing page using a mobile User-Agent, extracts `_ROUTER_DATA` JSON from the HTML, converts watermarked (`/playwm/`) URLs to watermark-free (`/play/`) URLs, and generates multiple quality options (default HEVC, 1080p H.264, 720p H.264). All I/O is async using `httpx`. Handles both video posts and image carousel posts (`aweme_type == 2`).
- **cli.py** — Argparse-based CLI. Supports parse-only mode (`--parse-only`) and JSON output (`--json`).
- **server.py** — FastAPI web server with REST API (`POST /api/parse`, `POST /api/download`, `GET /api/proxy`) and an embedded dark-themed single-page HTML frontend. The proxy endpoint resolves CDN 403 issues. Downloaded files are auto-cleaned via `BackgroundTask`. Image posts return a zip archive when multiple images.
- **Dockerfile** — Multi-arch Docker image based on `python:3.12-slim`. Runs as non-root user (`appuser`). Includes HEALTHCHECK. Published to Docker Hub as `stigachen/dy-downloader`.

Data flow: share text → `extract_url()` regex → `fetch_video_detail()` HTTP request → extract `_ROUTER_DATA` → `extract_video_urls()` → try multiple quality URLs until one succeeds → stream download.

## Key Implementation Details

- **Content type detection**: `aweme_type == 2` means image carousel post; anything else is a video post. This field comes from the `_ROUTER_DATA` detail dict.
- **Video URL construction**: Primary URLs use `https://aweme.snssdk.com/aweme/v1/play/?video_id={uri}&ratio={quality}` with quality values `default`, `1080p`, `720p`. Fallback converts `/playwm/` to `/play/` in existing URLs.
- **Error conventions**: Core functions raise `ValueError` for bad input (no URL found, invalid video ID) and `RuntimeError` for fetch/parse failures (missing `_ROUTER_DATA`, video unavailable, all download URLs failed).
- **Mobile User-Agent is required**: Non-mobile UA gets redirected to app download page instead of the sharing page with metadata.
- **Server temp files**: Downloads go to `/tmp/douyin_downloads` and are auto-cleaned via FastAPI `BackgroundTask`.
- **SSRF protection on proxy endpoint**: `GET /api/proxy` validates URLs against a whitelist of Douyin-related CDN domains (e.g. `douyinvod.com`, `snssdk.com`, `bytedance.com`) and rejects non-HTTP schemes and internal IPs.
- **`extract_video_urls` return shape**: Returns a dict with keys `type` (`"video"` or `"images"`), `title`, `author`, `aweme_id`, `video_urls` (list), `image_urls` (list), `cover_url`, and `duration` (seconds).

## Testing

Tests use `pytest` with `asyncio_mode = auto` (configured in `pytest.ini`). All async tests run automatically without markers. Tests mock HTTP calls via `unittest.mock.patch` and `AsyncMock` — no network access required. Shared fixtures are in `tests/conftest.py` (`sample_detail`, `sample_detail_minimal`, `sample_image_detail`, `sample_router_data_html`).
