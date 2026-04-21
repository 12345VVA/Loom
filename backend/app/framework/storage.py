import os
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from app.core.config import settings


class BaseStorageProvider(ABC):
    """存储提供者抽象基类"""

    @abstractmethod
    def upload(self, file_content: bytes, filename: str) -> str:
        """上传文件并返回访问路径"""
        pass

    @abstractmethod
    def delete(self, path: str) -> bool:
        """删除文件"""
        pass


class UploadRejectedError(ValueError):
    """文件上传被拒绝"""


def validate_upload(file_content: bytes, filename: str) -> str:
    """
    校验上传文件：类型白名单 + 大小限制。
    通过后返回规范化的扩展名（含前导点），供后续使用。
    """
    # 1. 扩展名白名单
    ext = os.path.splitext(filename)[1].lower()
    if not ext:
        raise UploadRejectedError(f"文件缺少扩展名: {filename}")

    allowed = {e.strip().lower() for e in settings.UPLOAD_ALLOWED_EXTENSIONS.split(",")}
    if ext not in allowed:
        raise UploadRejectedError(f"不支持的文件类型: {ext}，允许的类型: {', '.join(sorted(allowed))}")

    # 2. 文件大小限制
    max_bytes = settings.UPLOAD_MAX_SIZE_MB * 1024 * 1024
    if len(file_content) > max_bytes:
        raise UploadRejectedError(
            f"文件大小 {len(file_content) / 1024 / 1024:.1f}MB 超过限制 {settings.UPLOAD_MAX_SIZE_MB}MB"
        )

    return ext


class LocalStorageProvider(BaseStorageProvider):
    """本地文件存储提供者"""

    def __init__(self, upload_dir: str = "data/uploads", base_url: str = "/uploads"):
        self.upload_dir = os.path.abspath(upload_dir)
        self.base_url = base_url
        if not os.path.exists(self.upload_dir):
            os.makedirs(self.upload_dir)

    def upload(self, file_content: bytes, filename: str) -> str:
        ext = validate_upload(file_content, filename)

        date_folder = datetime.now().strftime("%Y%m%d")
        dest_dir = os.path.join(self.upload_dir, date_folder)

        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)

        unique_filename = f"{uuid.uuid4().hex}{ext}"
        dest_path = os.path.join(dest_dir, unique_filename)

        # 路径遍历防护：确保写入目标仍在上传根目录下
        dest_path = os.path.abspath(dest_path)
        if not dest_path.startswith(self.upload_dir + os.sep):
            raise UploadRejectedError("非法文件路径")

        with open(dest_path, "wb") as f:
            f.write(file_content)

        return f"{self.base_url}/{date_folder}/{unique_filename}"

    def delete(self, path: str) -> bool:
        relative_path = path.replace(self.base_url, "").lstrip("/")
        full_path = os.path.abspath(os.path.join(self.upload_dir, relative_path))

        # 路径遍历防护：确保删除目标在上传根目录下
        if not full_path.startswith(self.upload_dir + os.sep):
            return False

        if os.path.exists(full_path):
            os.remove(full_path)
            return True
        return False


class StorageService:
    """存储服务管理器"""

    _instance = None

    def __init__(self, provider: BaseStorageProvider):
        self.provider = provider

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls(LocalStorageProvider())
        return cls._instance

    def upload(self, file_content: bytes, filename: str) -> str:
        return self.provider.upload(file_content, filename)

    def delete(self, path: str) -> bool:
        return self.provider.delete(path)
