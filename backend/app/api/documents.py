"""
文档管理API路由

文档按用户隔离: 每个用户只能看到 / 操作自己上传的文档, 检索时也只召回自己的文档。
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


def _owned_record(document_id: str, current_user: User):
    """取出属于当前用户的文档记录, 不存在或不属于当前用户时返回 None"""
    record = document_service.get_document(document_id)
    if record is None:
        return None
    if int(record.get("owner_id", -1)) != int(current_user.id):
        return None
    return record


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

    owner_id = int(current_user.id)
    file_path, file_hash = await document_service.save_file(content, filename, owner_id)
    doc_id = document_service.build_document_id(owner_id, file_hash)

    # 同一用户重复上传相同内容时直接复用, 避免重复入库
    existing = document_service.get_document(doc_id)
    if existing is not None:
        return _to_response(existing)

    try:
        text = await document_service.parse_document(file_path, filename)
    except ValueError as exc:
        await document_service.delete_path(file_path)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:  # noqa: BLE001
        await document_service.delete_path(file_path)
        logger.exception("解析文档失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="文档解析失败，请确认文件内容后重试",
        ) from None

    metadata = {
        "source": Path(filename).name,
        "file_hash": file_hash,
        "file_type": file_path.suffix.lstrip("."),
        "owner_id": owner_id,
    }

    try:
        chunk_ids = await run_in_threadpool(rag_service.add_document, text, metadata)
    except Exception:  # noqa: BLE001
        await document_service.delete_path(file_path)
        logger.exception("文档入库失败")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="文档入库失败，请稍后重试",
        ) from None

    record = document_service.register_document(
        doc_id=doc_id,
        owner_id=owner_id,
        file_hash=file_hash,
        filename=filename,
        size=len(content),
        file_path=file_path,
        chunks=len(chunk_ids),
    )
    return _to_response(record)


@router.get("", response_model=List[DocumentResponse], summary="获取文档列表")
@router.get("/", response_model=List[DocumentResponse], include_in_schema=False)
async def list_documents(current_user: User = Depends(get_current_user)):
    records = document_service.list_documents(int(current_user.id))
    return [_to_response(record) for record in records]


@router.get("/stats", summary="知识库统计信息")
async def knowledge_base_stats(current_user: User = Depends(get_current_user)):
    stats = rag_service.stats()
    stats["documents"] = document_service.count(int(current_user.id))
    stats["vector_points"] = rag_service.count_owner(int(current_user.id))
    return stats


@router.delete("/{document_id}", response_model=MessageResponse, summary="删除文档")
async def delete_document(document_id: str, current_user: User = Depends(get_current_user)):
    record = _owned_record(document_id, current_user)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    try:
        await run_in_threadpool(
            rag_service.delete_document,
            int(current_user.id),
            str(record.get("file_hash") or ""),
        )
    except Exception:  # noqa: BLE001
        logger.exception("删除向量数据失败")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="删除向量数据失败，请稍后重试",
        ) from None

    await document_service.remove_document(document_id)
    return MessageResponse(message="文档删除成功")


@router.post("/clear", response_model=MessageResponse, summary="清空所有文档")
async def clear_all_documents(current_user: User = Depends(get_current_user)):
    try:
        await run_in_threadpool(rag_service.clear_owner, int(current_user.id))
    except Exception:  # noqa: BLE001
        logger.exception("清空向量库失败")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="清空向量库失败，请稍后重试",
        ) from None

    await document_service.clear_all(int(current_user.id))
    return MessageResponse(message="所有文档已清空")