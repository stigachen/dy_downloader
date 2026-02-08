"""
抖音无水印视频下载核心模块

原理：
1. 解析分享文本，提取短链接 (v.douyin.com/xxx)
2. 使用移动端 UA 访问短链接，跟随 302 重定向到 iesdouyin.com 分享页
3. 从分享页的 _ROUTER_DATA 中提取视频详情（包含 play_addr）
4. 将 play_addr 中的 /playwm/ 替换为 /play/ 获取无水印视频地址
5. 下载视频
"""

import re
import os
import json
import httpx

# 从分享文本中提取 URL
SHARE_URL_PATTERN = re.compile(r"https?://[^\s]+")

# 从重定向后的完整 URL 中提取 video id
VIDEO_ID_PATTERNS = [
    re.compile(r"video/(\d+)"),
    re.compile(r"note/(\d+)"),
    re.compile(r"modal_id=(\d+)"),
    re.compile(r"[?&]vid=(\d+)"),
]

# 从分享页提取 _ROUTER_DATA
ROUTER_DATA_PATTERN = re.compile(r"window\._ROUTER_DATA\s*=\s*(\{.*?\})</script>", re.DOTALL)

# 从 /share/slides/{id}/ 路径中提取 aweme_id
SLIDES_PATH_PATTERN = re.compile(r"/share/slides/(\d+)")

# 移动端 UA (用于触发 iesdouyin 分享页，该页面包含视频数据)
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
)

DEFAULT_HEADERS = {
    "User-Agent": MOBILE_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def extract_url(share_text: str) -> str:
    """从分享文本中提取 URL"""
    match = SHARE_URL_PATTERN.search(share_text)
    if not match:
        raise ValueError("未找到有效 URL，请检查输入内容")
    return match.group(0)


async def resolve_share_url(url: str) -> str:
    """跟随重定向，获取最终 URL"""
    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        timeout=15,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return str(resp.url)


def extract_aweme_id(url: str) -> str:
    """从完整 URL 中提取 aweme_id"""
    for pattern in VIDEO_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    raise ValueError(f"无法从 URL 中提取视频 ID: {url}")


async def fetch_video_detail(share_url: str) -> dict:
    """
    通过移动端 UA 访问分享链接，从 iesdouyin.com 分享页面的
    _ROUTER_DATA 中提取视频详情。

    如果重定向到 /share/slides/ 页面（CSR，无 _ROUTER_DATA），
    则从 URL 中提取 aweme_id，改用 /share/video/ 路径重新请求。

    这种方式不需要 Cookie 或签名算法。
    """
    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        timeout=15,
    ) as client:
        resp = await client.get(share_url)
        resp.raise_for_status()
        final_url = str(resp.url)

        # /share/slides/ 页面是纯 CSR，不包含 _ROUTER_DATA
        # 需要提取 aweme_id 后改用 /share/video/ 路径请求
        slides_match = SLIDES_PATH_PATTERN.search(final_url)
        if slides_match:
            aweme_id = slides_match.group(1)
            video_url = f"https://www.iesdouyin.com/share/video/{aweme_id}/"
            resp = await client.get(video_url)
            resp.raise_for_status()

    html = resp.text

    # 提取 _ROUTER_DATA
    match = ROUTER_DATA_PATTERN.search(html)
    if not match:
        raise RuntimeError(
            "未在页面中找到视频数据 (_ROUTER_DATA)。\n"
            "可能是抖音页面结构已更新，或链接无效。"
        )

    try:
        router_data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"解析页面数据失败: {e}")

    # 导航到视频数据
    loader_data = router_data.get("loaderData", {})

    # 页面 key 可能是 "video_(id)/page" 或其他变体，遍历查找 videoInfoRes
    video_info_res = None
    for key, value in loader_data.items():
        if isinstance(value, dict) and "videoInfoRes" in value:
            video_info_res = value["videoInfoRes"]
            break

    if not video_info_res:
        raise RuntimeError("未在页面数据中找到 videoInfoRes")

    item_list = video_info_res.get("item_list", [])
    if not item_list:
        raise RuntimeError("视频列表为空，该视频可能已被删除或不可用")

    return item_list[0]


