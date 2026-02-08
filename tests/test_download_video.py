import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock

from douyin_core import download_video


def _make_stream_mock_client(mock_stream_resp):
    """构造 mock client，正确处理 client.stream() 返回异步上下文管理器"""
    mock_client = MagicMock()
    mock_client.stream.return_value = mock_stream_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


async def test_download_video_writes_file(tmp_path):
    save_path = str(tmp_path / "test.mp4")
    chunks = [b"chunk1", b"chunk2", b"chunk3"]

    async def fake_aiter_bytes(chunk_size=None):
        for chunk in chunks:
            yield chunk

    mock_stream_resp = MagicMock()
    mock_stream_resp.raise_for_status = MagicMock()
    mock_stream_resp.headers = {"content-length": "18"}
    mock_stream_resp.aiter_bytes = fake_aiter_bytes
    mock_stream_resp.__aenter__ = AsyncMock(return_value=mock_stream_resp)
    mock_stream_resp.__aexit__ = AsyncMock(return_value=False)

    mock_client = _make_stream_mock_client(mock_stream_resp)

    with patch("douyin_core.httpx.AsyncClient", return_value=mock_client):
        result = await download_video("https://example.com/video.mp4", save_path)

    assert result == save_path
    with open(save_path, "rb") as f:
        assert f.read() == b"chunk1chunk2chunk3"


async def test_download_video_http_error(tmp_path):
    save_path = str(tmp_path / "test.mp4")

    mock_stream_resp = MagicMock()
    mock_stream_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "403 Forbidden",
        request=MagicMock(),
        response=MagicMock(status_code=403),
    )
    mock_stream_resp.__aenter__ = AsyncMock(return_value=mock_stream_resp)
    mock_stream_resp.__aexit__ = AsyncMock(return_value=False)

    mock_client = _make_stream_mock_client(mock_stream_resp)

    with patch("douyin_core.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await download_video("https://example.com/video.mp4", save_path)
