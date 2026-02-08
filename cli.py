#!/usr/bin/env python3
"""
抖音无水印视频下载 - 命令行工具

用法:
    python cli.py "分享文本或链接"
    python cli.py "https://v.douyin.com/xxx/" -o ./videos
    python cli.py "分享文本" --parse-only --json
"""

import argparse
import asyncio
import sys
import json

from douyin_core import parse_and_download


def main():
    parser = argparse.ArgumentParser(
        description="抖音无水印视频下载工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "2.56 复制打开抖音，看看... https://v.douyin.com/xxx/"
  %(prog)s "https://v.douyin.com/xxx/" -o ./videos
  %(prog)s "https://v.douyin.com/xxx/" --parse-only
  %(prog)s "https://v.douyin.com/xxx/" --parse-only --json
        """,
    )

    parser.add_argument(
        "share_text",
        help="抖音分享文本或视频链接",
    )
    parser.add_argument(
        "-o", "--output",
        default=".",
        help="下载目录 (默认: 当前目录)",
    )
    parser.add_argument(
        "--parse-only",
        action="store_true",
        help="仅解析视频信息，不下载",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="以 JSON 格式输出结果",
    )

    args = parser.parse_args()

    try:
        info = asyncio.run(
            parse_and_download(
                share_text=args.share_text,
                output_dir=args.output,
                only_parse=args.parse_only,
            )
        )

        if args.json_output:
            print(json.dumps(info, ensure_ascii=False, indent=2))
        elif args.parse_only:
            print("\n--- 视频信息 ---")
            print(f"标题: {info['title']}")
            print(f"作者: {info['author']}")
            print(f"视频ID: {info['aweme_id']}")
            print(f"时长: {info['duration']}s")
            print(f"封面: {info['cover_url']}")
            print(f"视频地址:")
            for i, u in enumerate(info["video_urls"], 1):
                print(f"  [{i}] {u}")

    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(130)
    except Exception as e:
        print(f"\n错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
