import json
import pytest


@pytest.fixture
def sample_detail():
    """模拟 Douyin 视频详情 dict（fetch_video_detail 返回值）"""
    return {
        "aweme_id": "7345678901234567890",
        "desc": "测试视频标题",
        "author": {
            "nickname": "TestAuthor",
            "uid": "123456",
        },
        "video": {
            "play_addr": {
                "uri": "v0200fg10000abc123def456",
                "url_list": [
                    "https://www.douyin.com/aweme/v1/playwm/?video_id=v0200fg10000abc123def456&line=0",
                    "https://www.douyin.com/aweme/v1/playwm/?video_id=v0200fg10000abc123def456&line=1",
                ],
            },
            "cover": {
                "url_list": [
                    "https://p3-sign.douyinpic.com/tos-cn-i/cover.jpeg",
                ],
            },
            "duration": 15000,
        },
    }


@pytest.fixture
def sample_detail_minimal():
    """最小化 detail，测试默认值"""
    return {
        "video": {},
    }


@pytest.fixture
def sample_router_data_html(sample_detail):
    """包含 _ROUTER_DATA 的模拟 HTML 页面"""
    router_data = {
        "loaderData": {
            "video_(id)/page": {
                "videoInfoRes": {
                    "item_list": [sample_detail]
                }
            }
        }
    }
    return (
        "<html><head></head><body>"
        f"<script>window._ROUTER_DATA = {json.dumps(router_data, ensure_ascii=False)}</script>"
        "</body></html>"
    )
