from douyin_core import extract_video_urls


def test_extract_video_urls_basic_fields(sample_detail):
    result = extract_video_urls(sample_detail)
    assert result["title"] == "测试视频标题"
    assert result["author"] == "TestAuthor"
    assert result["aweme_id"] == "7345678901234567890"
    assert result["cover_url"] == "https://p3-sign.douyinpic.com/tos-cn-i/cover.jpeg"


def test_extract_video_urls_constructed_from_uri(sample_detail):
    result = extract_video_urls(sample_detail)
    uri = "v0200fg10000abc123def456"
    expected_prefixes = [
        f"https://aweme.snssdk.com/aweme/v1/play/?video_id={uri}&ratio=default",
        f"https://aweme.snssdk.com/aweme/v1/play/?video_id={uri}&ratio=1080p",
        f"https://aweme.snssdk.com/aweme/v1/play/?video_id={uri}&ratio=720p",
    ]
    for expected in expected_prefixes:
        assert any(u.startswith(expected) for u in result["video_urls"]), (
            f"Expected URL starting with {expected}"
        )


def test_playwm_replaced_with_play(sample_detail):
    result = extract_video_urls(sample_detail)
    for u in result["video_urls"]:
        assert "/playwm/" not in u


def test_video_urls_no_duplicates(sample_detail):
    result = extract_video_urls(sample_detail)
    assert len(result["video_urls"]) == len(set(result["video_urls"]))


def test_duration_converted_from_millis(sample_detail):
    result = extract_video_urls(sample_detail)
    assert result["duration"] == 15  # 15000ms -> 15s


def test_duration_already_seconds():
    detail = {
        "video": {"duration": 15},
    }
    result = extract_video_urls(detail)
    assert result["duration"] == 15


def test_missing_fields_defaults(sample_detail_minimal):
    result = extract_video_urls(sample_detail_minimal)
    assert result["title"] == "未知标题"
    assert result["author"] == "未知作者"
    assert result["aweme_id"] == ""
    assert result["video_urls"] == []
    assert result["cover_url"] == ""
