import pytest
from douyin_core import extract_url


def test_extract_url_from_share_text():
    text = "2.56 ABcDe 复制打开抖音，看看 https://v.douyin.com/iRNBho5e/ 更多精彩"
    assert extract_url(text) == "https://v.douyin.com/iRNBho5e/"


def test_extract_url_bare_url():
    url = "https://v.douyin.com/iRNBho5e/"
    assert extract_url(url) == url


def test_extract_url_http_scheme():
    text = "看看 http://v.douyin.com/iRNBho5e/ 这个视频"
    assert extract_url(text) == "http://v.douyin.com/iRNBho5e/"


def test_extract_url_multiple_urls():
    text = "https://first.com/a https://second.com/b"
    assert extract_url(text) == "https://first.com/a"


def test_extract_url_no_url_raises():
    with pytest.raises(ValueError, match="未找到有效 URL"):
        extract_url("没有链接的文本")


def test_extract_url_empty_string_raises():
    with pytest.raises(ValueError, match="未找到有效 URL"):
        extract_url("")
