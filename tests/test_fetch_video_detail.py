import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from douyin_core import fetch_video_detail


def _make_mock_client(html_text):
    """构造一个 mock httpx.AsyncClient，返回指定 HTML 的响应"""
    mock_response = MagicMock()
    mock_response.text = html_text
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False
    return mock_client


async def test_fetch_video_detail_success(sample_detail, sample_router_data_html):
    mock_client = _make_mock_client(sample_router_data_html)

    with patch("douyin_core.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_video_detail("https://v.douyin.com/xxx/")

    assert result["aweme_id"] == "7345678901234567890"
    assert result["desc"] == "测试视频标题"


async def test_fetch_video_detail_no_router_data():
    mock_client = _make_mock_client("<html><body>no data here</body></html>")

    with patch("douyin_core.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(RuntimeError, match="未在页面中找到视频数据"):
            await fetch_video_detail("https://v.douyin.com/xxx/")


async def test_fetch_video_detail_invalid_json():
    html = "<html><script>window._ROUTER_DATA = {invalid json}</script></html>"
    mock_client = _make_mock_client(html)

    with patch("douyin_core.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(RuntimeError, match="解析页面数据失败"):
            await fetch_video_detail("https://v.douyin.com/xxx/")


async def test_fetch_video_detail_no_video_info_res():
    router_data = {"loaderData": {"some_page": {"otherData": {}}}}
    html = f"<html><script>window._ROUTER_DATA = {json.dumps(router_data)}</script></html>"
    mock_client = _make_mock_client(html)

    with patch("douyin_core.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(RuntimeError, match="未在页面数据中找到 videoInfoRes"):
            await fetch_video_detail("https://v.douyin.com/xxx/")


async def test_fetch_video_detail_empty_item_list():
    router_data = {
        "loaderData": {
            "video_page": {
                "videoInfoRes": {"item_list": []}
            }
        }
    }
    html = f"<html><script>window._ROUTER_DATA = {json.dumps(router_data)}</script></html>"
    mock_client = _make_mock_client(html)

    with patch("douyin_core.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(RuntimeError, match="视频列表为空"):
            await fetch_video_detail("https://v.douyin.com/xxx/")
