# dy_downloader

A Douyin (Chinese TikTok) watermark-free video downloader with both CLI and web interfaces.

## How It Works

1. Parses the Douyin share text or URL to extract the video link
2. Fetches the iesdouyin.com sharing page using a mobile User-Agent, which returns an HTML page containing video metadata in a `_ROUTER_DATA` JavaScript object
3. Extracts video URLs and converts watermarked paths (`/playwm/`) to watermark-free paths (`/play/`)
4. Generates multiple quality options (default HEVC, 1080p H.264, 720p H.264) and tries each until one succeeds

## Installation

```bash
# Create a virtual environment
uv venv

# Activate the virtual environment
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# Install dependencies
uv pip install -r requirements.txt
```

## Usage

### CLI

```bash
# Download a video from share text
python cli.py "分享文本或链接"

# Specify output directory
python cli.py "https://v.douyin.com/xxx/" -o ./videos

# Parse only (no download), output as JSON
python cli.py "https://v.douyin.com/xxx/" --parse-only --json
```

### Web Server

```bash
# Start server (default: http://0.0.0.0:8000, accessible from LAN)
python server.py

# Custom host and port
python server.py --host 0.0.0.0 --port 8080
```

The web server provides:

- A dark-themed web UI at the root URL
- `POST /api/parse` — Returns video metadata and direct download URLs
- `POST /api/download` — Returns the video file directly
- `GET /api/proxy` — Proxies video requests to resolve CDN 403 issues

## Project Structure

| File | Description |
|---|---|
| `douyin_core.py` | Core video extraction and download logic (async) |
| `cli.py` | Command-line interface |
| `server.py` | FastAPI web server with embedded frontend |
| `tests/` | Regression test suite |

## Testing

```bash
# Install test dependencies
uv pip install -r requirements-dev.txt

# Run all tests
pytest tests/ -v
```