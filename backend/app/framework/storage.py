import os
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from app.core.config import settings


class BaseStorageProvider(ABC):
    """存储提供者抽象基类"""

    @abstractmethod
    def upload(self, file_content: bytes, filename: str) -> str:
        """上传文件并返回访问路径"""
        pass

    @abstractmethod
    def save(self, file_content: bytes, filename: str) -> str:
        """保存已完成业务校验的文件并返回访问路径"""
        pass

    @abstractmethod
    def delete(self, path: str) -> bool:
        """删除文件"""
        pass

    @abstractmethod
    def read(self, path: str) -> bytes:
        """读取文件内容（按 save 返回的路径）"""
        pass


class UploadRejectedError(ValueError):
    """文件上传被拒绝"""


# 文件头 magic bytes 校验表
# - list：文件内容须以其中任一字节序列开头
# - None：需特殊校验逻辑（见 _check_magic_bytes）
# 未列入此表的扩展名（如纯文本 .txt/.csv/.json）跳过 magic bytes 校验，仅做扩展名白名单校验
# 注意：.doc/.xls/.ppt 共享 OLE2 容器头（\xd0\xcf\x11\xe0...）；未来若新增同容器扩展名
# （如 .msi/.msg）须同步在此登记，否则会因缺 magic 入口而仅靠扩展名白名单放行
_MAGIC_BYTES_TABLE: dict[str, list[bytes] | None] = {
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".gif": [b"GIF87a", b"GIF89a"],
    ".webp": None,  # RIFF....WEBP
    ".pdf": [b"%PDF"],
    ".zip": [b"PK\x03\x04"],
    ".docx": [b"PK\x03\x04"],
    ".xlsx": [b"PK\x03\x04"],
    ".pptx": [b"PK\x03\x04"],
    ".mp4": None,  # bytes[4:8] == b"ftyp"
    ".rar": [b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00"],
    ".mp3": None,  # ID3 标签或 MPEG 帧同步字，见 _check_magic_bytes
    ".doc": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    ".xls": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    ".ppt": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
}


def _check_magic_bytes(file_content: bytes, ext: str) -> bool:
    """校验文件头 magic bytes 是否与声明的扩展名匹配。"""
    if ext not in _MAGIC_BYTES_TABLE:
        # 纯文本等无固定 magic bytes 的类型：跳过校验
        return True

    entry = _MAGIC_BYTES_TABLE[ext]
    if entry is None:
        # 特殊校验：webp / mp4
        if ext == ".webp":
            return (
                len(file_content) >= 12
                and file_content[:4] == b"RIFF"
                and file_content[8:12] == b"WEBP"
            )
        if ext == ".mp4":
            return len(file_content) >= 8 and file_content[4:8] == b"ftyp"
        if ext == ".mp3":
            # ID3v2 标签开头，或 MPEG 帧同步字（首字节 0xFF，第二字节高 3 位须为 111），
            # 覆盖 0xFFFA/0xFFF2/0xFFE3 等所有合法 Layer III 帧头，避免合法 MP3 被误拒
            if file_content.startswith(b"ID3"):
                return True
            return (
                len(file_content) >= 2
                and file_content[0] == 0xFF
                and (file_content[1] & 0xE0) == 0xE0
            )
        return True

    return any(file_content.startswith(prefix) for prefix in entry)


def validate_upload(file_content: bytes, filename: str) -> str:
    """
    校验上传文件：类型白名单 + 大小限制 + magic bytes 校验。
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

    # 3. magic bytes 校验：文件头须与声明的扩展名匹配，防止伪装文件绕过白名单
    if not _check_magic_bytes(file_content, ext):
        raise UploadRejectedError(f"文件内容与声明的类型 {ext} 不匹配")

    return ext


DEFAULT_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "data" / "uploads"


class LocalStorageProvider(BaseStorageProvider):
    """本地文件存储提供者"""

    def __init__(self, upload_dir: str | None = None, base_url: str = "/uploads"):
        self.upload_dir = os.path.abspath(upload_dir or DEFAULT_UPLOAD_DIR)
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
        return self._save_with_ext(file_content, ext)

    def save(self, file_content: bytes, filename: str) -> str:
        ext = os.path.splitext(filename)[1].lower() or ".bin"
        return self._save_with_ext(file_content, ext)

    def _save_with_ext(self, file_content: bytes, ext: str) -> str:
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

    def read(self, path: str) -> bytes:
        relative_path = path.replace(self.base_url, "").lstrip("/")
        full_path = self._resolve_safe_path(relative_path)
        with open(full_path, "rb") as f:
            return f.read()


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
        return self._save_with_ext(file_content, ext)

    def save(self, file_content: bytes, filename: str) -> str:
        ext = os.path.splitext(filename)[1].lower() or ".bin"
        return self._save_with_ext(file_content, ext)

    def _save_with_ext(self, file_content: bytes, ext: str) -> str:
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

    def read(self, path: str) -> bytes:
        object_key = _extract_s3_key(path, self.bucket, self.public_base_url)
        if not object_key:
            raise ValueError(f"无法解析 S3 对象 key: {path}")
        response = self.client.get_object(Bucket=self.bucket, Key=object_key)
        return response["Body"].read()


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

    def save(self, file_content: bytes, filename: str) -> str:
        return self.provider.save(file_content, filename)

    def delete(self, path: str) -> bool:
        return self.provider.delete(path)

    def read(self, path: str) -> bytes:
        return self.provider.read(path)


def _extract_s3_key(path: str, bucket: str, public_base_url: str) -> str | None:
    if public_base_url and path.startswith(public_base_url):
        return path.removeprefix(public_base_url).lstrip("/")
    prefix = f"s3://{bucket}/"
    if path.startswith(prefix):
        return path.removeprefix(prefix)
    if path.startswith("uploads/"):
        return path
    return None


def offload_payload(content: str) -> tuple[str, str | None]:
    """T8：超阈值载荷落对象存储，返回 (inline_or_empty, storage_ref_or_None)。

    供 workflow 节点日志与评估 case 输出共用。载荷应由调用方提前脱敏。
    """
    if len(content.encode("utf-8")) <= settings.PAYLOAD_STORAGE_THRESHOLD:
        return content, None
    ref = StorageService.get_instance().save(
        content.encode("utf-8"), f"wf_payload_{uuid.uuid4().hex}.json"
    )
    return "", ref


def resolve_payload(content: str, ref: str | None) -> str:
    """T8 还原：ref 非空则从对象存储读回内容，否则原样返回 content。"""
    if ref:
        return StorageService.get_instance().read(ref).decode("utf-8")
    return content
