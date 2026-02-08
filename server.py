"""
抖音无水印视频下载 - Web 服务

启动:
    python server.py
    python server.py --port 8080 --host 0.0.0.0

API:
    POST /api/parse     - 解析视频信息
    POST /api/download  - 解析并下载视频，返回文件
    GET  /              - Web 界面
"""

import os
from urllib.parse import quote
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

from douyin_core import (
    extract_url,
    fetch_video_detail,
    extract_video_urls,
    download_video,
    sanitize_filename,
    MOBILE_UA,
)

app = FastAPI(title="抖音无水印下载", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ParseRequest(BaseModel):
    share_text: str


@app.post("/api/parse")
async def api_parse(req: ParseRequest):
    """解析视频信息，返回无水印视频地址"""
    try:
        url = extract_url(req.share_text)
        detail = await fetch_video_detail(url)
        info = extract_video_urls(detail)
        return {"success": True, "data": info}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/download")
async def api_download(req: ParseRequest):
    """解析并下载视频，返回视频文件"""
    try:
        url = extract_url(req.share_text)
        detail = await fetch_video_detail(url)
        info = extract_video_urls(detail)

        if not info["video_urls"]:
            raise HTTPException(status_code=404, detail="未找到视频地址")

        # 下载到临时目录
        tmp_dir = "/tmp/douyin_downloads"
        os.makedirs(tmp_dir, exist_ok=True)
        filename = sanitize_filename(f"{info['author']}_{info['title']}") + ".mp4"
        save_path = os.path.join(tmp_dir, filename)

        last_error = None
        for video_url in info["video_urls"]:
            try:
                await download_video(video_url, save_path)
                return FileResponse(
                    save_path,
                    media_type="video/mp4",
                    filename=filename,
                    background=BackgroundTask(os.remove, save_path),
                )
            except Exception as e:
                last_error = e
                continue

        raise HTTPException(status_code=500, detail=f"下载失败: {last_error}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/proxy")
async def api_proxy(
    url: str = Query(..., description="视频 URL"),
    filename: str = Query(None, description="下载文件名"),
):
    """代理视频请求，解决 CDN 403 问题"""
    headers = {
        "User-Agent": MOBILE_UA,
        "Referer": "https://www.douyin.com/",
    }

    async def stream_video():
        async with httpx.AsyncClient(
            headers=headers,
            follow_redirects=True,
            timeout=120,
        ) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    yield chunk

    try:
        # 先发一个 HEAD 请求获取 content-type 和 content-length
        async with httpx.AsyncClient(
            headers=headers,
            follow_redirects=True,
            timeout=30,
        ) as client:
            head_resp = await client.head(url)
            head_resp.raise_for_status()

        resp_headers = {
            "Content-Type": head_resp.headers.get("content-type", "video/mp4"),
        }
        if "content-length" in head_resp.headers:
            resp_headers["Content-Length"] = head_resp.headers["content-length"]
        if filename:
            resp_headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"

        return StreamingResponse(stream_video(), headers=resp_headers)

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"代理请求失败: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"代理请求失败: {e}")


# ==================== Web 前端 ====================

INDEX_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>抖音无水印下载</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0f0f0f;
            color: #e0e0e0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            width: 100%;
            max-width: 600px;
            padding: 20px;
        }
        h1 {
            text-align: center;
            font-size: 24px;
            margin-bottom: 8px;
            color: #fff;
        }
        .subtitle {
            text-align: center;
            color: #888;
            font-size: 14px;
            margin-bottom: 32px;
        }
        .input-group {
            margin-bottom: 16px;
        }
        label {
            display: block;
            font-size: 13px;
            color: #aaa;
            margin-bottom: 6px;
        }
        textarea {
            width: 100%;
            padding: 12px;
            border: 1px solid #333;
            border-radius: 8px;
            background: #1a1a1a;
            color: #fff;
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
            height: 100px;
            resize: vertical;
        }
        textarea:focus {
            border-color: #fe2c55;
        }
        .btn-row {
            display: flex;
            gap: 12px;
            margin-top: 20px;
        }
        button {
            flex: 1;
            padding: 12px;
            border: none;
            border-radius: 8px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: opacity 0.2s;
        }
        button:hover { opacity: 0.85; }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-parse {
            background: #333;
            color: #fff;
        }
        .btn-download {
            background: #fe2c55;
            color: #fff;
        }
        .result {
            margin-top: 24px;
            padding: 16px;
            background: #1a1a1a;
            border-radius: 8px;
            border: 1px solid #333;
            display: none;
        }
        .result.show { display: block; }
        .result h3 {
            font-size: 15px;
            margin-bottom: 12px;
            color: #fff;
        }
        .info-row {
            font-size: 13px;
            margin-bottom: 6px;
            color: #ccc;
        }
        .info-row span { color: #888; }
        .video-link {
            display: block;
            margin-top: 8px;
            padding: 8px 12px;
            background: #252525;
            border-radius: 6px;
            font-size: 12px;
            word-break: break-all;
            color: #4ea6f5;
            text-decoration: none;
        }
        .video-link:hover { background: #303030; }
        .error {
            margin-top: 16px;
            padding: 12px;
            background: #2a1215;
            color: #ff6b6b;
            border-radius: 8px;
            font-size: 13px;
            display: none;
        }
        .error.show { display: block; }
        .loading {
            text-align: center;
            padding: 20px;
            color: #888;
            display: none;
        }
        .loading.show { display: block; }
    </style>
</head>
<body>
    <div class="container">
        <h1>抖音无水印下载</h1>
        <p class="subtitle">粘贴抖音分享文本或链接，获取无水印视频</p>

        <div class="input-group">
            <label>分享文本 / 链接</label>
            <textarea id="shareText" placeholder="粘贴抖音分享内容，例如：&#10;2.56 复制打开抖音，看看... https://v.douyin.com/xxx/"></textarea>
        </div>

        <div class="btn-row">
            <button class="btn-parse" id="btnParse" onclick="parseVideo()">解析视频</button>
            <button class="btn-download" id="btnDownload" onclick="downloadVideo()">解析并下载</button>
        </div>

        <div class="loading" id="loading">解析中...</div>
        <div class="error" id="error"></div>
        <div class="result" id="result"></div>
    </div>

    <script>
        async function parseVideo() {
            const shareText = document.getElementById('shareText').value.trim();
            if (!shareText) return;

            setLoading(true);
            hideError();
            hideResult();

            try {
                const resp = await fetch('/api/parse', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({share_text: shareText}),
                });

                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.detail || '解析失败');
                }

                const json = await resp.json();
                showResult(json.data);
            } catch (e) {
                showError(e.message);
            } finally {
                setLoading(false);
            }
        }

        async function downloadVideo() {
            const shareText = document.getElementById('shareText').value.trim();
            if (!shareText) return;

            setLoading(true);
            hideError();
            hideResult();

            try {
                const resp = await fetch('/api/download', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({share_text: shareText}),
                });

                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.detail || '下载失败');
                }

                const blob = await resp.blob();
                const disposition = resp.headers.get('content-disposition') || '';
                let filename = 'douyin_video.mp4';
                const match = disposition.match(/filename\\*?=(?:UTF-8'')?([^;]+)/i);
                if (match) filename = decodeURIComponent(match[1].replace(/"/g, ''));

                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = filename;
                a.click();
                URL.revokeObjectURL(a.href);
            } catch (e) {
                showError(e.message);
            } finally {
                setLoading(false);
            }
        }

        function showResult(data) {
            const el = document.getElementById('result');
            const filename = (data.author && data.title)
                ? (data.author + '_' + data.title).replace(/[\\\\/:*?"<>|]/g, '_') + '.mp4'
                : 'douyin_video.mp4';
            let videoLinks = '';
            (data.video_urls || []).forEach((u, i) => {
                const proxyUrl = '/api/proxy?url=' + encodeURIComponent(u) + '&filename=' + encodeURIComponent(filename);
                videoLinks += `<a class="video-link" href="${proxyUrl}" target="_blank" rel="noopener">[${i+1}] ${u}</a>`;
            });

            el.innerHTML = `
                <h3>${data.title || '未知标题'}</h3>
                <div class="info-row"><span>作者：</span>${data.author || '-'}</div>
                <div class="info-row"><span>视频ID：</span>${data.aweme_id || '-'}</div>
                <div class="info-row"><span>时长：</span>${data.duration || 0}s</div>
                <div class="info-row" style="margin-top:12px;"><span>无水印视频地址：</span></div>
                ${videoLinks}
            `;
            el.classList.add('show');
        }

        function showError(msg) {
            const el = document.getElementById('error');
            el.textContent = msg;
            el.classList.add('show');
        }
        function hideError() { document.getElementById('error').classList.remove('show'); }
        function hideResult() { document.getElementById('result').classList.remove('show'); }
        function setLoading(on) {
            document.getElementById('loading').classList.toggle('show', on);
            document.getElementById('btnParse').disabled = on;
            document.getElementById('btnDownload').disabled = on;
        }
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return INDEX_HTML


def start_server():
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="抖音无水印下载 Web 服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="端口 (默认: 8000)")
    args = parser.parse_args()

    print(f"启动服务: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    start_server()
