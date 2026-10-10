"""
向量存储服务

提供两种实现, 通过 VECTOR_STORE_MODE 配置切换:
- LocalVectorStore: 纯 Python 实现, 数据落盘为 JSON, 无需任何外部服务(默认)
- QdrantVectorStore: 基于 qdrant-client, 连接独立的 Qdrant 服务(docker-compose 中提供)

auto 模式: 优先尝试连接 Qdrant 服务, 不可用时自动回退到本地实现。
"""
import json
import logging
import math
import threading
from pathlib import Path
from typing import Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

logger = logging.getLogger(__name__)

_QDRANT_PROBE_TIMEOUT = 3


# ======================================================================
# 本地实现
# ======================================================================
class LocalVectorStore:
    """基于 JSON 文件的本地向量库, 使用余弦相似度做暴力检索"""

    backend = "local"

    def __init__(self, dimension: int, collection_name: str, data_dir: Path):
        self.dimension = dimension
        self.collection_name = collection_name
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.data_dir / f"{collection_name}.json"
        self._lock = threading.RLock()
        self._points: Dict[str, dict] = {}
        self._load()

    # ---------------- 持久化 ----------------
    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("读取本地向量库失败, 将以空索引启动: %s", exc)
            return

        stored_dim = data.get("dimension")
        if stored_dim and int(stored_dim) != self.dimension:
            logger.warning(
                "本地向量库维度(%s)与当前配置(%s)不一致, 已忽略旧数据",
                stored_dim, self.dimension,
            )
            self._points = {}
            return

        points = data.get("points") or {}
        loaded = {}
        for point_id, item in points.items():
            vector = item.get("vector") or []
            if len(vector) != self.dimension:
                continue
            loaded[str(point_id)] = {
                "vector": vector,
                "payload": item.get("payload") or {},
            }
        self._points = loaded

    def _save(self) -> None:
        payload = {
            "dimension": self.dimension,
            "collection": self.collection_name,
            "points": self._points,
        }
        tmp = self._file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._file)

    # ---------------- 生命周期 ----------------
    def ensure_collection(self) -> None:
        return

    def close(self) -> None:
        return

    # ---------------- 写入 ----------------
    def upsert(self, ids: List[str], vectors: List[List[float]], payloads: List[Dict]) -> None:
        with self._lock:
            for point_id, vector, payload in zip(ids, vectors, payloads):
                self._points[str(point_id)] = {
                    "vector": [round(float(value), 6) for value in vector],
                    "payload": payload,
                }
            self._save()

    def delete_ids(self, ids: List[str]) -> None:
        if not ids:
            return
        with self._lock:
            for point_id in ids:
                self._points.pop(str(point_id), None)
            self._save()

    def delete_by_file_hash(self, file_hash: str) -> None:
        with self._lock:
            removable = [
                point_id
                for point_id, item in self._points.items()
                if ((item.get("payload") or {}).get("metadata") or {}).get("file_hash") == file_hash
            ]
            for point_id in removable:
                self._points.pop(point_id, None)
            if removable:
                self._save()

    def clear(self) -> None:
        with self._lock:
            self._points = {}
            try:
                if self._file.exists():
                    self._file.unlink()
            except OSError as exc:
                logger.warning("删除本地向量库文件失败: %s", exc)

    # ---------------- 查询 ----------------
    def search(self, vector: List[float], top_k: int) -> List[Dict]:
        with self._lock:
            items = [(point_id, dict(item)) for point_id, item in self._points.items()]

        scored = []
        for point_id, item in items:
            score = self._cosine(vector, item.get("vector") or [])
            scored.append((point_id, score, item.get("payload") or {}))

        scored.sort(key=lambda entry: entry[1], reverse=True)
        return [
            {"id": point_id, "score": score, "payload": payload}
            for point_id, score, payload in scored[: max(top_k, 0)]
        ]

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = 0.0
        norm_a = 0.0
        norm_b = 0.0
        for x, y in zip(a, b):
            dot += x * y
            norm_a += x * x
            norm_b += y * y
        if norm_a <= 0.0 or norm_b <= 0.0:
            return 0.0
        return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))

    def scroll_all(self) -> List[Dict]:
        with self._lock:
            return [
                {"id": point_id, "payload": item.get("payload") or {}}
                for point_id, item in self._points.items()
            ]

    def count(self) -> int:
        with self._lock:
            return len(self._points)


