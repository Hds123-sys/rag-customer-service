"""
向量化服务

提供两种实现:
- LocalHashingEmbeddings: 内置离线算法(特征哈希 + TF 加权 + L2 归一化), 无需外部服务
- OpenAICompatEmbeddings: 调用 OpenAI 兼容的 /v1/embeddings 接口

可通过 EMBEDDING_PROVIDER 配置项切换。
"""
import hashlib
import logging
import math
from typing import List, Sequence

import httpx

from app.core.config import settings
from app.services.openai_api import normalize_base_url
from app.services.text_utils import extract_features

logger = logging.getLogger(__name__)


class BaseEmbeddings:
    """向量化基类"""

    @property
    def dimension(self) -> int:
        raise NotImplementedError

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        raise NotImplementedError


class LocalHashingEmbeddings(BaseEmbeddings):
    """
    内置离线向量化: 将文本的字符 n-gram / 单词特征哈希到固定维度空间,
    使用 TF 加权并做 L2 归一化, 得到的向量可用于余弦相似度检索。
    """

    def __init__(self, dimension: int = 1024):
        if dimension <= 0:
            raise ValueError("EMBEDDING_DIM 必须大于 0")
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_query(self, text: str) -> List[float]:
        return self._embed(text)

    def _embed(self, text: str) -> List[float]:
        vector = [0.0] * self._dimension

        counts = {}
        for feature, weight in extract_features(text):
            counts[feature] = counts.get(feature, 0.0) + weight

        if not counts:
            return vector

        for feature, total in counts.items():
            tf = 1.0 + math.log(total)
            index = self._hash_index(feature)
            vector[index] += self._hash_sign(feature) * tf

        norm = math.sqrt(sum(value * value for value in vector))
        if norm > 0:
            vector = [value / norm for value in vector]
        return vector

    def _hash_index(self, feature: str) -> int:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") % self._dimension

    @staticmethod
    def _hash_sign(feature: str) -> float:
        digest = hashlib.blake2b(
            feature.encode("utf-8"), digest_size=1, person=b"RAG-sign"
        ).digest()
        return 1.0 if digest[0] & 1 else -1.0


class OpenAICompatEmbeddings(BaseEmbeddings):
    """调用 OpenAI 兼容 /v1/embeddings 接口的向量化实现"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        batch_size: int = 32,
    ):
        self.base_url = normalize_base_url(base_url)
        self.api_key = api_key or ""
        self.model = model
        self.timeout = timeout
        self.batch_size = max(1, batch_size)
        self._dimension: int = 0

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/embeddings"

    @property
    def dimension(self) -> int:
        if self._dimension <= 0:
            self.embed_query("dimension probe")
        return self._dimension

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        results: List[List[float]] = []
        texts = list(texts)
        for start in range(0, len(texts), self.batch_size):
            results.extend(self._request(texts[start:start + self.batch_size]))
        return results

    def embed_query(self, text: str) -> List[float]:
        return self._request([text])[0]

    def _request(self, texts: List[str]) -> List[List[float]]:
        if not self.api_key:
            raise RuntimeError("未配置 EMBEDDING_API_KEY, 无法调用向量化接口")

        payload = {"model": self.model, "input": texts}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(self.endpoint, headers=headers, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(
                f"向量化接口返回 {response.status_code}: {response.text[:300]}"
            )

        data = response.json()
        items = data.get("data") or []
        if len(items) != len(texts):
            raise RuntimeError("向量化接口返回的数据条数与请求不一致")

        items = sorted(items, key=lambda item: item.get("index", 0))
        vectors = [item["embedding"] for item in items]
        if vectors and self._dimension <= 0:
            self._dimension = len(vectors[0])
        return vectors


def build_embeddings() -> BaseEmbeddings:
    """根据配置构建向量化实现"""
    provider = (settings.EMBEDDING_PROVIDER or "local").strip().lower()
    if provider == "openai":
        logger.info("使用 OpenAI 兼容向量化接口: %s", settings.EMBEDDING_MODEL)
        return OpenAICompatEmbeddings(
            base_url=settings.EMBEDDING_API_BASE_URL,
            api_key=settings.EMBEDDING_API_KEY,
            model=settings.EMBEDDING_MODEL,
        )
    logger.info("使用内置离线向量化, 维度=%s", settings.EMBEDDING_DIM)
    return LocalHashingEmbeddings(dimension=settings.EMBEDDING_DIM)