import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from douyin_core import fetch_video_detail


def _make_mock_client(html_text, final_url="https://www.iesdouyin.com/share/video/123/"):
    """构造一个 mock httpx.AsyncClient，返回指定 HTML 的响应"""
    mock_response = MagicMock()
    mock_response.text = html_text
    mock_response.raise_for_status = MagicMock()
    mock_response.url = final_url

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


async def test_fetch_video_detail_slides_fallback(sample_detail):
    """当重定向到 /share/slides/ 时，应自动改用 /share/video/ 路径重新请求"""
    # 第一次请求返回 slides 页面（无 _ROUTER_DATA）
    slides_response = MagicMock()
    slides_response.text = "<html><body>slides CSR page</body></html>"
    slides_response.raise_for_status = MagicMock()
    slides_response.url = "https://www.iesdouyin.com/share/slides/7604002509288003003/?region=CN"

    # 第二次请求返回 video 页面（有 _ROUTER_DATA）
    router_data = {
        "loaderData": {
            "video_(id)/page": {
                "videoInfoRes": {
                    "item_list": [sample_detail]
                }
            }
        }
    }
    video_html = (
        "<html><head></head><body>"
        f"<script>window._ROUTER_DATA = {json.dumps(router_data, ensure_ascii=False)}</script>"
        "</body></html>"
    )
    video_response = MagicMock()
    video_response.text = video_html
    video_response.raise_for_status = MagicMock()
    video_response.url = "https://www.iesdouyin.com/share/video/7604002509288003003/"

    mock_client = AsyncMock()
    mock_client.get.side_effect = [slides_response, video_response]
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False

    with patch("douyin_core.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_video_detail("https://v.douyin.com/EygiOkP3IAU/")

    assert result["aweme_id"] == sample_detail["aweme_id"]
    assert result["desc"] == sample_detail["desc"]
    # 验证第二次请求使用了 /share/video/ 路径
    assert mock_client.get.call_count == 2
    second_call_url = mock_client.get.call_args_list[1][0][0]
    assert "/share/video/7604002509288003003/" in second_call_url
