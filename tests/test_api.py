import pytest
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

    mock_stream_resp = MagicMock()
    mock_stream_resp.raise_for_status = MagicMock()
    mock_stream_resp.headers = {"content-type": "video/mp4", "content-length": "10"}
    mock_stream_resp.aiter_bytes = fake_aiter_bytes
    mock_stream_resp.__aenter__ = AsyncMock(return_value=mock_stream_resp)
    mock_stream_resp.__aexit__ = AsyncMock(return_value=False)

    mock_head_resp = MagicMock()
    mock_head_resp.raise_for_status = MagicMock()
    mock_head_resp.headers = {"content-type": "video/mp4", "content-length": "10"}

    mock_client = MagicMock()
    mock_client.head = AsyncMock(return_value=mock_head_resp)
    mock_client.stream.return_value = mock_stream_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("server.httpx.AsyncClient", return_value=mock_client):
        resp = await client.get(
            "/api/proxy",
            params={"url": "https://example.com/video.mp4", "filename": "测试.mp4"},
        )

    assert resp.status_code == 200
    assert "Content-Disposition" in resp.headers or "content-disposition" in resp.headers
    disposition = resp.headers.get("content-disposition", "")
    assert "测试.mp4" in disposition or "%E6%B5%8B%E8%AF%95.mp4" in disposition


async def test_api_proxy_missing_url(client):
    resp = await client.get("/api/proxy")
    assert resp.status_code == 422