def extract_video_urls(detail: dict) -> dict:
    """
    从视频/图文详情中提取内容信息。

    通过 aweme_type 判断类型：
        - aweme_type == 2: 图文帖，提取 images 数组中的图片 URL
        - 其他: 视频帖，提取 play_addr 中的视频 URL

    返回:
        {
            "type": "video" 或 "images",
            "title": 标题,
            "author": 作者昵称,
            "aweme_id": ID,
            "video_urls": [无水印视频URL列表],
            "image_urls": [图片URL列表],
            "cover_url": 封面URL,
            "duration": 视频时长(秒),
        }
    """
    author_info = detail.get("author", {})
    desc = detail.get("desc", "未知标题")
    aweme_type = detail.get("aweme_type", 0)

    base_info = {
        "title": desc,
        "author": author_info.get("nickname", "未知作者"),
        "aweme_id": str(detail.get("aweme_id", "")),
    }

    # 图文帖
    if aweme_type == 2:
        images = detail.get("images", [])
        image_urls = []
        for img in images:
            url_list = img.get("url_list", [])
            if url_list:
                image_urls.append(url_list[0])
        cover_url = image_urls[0] if image_urls else ""
        return {
            **base_info,
            "type": "images",
            "video_urls": [],
            "image_urls": image_urls,
            "cover_url": cover_url,
            "duration": 0,
        }

    # 视频帖
    video = detail.get("video", {})
    play_addr = video.get("play_addr", {})
    uri = play_addr.get("uri", "")

    # 通过 video_id (uri) 构造无水印地址，按画质从高到低排列
    # ratio=default 返回原始最高画质 (通常 1080p HEVC 高码率)
    # ratio=1080p 返回 1080p H.264
    # ratio=720p 返回 720p H.264 (分享页默认给的就是这个)
    clean_urls = []
    if uri:
        for ratio in ("default", "1080p", "720p"):
            clean_urls.append(
                f"https://aweme.snssdk.com/aweme/v1/play/?video_id={uri}&ratio={ratio}&line=0"
            )

    # 也保留分享页原始地址作为兜底 (替换 /playwm/ -> /play/ 去水印)
    url_list = play_addr.get("url_list", [])
    for u in url_list:
        fallback = u.replace("/playwm/", "/play/")
        if fallback not in clean_urls:
            clean_urls.append(fallback)

    # 去重但保持顺序
    seen = set()
    unique_urls = []
    for u in clean_urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    duration = video.get("duration", 0)
    cover = video.get("cover", {}).get("url_list", [""])[0]

    return {
        **base_info,
        "type": "video",
        "video_urls": unique_urls,
        "image_urls": [],
        "cover_url": cover,
        "duration": duration // 1000 if duration > 1000 else duration,
    }


async def download_video(url: str, save_path: str) -> str:
    """下载视频到本地文件"""
    headers = {
        "User-Agent": MOBILE_UA,
        "Referer": "https://www.douyin.com/",
    }

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=120,
    ) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0

            with open(save_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = downloaded / total * 100
                        print(f"\r下载进度: {pct:.1f}% ({downloaded}/{total} bytes)", end="", flush=True)

            if total > 0:
                print()  # 换行

    return save_path


def sanitize_filename(name: str, max_len: int = 80) -> str:
    """清理文件名中的非法字符"""
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", name)
    name = name.strip(". ")
    if len(name) > max_len:
        name = name[:max_len]
    return name or "douyin_video"


async def parse_and_download(
    share_text: str,
    output_dir: str = ".",
    only_parse: bool = False,
) -> dict:
    """
    完整流程：解析 → 获取详情 → 下载

    Args:
        share_text: 抖音分享文本或链接
        output_dir: 下载目录
        only_parse: 仅解析不下载

    Returns:
        视频信息字典
    """
    # 1. 提取 URL
    url = extract_url(share_text)
    print(f"[1/4] 提取到链接: {url}")

    # 2. 获取视频详情 (直接从分享页提取，不需要额外 API)
    print("[2/4] 正在解析视频信息...")
    detail = await fetch_video_detail(url)
    info = extract_video_urls(detail)
    aweme_id = info["aweme_id"]
    content_type = info.get("type", "video")
    print(f"[3/4] ID: {aweme_id}")
    print(f"      类型: {'图文' if content_type == 'images' else '视频'}")
    print(f"      标题: {info['title']}")
    print(f"      作者: {info['author']}")
    if content_type == "video":
        print(f"      时长: {info['duration']}s")
        print(f"      找到 {len(info['video_urls'])} 个视频地址")
    else:
        print(f"      找到 {len(info['image_urls'])} 张图片")

    if only_parse:
        info["downloaded"] = False
        return info

    os.makedirs(output_dir, exist_ok=True)

    if content_type == "images":
        # 图文帖：逐张下载图片
        if not info["image_urls"]:
            raise RuntimeError("未找到可下载的图片地址")

        base_name = sanitize_filename(f"{info['author']}_{info['title']}")
        saved_paths = []
        for i, img_url in enumerate(info["image_urls"], 1):
            ext = ".webp"
            filename = f"{base_name}_{i}{ext}"
            save_path = os.path.join(output_dir, filename)
            print(f"[4/4] 正在下载图片 {i}/{len(info['image_urls'])}: {filename}")
            try:
                await download_video(img_url, save_path)
                saved_paths.append(save_path)
            except Exception as e:
                print(f"图片 {i} 下载失败: {e}")

        if not saved_paths:
            raise RuntimeError("所有图片均下载失败")

        info["save_paths"] = saved_paths
        info["downloaded"] = True
        print(f"下载完成: 共 {len(saved_paths)} 张图片")
        return info

    # 视频帖
    if not info["video_urls"]:
        raise RuntimeError("未找到可下载的视频地址")

    # 4. 下载视频
    filename = sanitize_filename(f"{info['author']}_{info['title']}") + ".mp4"
    save_path = os.path.join(output_dir, filename)

    print(f"[4/4] 正在下载到: {save_path}")

    # 尝试多个 URL，直到成功
    last_error = None
    for video_url in info["video_urls"]:
        try:
            await download_video(video_url, save_path)
            info["save_path"] = save_path
            info["downloaded"] = True
            print(f"下载完成: {save_path}")
            return info
        except Exception as e:
            last_error = e
            print(f"该地址下载失败，尝试下一个...")
            continue

    raise RuntimeError(f"所有视频地址均下载失败: {last_error}")