# ======================================================================
# Qdrant 实现
# ======================================================================
class QdrantVectorStore:
    """基于 Qdrant 服务的向量库"""

    backend = "qdrant"

    def __init__(self, dimension: int, collection_name: str, host: str, port: int):
        self.dimension = dimension
        self.collection_name = collection_name
        self.host = host
        self.port = port
        self._client = QdrantClient(
            host=host, port=port, timeout=_QDRANT_PROBE_TIMEOUT,
            prefer_grpc=False, check_compatibility=False,
        )
        # 触发一次真实请求以确认服务可用
        self._client.get_collections()

    def ensure_collection(self) -> None:
        collections = {item.name for item in self._client.get_collections().collections}
        if self.collection_name in collections:
            size = self._current_vector_size()
            if size is None or size == self.dimension:
                return
            logger.warning(
                "集合 %s 维度(%s)与当前配置(%s)不一致, 正在重建",
                self.collection_name, size, self.dimension,
            )
            self._client.delete_collection(self.collection_name)

        self._client.create_collection(
            collection_name=self.collection_name,
            vectors_config=qmodels.VectorParams(
                size=self.dimension, distance=qmodels.Distance.COSINE
            ),
        )

    def _current_vector_size(self) -> Optional[int]:
        try:
            info = self._client.get_collection(self.collection_name)
            vectors = info.config.params.vectors
            size = getattr(vectors, "size", None)
            if size is None and isinstance(vectors, dict):
                size = vectors.get("size")
            return int(size) if size else None
        except Exception:
            return None

    def upsert(self, ids: List[str], vectors: List[List[float]], payloads: List[Dict]) -> None:
        points = [
            qmodels.PointStruct(id=point_id, vector=vector, payload=payload)
            for point_id, vector, payload in zip(ids, vectors, payloads)
        ]
        if points:
            self._client.upsert(collection_name=self.collection_name, points=points)

    def delete_ids(self, ids: List[str]) -> None:
        if ids:
            self._client.delete(collection_name=self.collection_name, points_selector=list(ids))

    def delete_by_file_hash(self, file_hash: str) -> None:
        self._client.delete(
            collection_name=self.collection_name,
            points_selector=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="metadata.file_hash",
                        match=qmodels.MatchValue(value=file_hash),
                    )
                ]
            ),
        )

    def scroll_all(self) -> List[Dict]:
        records: List[Dict] = []
        offset = None
        while True:
            points, offset = self._client.scroll(
                collection_name=self.collection_name,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                records.append({"id": str(point.id), "payload": point.payload or {}})
            if offset is None:
                break
        return records

    def search(self, vector: List[float], top_k: int) -> List[Dict]:
        response = self._client.query_points(
            collection_name=self.collection_name,
            query=vector,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        return [
            {"id": str(point.id), "score": float(point.score), "payload": point.payload or {}}
            for point in response.points
        ]

    def count(self) -> int:
        try:
            return int(self._client.count(self.collection_name).count)
        except Exception:
            return 0

    def clear(self) -> None:
        self._client.delete_collection(self.collection_name)
        self._client.create_collection(
            collection_name=self.collection_name,
            vectors_config=qmodels.VectorParams(
                size=self.dimension, distance=qmodels.Distance.COSINE
            ),
        )

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass


# ======================================================================
# 工厂
# ======================================================================
def create_vector_store(
    dimension: int,
    collection_name: str,
    mode: str = "auto",
    host: str = "localhost",
    port: int = 6333,
    data_dir: Optional[Path] = None,
):
    """根据模式创建向量库实例"""
    mode = (mode or "auto").strip().lower()

    if mode == "qdrant":
        logger.info("连接 Qdrant 服务 %s:%s", host, port)
        return QdrantVectorStore(dimension, collection_name, host, port)

    if mode == "auto":
        try:
            store = QdrantVectorStore(dimension, collection_name, host, port)
            logger.info("已连接 Qdrant 服务 %s:%s", host, port)
            return store
        except Exception as exc:  # noqa: BLE001
            logger.info("未检测到可用的 Qdrant 服务(%s), 使用本地向量库", exc)

    logger.info("使用本地向量库, 数据目录: %s", data_dir)
    return LocalVectorStore(dimension, collection_name, data_dir or Path("./data"))