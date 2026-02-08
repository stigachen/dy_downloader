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
    assert result["type"] == "video"


# ====== 图文帖测试 ======


def test_image_post_type(sample_image_detail):
    result = extract_video_urls(sample_image_detail)
    assert result["type"] == "images"


def test_image_post_extracts_image_urls(sample_image_detail):
    result = extract_video_urls(sample_image_detail)
    assert len(result["image_urls"]) == 2
    assert result["image_urls"][0] == "https://p3-sign.douyinpic.com/tos-cn-i/img1.webp"
    assert result["image_urls"][1] == "https://p3-sign.douyinpic.com/tos-cn-i/img2.webp"


def test_image_post_no_video_urls(sample_image_detail):
    result = extract_video_urls(sample_image_detail)
    assert result["video_urls"] == []


def test_image_post_cover_is_first_image(sample_image_detail):
    result = extract_video_urls(sample_image_detail)
    assert result["cover_url"] == result["image_urls"][0]


def test_image_post_basic_fields(sample_image_detail):
    result = extract_video_urls(sample_image_detail)
    assert result["title"] == "测试图文标题"
    assert result["author"] == "TestImageAuthor"
    assert result["aweme_id"] == "7603777432471298643"
    assert result["duration"] == 0


def test_video_post_type(sample_detail):
    result = extract_video_urls(sample_detail)
    assert result["type"] == "video"
    assert result["image_urls"] == []


def test_no_aweme_type_defaults_to_video():
    """无 aweme_type 字段默认当作视频帖处理"""
    detail = {
        "video": {"play_addr": {"uri": "test_uri"}},
    }
    result = extract_video_urls(detail)
    assert result["type"] == "video"
