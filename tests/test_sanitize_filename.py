from douyin_core import sanitize_filename


def test_sanitize_normal_name():
    assert sanitize_filename("hello world") == "hello world"


def test_sanitize_illegal_chars():
    result = sanitize_filename('a\\b/c:d*e?"f<g>h|i')
    assert "\\" not in result
    assert "/" not in result
    assert ":" not in result
    assert "*" not in result
    assert "?" not in result
    assert '"' not in result
    assert "<" not in result
    assert ">" not in result
    assert "|" not in result
    assert result == "a_b_c_d_e__f_g_h_i"


def test_sanitize_newlines_tabs():
    result = sanitize_filename("line1\nline2\rtab\there")
    assert "\n" not in result
    assert "\r" not in result
    assert "\t" not in result


def test_sanitize_strips_dots_spaces():
    assert sanitize_filename("  ..hello..  ") == "hello"


def test_sanitize_truncation_default():
    long_name = "a" * 100
    result = sanitize_filename(long_name)
    assert len(result) == 80


def test_sanitize_truncation_custom():
    assert sanitize_filename("abcdefghij", max_len=5) == "abcde"


def test_sanitize_empty_returns_default():
    assert sanitize_filename("") == "douyin_video"


def test_sanitize_chinese_chars():
    assert sanitize_filename("测试视频标题") == "测试视频标题"
