import pytest
from douyin_core import extract_aweme_id


def test_extract_aweme_id_video_path():
    url = "https://www.iesdouyin.com/share/video/7345678901234567890/?region=CN"
    assert extract_aweme_id(url) == "7345678901234567890"


def test_extract_aweme_id_note_path():
    url = "https://www.iesdouyin.com/share/note/7345678901234567890/?region=CN"
    assert extract_aweme_id(url) == "7345678901234567890"


def test_extract_aweme_id_modal_id():
    url = "https://www.douyin.com/discover?modal_id=7345678901234567890"
    assert extract_aweme_id(url) == "7345678901234567890"


def test_extract_aweme_id_vid_param():
    url = "https://www.douyin.com/video?vid=7345678901234567890&other=1"
    assert extract_aweme_id(url) == "7345678901234567890"


def test_extract_aweme_id_no_match_raises():
    with pytest.raises(ValueError, match="无法从 URL 中提取视频 ID"):
        extract_aweme_id("https://www.douyin.com/some/other/path")


def test_extract_aweme_id_empty_raises():
    with pytest.raises(ValueError, match="无法从 URL 中提取视频 ID"):
        extract_aweme_id("")
