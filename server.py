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
import zipfile
import tempfile
import shutil
from urllib.parse import quote, urlparse
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
    """解析并下载视频/图片，返回文件"""
    try:
        url = extract_url(req.share_text)
        detail = await fetch_video_detail(url)
        info = extract_video_urls(detail)
        content_type = info.get("type", "video")

        tmp_dir = "/tmp/douyin_downloads"
        os.makedirs(tmp_dir, exist_ok=True)
        base_name = sanitize_filename(f"{info['author']}_{info['title']}")

        # 每个请求使用独立临时目录，避免并发请求间文件名冲突
        req_dir = tempfile.mkdtemp(dir=tmp_dir)

        if content_type == "images":
            # 图文帖：下载所有图片，打包为 zip
            if not info.get("image_urls"):
                shutil.rmtree(req_dir, ignore_errors=True)
                raise HTTPException(status_code=404, detail="未找到图片地址")

            saved = []
            for i, img_url in enumerate(info["image_urls"], 1):
                img_path = os.path.join(req_dir, f"{base_name}_{i}.webp")
                try:
                    await download_video(img_url, img_path)
                    saved.append(img_path)
                except Exception:
                    continue

            if not saved:
                shutil.rmtree(req_dir, ignore_errors=True)
                raise HTTPException(status_code=500, detail="所有图片下载失败")

            if len(saved) == 1:
                # 只有一张图片，直接返回
                filename = f"{base_name}.webp"
                return FileResponse(
                    saved[0],
                    media_type="image/webp",
                    filename=filename,
                    background=BackgroundTask(shutil.rmtree, req_dir, ignore_errors=True),
                )

            # 多张图片打包为 zip
            zip_filename = f"{base_name}.zip"
            zip_path = os.path.join(req_dir, zip_filename)
            with zipfile.ZipFile(zip_path, "w") as zf:
                for p in saved:
                    zf.write(p, os.path.basename(p))

            return FileResponse(
                zip_path,
                media_type="application/zip",
                filename=zip_filename,
                background=BackgroundTask(shutil.rmtree, req_dir, ignore_errors=True),
            )

        # 视频帖
        if not info["video_urls"]:
            shutil.rmtree(req_dir, ignore_errors=True)
            raise HTTPException(status_code=404, detail="未找到视频地址")

        filename = base_name + ".mp4"
        save_path = os.path.join(req_dir, filename)

        last_error = None
        for video_url in info["video_urls"]:
            try:
                await download_video(video_url, save_path)
                return FileResponse(
                    save_path,
                    media_type="video/mp4",
                    filename=filename,
                    background=BackgroundTask(shutil.rmtree, req_dir, ignore_errors=True),
                )
            except Exception as e:
                last_error = e
                continue

        shutil.rmtree(req_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"下载失败: {last_error}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


ALLOWED_PROXY_DOMAINS = {
    "douyinvod.com",
    "douyincdn.com",
    "snssdk.com",
    "amemv.com",
    "bytecdn.cn",
    "bytedance.com",
    "pstatp.com",
    "iesdouyin.com",
    "douyin.com",
    "byteicdn.com",
    "ibytedtos.com",
    "byted-static.com",
    "toutiaovod.com",
    "douyinpic.com",
}


def _is_allowed_proxy_url(url: str) -> bool:
    """检查 URL 是否属于允许代理的域名，防止 SSRF 攻击"""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname or ""
        return any(
            hostname == domain or hostname.endswith("." + domain)
            for domain in ALLOWED_PROXY_DOMAINS
        )
    except Exception:
        return False


@app.get("/api/proxy")
async def api_proxy(
    url: str = Query(..., description="视频 URL"),
    filename: str = Query(None, description="下载文件名"),
):
    """代理视频请求，解决 CDN 403 问题"""
    if not _is_allowed_proxy_url(url):
        raise HTTPException(status_code=403, detail="该 URL 域名不在允许代理的范围内")

    headers = {
        "User-Agent": MOBILE_UA,
        "Referer": "https://www.douyin.com/",
    }

    try:
        # 用 GET 流式请求，从响应头中读取 content-type 和 content-length
        # 不再发 HEAD 预检，因为部分 CDN（如 douyinpic.com）不支持 HEAD 方法
        client = httpx.AsyncClient(
            headers=headers,
            follow_redirects=True,
            timeout=120,
        )
        resp = await client.send(
            client.build_request("GET", url),
            stream=True,
        )
        resp.raise_for_status()

        resp_headers = {
            "Content-Type": resp.headers.get("content-type", "video/mp4"),
        }
        if "content-length" in resp.headers:
            resp_headers["Content-Length"] = resp.headers["content-length"]
        if filename:
            resp_headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"

        async def stream_response():
            try:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    yield chunk
            finally:
                await resp.aclose()
                await client.aclose()

        return StreamingResponse(stream_response(), headers=resp_headers)

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

        function showResult(data) {
            const el = document.getElementById('result');
            const baseName = (data.author && data.title)
                ? (data.author + '_' + data.title).replace(/[\\\\/:*?"<>|]/g, '_')
                : 'douyin_video';
            const isImages = data.type === 'images';

            let contentLinks = '';
            if (isImages) {
                (data.image_urls || []).forEach((u, i) => {
                    const imgFilename = baseName + '_' + (i+1) + '.webp';
                    const proxyUrl = '/api/proxy?url=' + encodeURIComponent(u) + '&filename=' + encodeURIComponent(imgFilename);
                    contentLinks += `<a class="video-link" href="${proxyUrl}" target="_blank" rel="noopener">[${i+1}] ${u}</a>`;
                });
            } else {
                const filename = baseName + '.mp4';
                (data.video_urls || []).forEach((u, i) => {
                    const proxyUrl = '/api/proxy?url=' + encodeURIComponent(u) + '&filename=' + encodeURIComponent(filename);
                    contentLinks += `<a class="video-link" href="${proxyUrl}" target="_blank" rel="noopener">[${i+1}] ${u}</a>`;
                });
            }

            const typeLabel = isImages ? '图文' : '视频';
            const extraInfo = isImages
                ? `<div class="info-row"><span>图片数量：</span>${(data.image_urls || []).length}</div>`
                : `<div class="info-row"><span>时长：</span>${data.duration || 0}s</div>`;
            const linksLabel = isImages ? '图片地址' : '无水印视频地址';

            el.innerHTML = `
                <h3>${data.title || '未知标题'}</h3>
                <div class="info-row"><span>类型：</span>${typeLabel}</div>
                <div class="info-row"><span>作者：</span>${data.author || '-'}</div>
                <div class="info-row"><span>ID：</span>${data.aweme_id || '-'}</div>
                ${extraInfo}
                <div class="info-row" style="margin-top:12px;"><span>${linksLabel}：</span></div>
                ${contentLinks}
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
