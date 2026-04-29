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

    def _resolve_safe_path(self, relative_path: str) -> str:
        full_path = os.path.abspath(os.path.join(self.upload_dir, relative_path))
        try:
            common = os.path.commonpath([self.upload_dir, full_path])
        except ValueError as exc:
            raise UploadRejectedError("非法文件路径") from exc
        if common != self.upload_dir:
            raise UploadRejectedError("非法文件路径")
        return full_path

    def upload(self, file_content: bytes, filename: str) -> str:
        ext = validate_upload(file_content, filename)

        date_folder = datetime.now().strftime("%Y%m%d")
        dest_dir = os.path.join(self.upload_dir, date_folder)

        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)

        unique_filename = f"{uuid.uuid4().hex}{ext}"
        dest_path = self._resolve_safe_path(os.path.join(date_folder, unique_filename))

        with open(dest_path, "wb") as f:
            f.write(file_content)

        return f"{self.base_url}/{date_folder}/{unique_filename}"

    def delete(self, path: str) -> bool:
        relative_path = path.replace(self.base_url, "").lstrip("/")
        try:
            full_path = self._resolve_safe_path(relative_path)
        except UploadRejectedError:
            return False

        if os.path.exists(full_path):
            os.remove(full_path)
            return True
        return False


class S3StorageProvider(BaseStorageProvider):
    """S3-compatible 对象存储提供者。"""

    def __init__(self):
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("使用 S3 存储需要安装 boto3") from exc

        if not settings.S3_BUCKET:
            raise RuntimeError("S3_BUCKET 未配置")
        self.bucket = settings.S3_BUCKET
        self.public_base_url = (settings.S3_PUBLIC_BASE_URL or "").rstrip("/")
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL or None,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY or None,
            region_name=settings.S3_REGION or None,
        )

    def upload(self, file_content: bytes, filename: str) -> str:
        ext = validate_upload(file_content, filename)
        date_folder = datetime.now().strftime("%Y%m%d")
        object_key = f"uploads/{date_folder}/{uuid.uuid4().hex}{ext}"
        self.client.put_object(Bucket=self.bucket, Key=object_key, Body=file_content)
        if self.public_base_url:
            return f"{self.public_base_url}/{object_key}"
        return f"s3://{self.bucket}/{object_key}"

    def delete(self, path: str) -> bool:
        object_key = _extract_s3_key(path, self.bucket, self.public_base_url)
        if not object_key:
            return False
        self.client.delete_object(Bucket=self.bucket, Key=object_key)
        return True


class StorageService:
    """存储服务管理器"""

    _instance = None

    def __init__(self, provider: BaseStorageProvider):
        self.provider = provider

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            provider_name = settings.STORAGE_PROVIDER.strip().lower()
            provider = S3StorageProvider() if provider_name in {"s3", "oss"} else LocalStorageProvider()
            cls._instance = cls(provider)
        return cls._instance

    def upload(self, file_content: bytes, filename: str) -> str:
        return self.provider.upload(file_content, filename)

    def delete(self, path: str) -> bool:
        return self.provider.delete(path)


def _extract_s3_key(path: str, bucket: str, public_base_url: str) -> str | None:
    if public_base_url and path.startswith(public_base_url):
        return path.removeprefix(public_base_url).lstrip("/")
    prefix = f"s3://{bucket}/"
    if path.startswith(prefix):
        return path.removeprefix(prefix)
    if path.startswith("uploads/"):
        return path
    return None
