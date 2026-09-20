"""一次性补转存失败媒体资产。

对 status=failed 且带 original_url 的媒体资产重新执行转存（复用
MediaAssetService._transfer_artifact，含去重与存储落盘）。厂商签名 URL
默认 24h 过期，已过期的资产会保持 failed 状态并打印原因。

用法（backend/ 目录下）：
    venv/Scripts/python scripts/retry_failed_media_transfer.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import select

from app.core.database import SessionLocal
from app.modules.media.model.media import MediaAsset
from app.modules.media.service.media_service import MediaArtifact, MediaAssetService


def main() -> None:
    with SessionLocal() as session:
        assets = session.exec(
            select(MediaAsset)
            .where(
                MediaAsset.status == "failed",
                MediaAsset.original_url != None,  # noqa: E711
                MediaAsset.delete_time == None,  # noqa: E711
            )
            .order_by(MediaAsset.id)
        ).all()
        if not assets:
            print("没有需要补转存的失败资产")
            return
        print(f"待补转存资产 {len(assets)} 条")
        service = MediaAssetService(session)
        succeeded = 0
        for asset in assets:
            artifact = MediaArtifact(
                asset_type=asset.asset_type,
                original_url=asset.original_url,
                mime_type=asset.mime_type,
                file_name=asset.file_name,
                width=asset.width,
                height=asset.height,
                duration_seconds=asset.duration_seconds,
            )
            try:
                service._transfer_artifact(asset, artifact)
                succeeded += 1
                print(f"  #{asset.id} 转存成功 -> {asset.storage_url}")
            except Exception as exc:  # 补转存失败不影响其他资产
                asset.status = "failed"
                asset.error_message = str(exc)[:1000]
                session.add(asset)
                session.commit()
                print(f"  #{asset.id} 转存失败: {exc}")
        print(f"完成：成功 {succeeded}/{len(assets)}")


if __name__ == "__main__":
    main()
