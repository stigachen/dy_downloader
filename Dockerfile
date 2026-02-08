FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY douyin_core.py cli.py server.py ./

RUN useradd --create-home appuser \
    && mkdir -p /tmp/douyin_downloads \
    && chown appuser:appuser /tmp/douyin_downloads

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

CMD ["python", "server.py"]
