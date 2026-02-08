import pytest
import asyncio
import httpx
from unittest.mock import patch, AsyncMock, MagicMock

from server import app


@pytest.fixture
async def client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


async def test_index_returns_html(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "抖音无水印下载" in resp.text


async def test_api_parse_success(client, sample_detail):
    with patch("server.fetch_video_detail", new_callable=AsyncMock, return_value=sample_detail):
        resp = await client.post("/api/parse", json={"share_text": "https://v.douyin.com/xxx/"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["title"] == "测试视频标题"
    assert data["data"]["author"] == "TestAuthor"
    assert len(data["data"]["video_urls"]) > 0


async def test_api_parse_invalid_input(client):
    resp = await client.post("/api/parse", json={"share_text": "no url here"})
    assert resp.status_code == 400


async def test_api_download_success(client, sample_detail, tmp_path):
    video_file = tmp_path / "test.mp4"
    video_file.write_bytes(b"fake video content")

    async def mock_download(url, save_path):
        import shutil
        shutil.copy(str(video_file), save_path)
        return save_path

    with (
        patch("server.fetch_video_detail", new_callable=AsyncMock, return_value=sample_detail),
        patch("server.download_video", side_effect=mock_download),
    ):
        resp = await client.post("/api/download", json={"share_text": "https://v.douyin.com/xxx/"})

    assert resp.status_code == 200
    assert "video/mp4" in resp.headers.get("content-type", "")


async def test_api_download_no_video_urls(client):
    detail_no_urls = {
        "video": {},
    }
    with patch("server.fetch_video_detail", new_callable=AsyncMock, return_value=detail_no_urls):
        resp = await client.post("/api/download", json={"share_text": "https://v.douyin.com/xxx/"})

    assert resp.status_code == 404


async def test_api_proxy_with_filename(client):
    async def fake_aiter_bytes(chunk_size=None):
        yield b"video data"

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.headers = {"content-type": "video/mp4", "content-length": "10"}
    mock_resp.aiter_bytes = fake_aiter_bytes
    mock_resp.aclose = AsyncMock()

    mock_client = MagicMock()
    mock_client.build_request = MagicMock(return_value="fake_request")
    mock_client.send = AsyncMock(return_value=mock_resp)
    mock_client.aclose = AsyncMock()

    with patch("server.httpx.AsyncClient", return_value=mock_client):
        resp = await client.get(
            "/api/proxy",
            params={"url": "https://v3-dy.douyinvod.com/video.mp4", "filename": "测试.mp4"},
        )

    assert resp.status_code == 200
    assert "Content-Disposition" in resp.headers or "content-disposition" in resp.headers
    disposition = resp.headers.get("content-disposition", "")
    assert "测试.mp4" in disposition or "%E6%B5%8B%E8%AF%95.mp4" in disposition


async def test_api_proxy_missing_url(client):
    resp = await client.get("/api/proxy")
    assert resp.status_code == 422


async def test_api_proxy_blocks_disallowed_domain(client):
    """SSRF 防护：非白名单域名应返回 403"""
    resp = await client.get("/api/proxy", params={"url": "https://evil.com/steal"})
    assert resp.status_code == 403


async def test_api_proxy_blocks_internal_ip(client):
    """SSRF 防护：内网地址应返回 403"""
    resp = await client.get("/api/proxy", params={"url": "http://169.254.169.254/latest/meta-data/"})
    assert resp.status_code == 403


async def test_api_proxy_blocks_non_http_scheme(client):
    """SSRF 防护：非 http/https 协议应返回 403"""
    resp = await client.get("/api/proxy", params={"url": "file:///etc/passwd"})
    assert resp.status_code == 403


# ====== 图文帖 API 测试 ======


async def test_api_parse_image_post(client, sample_image_detail):
    with patch("server.fetch_video_detail", new_callable=AsyncMock, return_value=sample_image_detail):
        resp = await client.post("/api/parse", json={"share_text": "https://v.douyin.com/xxx/"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["type"] == "images"
    assert data["data"]["video_urls"] == []
    assert len(data["data"]["image_urls"]) == 2
    assert data["data"]["title"] == "测试图文标题"


async def test_api_download_image_post(client, sample_image_detail, tmp_path):
    img_file = tmp_path / "fake.webp"
    img_file.write_bytes(b"fake image content")

    async def mock_download(url, save_path):
        import shutil
        shutil.copy(str(img_file), save_path)
        return save_path

    with (
        patch("server.fetch_video_detail", new_callable=AsyncMock, return_value=sample_image_detail),
        patch("server.download_video", side_effect=mock_download),
    ):
        resp = await client.post("/api/download", json={"share_text": "https://v.douyin.com/xxx/"})

    assert resp.status_code == 200
    # 多张图片返回 zip
    assert "application/zip" in resp.headers.get("content-type", "") or "application/x-zip" in resp.headers.get("content-type", "")


async def test_api_download_concurrent_same_video(client, sample_detail, tmp_path):
    """并发下载同一视频时，各请求使用独立临时文件，互不干扰"""
    video_file = tmp_path / "test.mp4"
    video_file.write_bytes(b"fake video content")

    async def mock_download(url, save_path):
        import shutil
        # 模拟下载耗时，增加并发冲突概率
        await asyncio.sleep(0.05)
        shutil.copy(str(video_file), save_path)
        return save_path

    with (
        patch("server.fetch_video_detail", new_callable=AsyncMock, return_value=sample_detail),
        patch("server.download_video", side_effect=mock_download),
    ):
        results = await asyncio.gather(
            client.post("/api/download", json={"share_text": "https://v.douyin.com/aaa/"}),
            client.post("/api/download", json={"share_text": "https://v.douyin.com/bbb/"}),
            client.post("/api/download", json={"share_text": "https://v.douyin.com/ccc/"}),
        )

    for resp in results:
        assert resp.status_code == 200
        assert "video/mp4" in resp.headers.get("content-type", "")
        assert len(resp.content) > 0


async def test_api_proxy_image_url(client):
    """代理图片 URL（douyinpic.com CDN）应正常工作，不再依赖 HEAD 请求"""
    async def fake_aiter_bytes(chunk_size=None):
        yield b"image data"

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.headers = {"content-type": "image/webp", "content-length": "10"}
    mock_resp.aiter_bytes = fake_aiter_bytes
    mock_resp.aclose = AsyncMock()

    mock_client = MagicMock()
    mock_client.build_request = MagicMock(return_value="fake_request")
    mock_client.send = AsyncMock(return_value=mock_resp)
    mock_client.aclose = AsyncMock()

    with patch("server.httpx.AsyncClient", return_value=mock_client):
        resp = await client.get(
            "/api/proxy",
            params={
                "url": "https://p26-sign.douyinpic.com/tos-cn-i/image.webp?x-expires=123",
                "filename": "图片.webp",
            },
        )

    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "image/webp"
