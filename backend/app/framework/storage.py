import os
import shutil
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from app.core.config import settings


class BaseStorageProvider(ABC):
    """
    存储提供者抽象基类
    """
    @abstractmethod
    def upload(self, file_content: bytes, filename: str) -> str:
        """上传文件并返回访问路径"""
        pass

    @abstractmethod
    def delete(self, path: str) -> bool:
        """删除文件"""
        pass


class LocalStorageProvider(BaseStorageProvider):
    """
    本地文件存储提供者
    """
    def __init__(self, upload_dir: str = "data/uploads", base_url: str = "/uploads"):
        self.upload_dir = upload_dir
        self.base_url = base_url
        if not os.path.exists(self.upload_dir):
            os.makedirs(self.upload_dir)

    def upload(self, file_content: bytes, filename: str) -> str:
        # 生成唯一文件名
        ext = os.path.splitext(filename)[1]
        date_folder = datetime.now().strftime("%Y%m%d")
        dest_dir = os.path.join(self.upload_dir, date_folder)
        
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
            
        unique_filename = f"{uuid.uuid4().hex}{ext}"
        dest_path = os.path.join(dest_dir, unique_filename)
        
        with open(dest_path, "wb") as f:
            f.write(file_content)
            
        return f"{self.base_url}/{date_folder}/{unique_filename}"

    def delete(self, path: str) -> bool:
        # 简单实现路径转换
        relative_path = path.replace(self.base_url, "").lstrip("/")
        full_path = os.path.join(self.upload_dir, relative_path)
        if os.path.exists(full_path):
            os.remove(full_path)
            return True
        return False


class StorageService:
    """
    存储服务管理器
    """
    _instance = None

    def __init__(self, provider: BaseStorageProvider):
        self.provider = provider

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            # 默认使用本地存储，后续可根据 settings 切换为 OSS 等
            cls._instance = cls(LocalStorageProvider())
        return cls._instance

    def upload(self, file_content: bytes, filename: str) -> str:
        return self.provider.upload(file_content, filename)

    def delete(self, path: str) -> bool:
        return self.provider.delete(path)
