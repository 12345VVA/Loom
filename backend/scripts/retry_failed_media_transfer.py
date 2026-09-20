"""一次性补转存失败媒体资产。

对 status=failed 且带 original_url 的媒体资产重新执行转存，逻辑收敛到
MediaAssetService.retry_failed（含 24h 失败窗口与去重落盘）。厂商签名 URL
默认 24h 过期，已过期的资产会保持 failed 状态。

用法（backend/ 目录下）：
    venv/Scripts/python scripts/retry_failed_media_transfer.py [limit] [window_hours]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.modules.media.service.media_service import MediaAssetService


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    window_hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    with SessionLocal() as session:
        result = MediaAssetService(session).retry_failed(limit=limit, window_hours=window_hours)
    print(
        f"完成：尝试 {result['attempted']}，成功 {result['succeeded']}，"
        f"失败 {result['failed']}（窗口 {window_hours}h，limit {limit}）"
    )


if __name__ == "__main__":
    main()
