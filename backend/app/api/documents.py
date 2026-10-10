"""
文档管理API路由
"""
import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.api.deps import get_current_user
from app.models.schemas import DocumentResponse, MessageResponse
from app.models.user import User
from app.services.document import document_service
from app.services.rag import rag_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_response(record: dict) -> DocumentResponse:
    return DocumentResponse(
        id=record["id"],
        filename=record.get("filename", ""),
        size=int(record.get("size", 0)),
        created_at=float(record.get("created_at", 0)),
        modified_at=float(record.get("modified_at", 0)),
        status=record.get("status", "processed"),
        chunks=int(record.get("chunks", 0)),
        file_type=record.get("file_type", ""),
    )


@router.post("/upload", response_model=DocumentResponse, summary="上传文档")
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    filename = file.filename or ""
    content = await file.read()

    is_valid, error_msg = document_service.validate_file(filename, len(content))
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    # 内容相同(哈希一致)的文档直接复用, 避免重复入库
    existing = None
    file_path, file_hash = await document_service.save_file(content, filename)
    existing = document_service.get_document(file_hash)
    if existing is not None:
        return _to_response(existing)

    try:
        text = await document_service.parse_document(file_path, filename)
    except ValueError as exc:
        await document_service.delete_file(file_hash)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await document_service.delete_file(file_hash)
        logger.exception("解析文档失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"文档解析失败: {exc}"
        ) from exc

    metadata = {
        "source": Path(filename).name,
        "file_hash": file_hash,
        "file_type": file_path.suffix.lstrip("."),
    }

    try:
        chunk_ids = await run_in_threadpool(rag_service.add_document, text, metadata)
    except Exception as exc:  # noqa: BLE001
        await document_service.delete_file(file_hash)
        logger.exception("文档入库失败")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"文档入库失败: {exc}"
        ) from exc

    record = document_service.register_document(
        doc_id=file_hash,
        filename=filename,
        size=len(content),
        file_path=file_path,
        chunks=len(chunk_ids),
    )
    return _to_response(record)


@router.get("", response_model=List[DocumentResponse], summary="获取文档列表")
@router.get("/", response_model=List[DocumentResponse], include_in_schema=False)
async def list_documents(current_user: User = Depends(get_current_user)):
    return [_to_response(record) for record in document_service.list_documents()]


@router.get("/stats", summary="知识库统计信息")
async def knowledge_base_stats(current_user: User = Depends(get_current_user)):
    stats = rag_service.stats()
    stats["documents"] = document_service.count()
    return stats


@router.delete("/{document_id}", response_model=MessageResponse, summary="删除文档")
async def delete_document(document_id: str, current_user: User = Depends(get_current_user)):
    record = document_service.get_document(document_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    try:
        await run_in_threadpool(rag_service.delete_by_file_hash, document_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("删除向量数据失败")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"删除向量数据失败: {exc}"
        ) from exc

    await document_service.remove_document(document_id)
    return MessageResponse(message="文档删除成功")


@router.post("/clear", response_model=MessageResponse, summary="清空所有文档")
async def clear_all_documents(current_user: User = Depends(get_current_user)):
    try:
        await run_in_threadpool(rag_service.clear)
    except Exception as exc:  # noqa: BLE001
        logger.exception("清空向量库失败")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"清空向量库失败: {exc}"
        ) from exc

    await document_service.clear_all()
    return MessageResponse(message="所有文档已清空")