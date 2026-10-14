"""
文档处理服务

负责上传文件的保存、解析、元数据管理与删除。
元数据(原始文件名、大小、上传时间、片段数)持久化在 uploads/.metadata.json。
"""
import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiofiles
import pymupdf

from app.core.config import settings

logger = logging.getLogger(__name__)

_METADATA_FILENAME = ".metadata.json"


class DocumentService:
    def __init__(self):
        self.upload_dir = settings.upload_path
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self._metadata_file = self.upload_dir / _METADATA_FILENAME
        self._lock = threading.RLock()
        self._metadata: Dict[str, dict] = self._load_metadata()

    # ==================== 元数据 ====================
    def _load_metadata(self) -> Dict[str, dict]:
        if not self._metadata_file.exists():
            return {}
        try:
            with self._metadata_file.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("读取文档元数据失败: %s", exc)
            return {}

    def _save_metadata(self) -> None:
        tmp = self._metadata_file.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fp:
            json.dump(self._metadata, fp, ensure_ascii=False, indent=2)
        tmp.replace(self._metadata_file)

    def _set_record(self, doc_id: str, record: dict) -> None:
        with self._lock:
            self._metadata[doc_id] = record
            self._save_metadata()

    def _pop_record(self, doc_id: str) -> Optional[dict]:
        with self._lock:
            record = self._metadata.pop(doc_id, None)
            if record is not None:
                self._save_metadata()
            return record

    # ==================== 工具方法 ====================
    @staticmethod
    def _get_file_hash(file_content: bytes) -> str:
        return hashlib.md5(file_content).hexdigest()

    @staticmethod
    def _get_file_extension(filename: str) -> str:
        return Path(filename or "").suffix.lower()

    @staticmethod
    def _safe_original_name(filename: str) -> str:
        name = Path(filename or "").name
        return name or "unknown"

    # ==================== 校验与保存 ====================
    def validate_file(self, filename: str, file_size: int) -> Tuple[bool, Optional[str]]:
        if not filename:
            return False, "文件名不能为空"

        extension = self._get_file_extension(filename)
        if extension not in settings.allowed_extensions:
            allowed = ", ".join(sorted(settings.allowed_extensions))
            return False, f"不支持的文件格式: {extension or '(无扩展名)'}，仅支持: {allowed}"

        if file_size <= 0:
            return False, "文件内容为空"

        if file_size > settings.MAX_FILE_SIZE:
            return False, f"文件过大: {file_size / (1024 * 1024):.1f}MB，最大允许 {settings.MAX_FILE_SIZE / (1024 * 1024):.0f}MB"

        return True, None

    @staticmethod
    def build_document_id(owner_id: int, file_hash: str) -> str:
        """文档 ID 由 上传用户 + 内容哈希 组成, 保证用户之间相互隔离"""
        return f"{int(owner_id)}:{file_hash}"

    def delete_path(self, file_path: Path) -> None:
        """删除单个文件(用于上传流程失败时回滚)。同步阻塞, 调用方应放入线程池。"""
        try:
            if file_path.is_file() and file_path.name != _METADATA_FILENAME:
                file_path.unlink()
        except OSError as exc:
            logger.warning("删除文件失败 %s: %s", file_path, exc)

    async def save_file(
        self, file_content: bytes, filename: str, owner_id: int
    ) -> Tuple[Path, str]:
        file_hash = self._get_file_hash(file_content)
        # 存储文件名同样按用户隔离, 避免不同用户互相覆盖
        safe_filename = f"{int(owner_id)}_{file_hash}{self._get_file_extension(filename)}"
        file_path = self.upload_dir / safe_filename

        async with aiofiles.open(file_path, "wb") as fp:
            await fp.write(file_content)

        return file_path, file_hash

    # ==================== 解析 ====================
    async def parse_pdf_pages(self, file_path: Path) -> List[Tuple[int, str]]:
        """按页解析 PDF, 返回 [(页码, 文本), ...], 页码从 1 开始"""

        def _read() -> List[Tuple[int, str]]:
            pages: List[Tuple[int, str]] = []
            with pymupdf.open(file_path) as document:
                for number, page in enumerate(document, start=1):
                    pages.append((number, page.get_text()))
            return pages

        import asyncio

        return await asyncio.to_thread(_read)

    async def parse_pdf(self, file_path: Path) -> str:
        pages = await self.parse_pdf_pages(file_path)
        return "\n".join(text for _, text in pages)

    async def parse_txt(self, file_path: Path) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
            try:
                async with aiofiles.open(file_path, "r", encoding=encoding) as fp:
                    return await fp.read()
            except UnicodeDecodeError:
                continue
        # 兜底: 忽略无法解码的字符
        async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as fp:
            return await fp.read()

    async def parse_document_pages(
        self, file_path: Path, filename: str
    ) -> List[Tuple[Optional[int], str]]:
        """
        解析文档并保留页码: PDF 返回 [(页码, 文本), ...]; TXT/MD 无页概念, 返回 [(None, 文本)]。
        """
        extension = self._get_file_extension(filename)
        if extension == ".pdf":
            pages: List[Tuple[Optional[int], str]] = list(await self.parse_pdf_pages(file_path))
        elif extension in (".txt", ".md"):
            pages = [(None, await self.parse_txt(file_path))]
        else:
            raise ValueError(f"不支持的文件格式: {extension}")

        if not any(text and text.strip() for _, text in pages):
            raise ValueError("文档解析结果为空，请确认文件内容")
        return pages

    async def parse_document(self, file_path: Path, filename: str) -> str:
        pages = await self.parse_document_pages(file_path, filename)
        return "\n".join(text for _, text in pages)

    # ==================== 记录管理 ====================
    def register_document(
        self,
        doc_id: str,
        owner_id: int,
        file_hash: str,
        filename: str,
        size: int,
        file_path: Path,
        chunks: int,
        status: str = "processed",
    ) -> dict:
        stat = file_path.stat()
        record = {
            "id": doc_id,
            "owner_id": int(owner_id),
            "file_hash": file_hash,
            "filename": self._safe_original_name(filename),
            "size": size,
            "file_type": self._get_file_extension(filename).lstrip("."),
            "stored_name": file_path.name,
            "created_at": stat.st_ctime,
            "modified_at": stat.st_mtime,
            "chunks": chunks,
            "status": status,
        }
        self._set_record(doc_id, record)
        return record

    def list_documents(self, owner_id: int) -> List[dict]:
        with self._lock:
            records = [
                item for item in self._metadata.values()
                if int(item.get("owner_id", -1)) == int(owner_id)
            ]
        records.sort(key=lambda item: item.get("created_at", 0), reverse=True)
        return records

    def get_document(self, doc_id: str) -> Optional[dict]:
        with self._lock:
            return self._metadata.get(doc_id)

    def count(self, owner_id: int) -> int:
        with self._lock:
            return sum(
                1 for item in self._metadata.values()
                if int(item.get("owner_id", -1)) == int(owner_id)
            )

    def delete_file(self, doc_id: str) -> bool:
        record = self.get_document(doc_id)
        candidates = []
        if record and record.get("stored_name"):
            candidates.append(self.upload_dir / record["stored_name"])

        deleted = False
        for file_path in candidates:
            try:
                if file_path.is_file() and file_path.name != _METADATA_FILENAME:
                    file_path.unlink()
                    deleted = True
            except OSError as exc:
                logger.warning("删除文件失败 %s: %s", file_path, exc)
        return deleted

    def remove_document(self, doc_id: str) -> bool:
        """删除文件与元数据记录。同步阻塞, 调用方应放入线程池。"""
        existed = self.get_document(doc_id) is not None
        self.delete_file(doc_id)
        self._pop_record(doc_id)
        return existed

    def clear_all(self, owner_id: int) -> None:
        """清空某用户的文档与文件。同步阻塞, 调用方应放入线程池。"""
        import shutil

        with self._lock:
            removable = [
                (doc_id, item) for doc_id, item in self._metadata.items()
                if int(item.get("owner_id", -1)) == int(owner_id)
            ]
            for doc_id, _ in removable:
                self._metadata.pop(doc_id, None)

            for _, item in removable:
                stored_name = item.get("stored_name")
                if not stored_name:
                    continue
                file_path = self.upload_dir / stored_name
                try:
                    if file_path.is_dir():
                        shutil.rmtree(file_path, ignore_errors=True)
                    elif file_path.is_file():
                        file_path.unlink()
                except OSError as exc:
                    logger.warning("清理文件失败 %s: %s", file_path, exc)
            self._save_metadata()

    def touch(self) -> None:
        """确保上传目录存在"""
        self.upload_dir.mkdir(parents=True, exist_ok=True)


# 全局文档服务实例
document_service = DocumentService()