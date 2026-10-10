"""
RAG 核心服务

流程: 文档切分 -> 向量化 -> 向量库存储 -> 混合检索(向量 + BM25 关键词) -> 大模型生成答案
"""
import logging
import math
import threading
import uuid
from collections import Counter
from typing import Dict, List, Optional

from app.core.config import settings
from app.services.embeddings import BaseEmbeddings, build_embeddings
from app.services.openai_api import ChatClient
from app.services.text_splitter import RecursiveTextSplitter
from app.services.text_utils import clean_preview, tokenize
from app.services.vectorstore import create_vector_store

logger = logging.getLogger(__name__)

_BM25_K1 = 1.5
_BM25_B = 0.75

SYSTEM_PROMPT = (
    "你是一个专业、友好的智能客服助手。请严格依据提供的【参考信息】回答用户问题。\n"
    "要求:\n"
    "1. 答案必须基于参考信息, 不要编造参考信息中不存在的内容;\n"
    "2. 如果参考信息不足以回答问题, 请明确说明「根据现有资料无法回答该问题」并给出可行的建议;\n"
    "3. 使用简洁、条理清晰的中文回答;\n"
    "4. 使用纯文本作答, 不要使用 Markdown 语法(例如 ** 加粗、## 标题、``` 代码块); "
    "需要分点时请使用 1. 2. 3. 或「- 」开头, 需要强调时可使用「」或【】。"
)


class RAGService:
    def __init__(self):
        self.ready = False
        self.init_error: Optional[str] = None

        self.embeddings: Optional[BaseEmbeddings] = None
        self.vector_store = None
        self.llm: Optional[ChatClient] = None
        self.splitter = RecursiveTextSplitter(
            chunk_size=settings.CHUNK_SIZE, chunk_overlap=settings.CHUNK_OVERLAP
        )
        self.dimension = 0

        self._lock = threading.RLock()
        self._documents: Dict[str, dict] = {}
        self._term_freq: Dict[str, Counter] = {}
        self._doc_length: Dict[str, int] = {}
        self._doc_freq: Counter = Counter()
        self._avg_length = 0.0

        self._initialize()

    # ==================== 初始化 ====================
    def _initialize(self) -> None:
        try:
            self.embeddings = build_embeddings()
            self.dimension = self.embeddings.dimension
            self.vector_store = create_vector_store(
                dimension=self.dimension,
                collection_name=settings.QDRANT_COLLECTION_NAME,
                mode=settings.VECTOR_STORE_MODE,
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                data_dir=settings.vector_store_path,
            )
            self.vector_store.ensure_collection()
            self.llm = ChatClient(
                base_url=settings.API_BASE_URL,
                api_key=settings.API_KEY,
                model=settings.API_MODEL,
                temperature=settings.TEMPERATURE,
                timeout=settings.API_TIMEOUT,
            )
            self._rebuild_lexical_index()
            self.ready = True
            self.init_error = None
            logger.info(
                "RAG 服务就绪: 向量库=%s, 维度=%s, 文档片段=%s, 模型=%s",
                self.vector_store.backend, self.dimension,
                self.vector_store.count(), settings.API_MODEL,
            )
        except Exception as exc:  # noqa: BLE001 - 需要捕获所有初始化异常
            self.ready = False
            self.init_error = str(exc)
            logger.exception("RAG 服务初始化失败: %s", exc)

    def ensure_ready(self) -> None:
        if not self.ready:
            raise RuntimeError(f"RAG 服务未就绪: {self.init_error}")

    # ==================== 词法索引 ====================
    def _rebuild_lexical_index(self) -> None:
        assert self.vector_store is not None
        records = self.vector_store.scroll_all()

        documents: Dict[str, dict] = {}
        term_freq: Dict[str, Counter] = {}
        doc_length: Dict[str, int] = {}
        doc_freq: Counter = Counter()

        for record in records:
            payload = record.get("payload") or {}
            text = payload.get("text") or ""
            metadata = payload.get("metadata") or {}
            tokens = tokenize(text)
            documents[record["id"]] = {"text": text, "metadata": metadata}
            term_freq[record["id"]] = Counter(tokens)
            doc_length[record["id"]] = len(tokens)
            for token in set(tokens):
                doc_freq[token] += 1

        with self._lock:
            self._documents = documents
            self._term_freq = term_freq
            self._doc_length = doc_length
            self._doc_freq = doc_freq
            self._avg_length = (
                sum(doc_length.values()) / len(doc_length) if doc_length else 0.0
            )

    # ==================== 写入 ====================
    def add_document(self, text: str, metadata: dict) -> List[str]:
        """切分、向量化并写入文档, 返回片段ID列表"""
        self.ensure_ready()
        assert self.embeddings is not None and self.vector_store is not None

        chunks = self.splitter.split_text(text)
        if not chunks:
            raise ValueError("文档内容为空，无法切分")

        vectors = self.embeddings.embed_documents(chunks)
        ids = [str(uuid.uuid4()) for _ in chunks]
        payloads = []
        total = len(chunks)
        for index, (chunk, _vector) in enumerate(zip(chunks, vectors)):
            payloads.append({
                "text": chunk,
                "metadata": {
                    **metadata,
                    "chunk_index": index,
                    "chunk_total": total,
                },
            })

        self.vector_store.upsert(ids, vectors, payloads)
        self._rebuild_lexical_index()
        return ids

    def delete_document(self, owner_id: int, file_hash: str) -> None:
        """删除指定用户某个文档的全部片段"""
        self.ensure_ready()
        assert self.vector_store is not None
        self.vector_store.delete_matching(owner_id, file_hash)
        self._rebuild_lexical_index()

    def clear_owner(self, owner_id: int) -> None:
        """清空指定用户的知识库"""
        self.ensure_ready()
        assert self.vector_store is not None
        self.vector_store.clear_owner(owner_id)
        self._rebuild_lexical_index()

    # ==================== 检索 ====================
    def _bm25_scores(self, query: str) -> Dict[str, float]:
        tokens = tokenize(query)
        if not tokens:
            return {}

        with self._lock:
            documents = self._documents
            term_freq = self._term_freq
            doc_length = self._doc_length
            doc_freq = self._doc_freq
            avg_length = self._avg_length or 1.0
            total_docs = max(len(documents), 1)

        scores: Dict[str, float] = {}
        for token in set(tokens):
            freq = doc_freq.get(token, 0)
            if freq == 0:
                continue
            idf = math.log(1 + (total_docs - freq + 0.5) / (freq + 0.5))
            for doc_id, counter in term_freq.items():
                tf = counter.get(token, 0)
                if not tf:
                    continue
                length = doc_length.get(doc_id, 0)
                denominator = tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * length / avg_length)
                scores[doc_id] = scores.get(doc_id, 0.0) + idf * (tf * (_BM25_K1 + 1)) / denominator
        return scores

    def search(
        self, query: str, top_k: Optional[int] = None, owner_id: Optional[int] = None
    ) -> List[dict]:
        """混合检索: 向量相似度 + BM25 关键词(仅召回 owner_id 对应的文档)"""
        self.ensure_ready()
        assert self.embeddings is not None and self.vector_store is not None

        top_k = top_k or settings.TOP_K_RESULTS
        if self.vector_store.count() == 0:
            return []

        query_vector = self.embeddings.embed_query(query)
        vector_hits = self.vector_store.search(query_vector, top_k=max(top_k * 3, 10))
        vector_scores = {hit["id"]: max(0.0, hit["score"]) for hit in vector_hits}

        keyword_scores = self._bm25_scores(query)
        max_keyword = max(keyword_scores.values()) if keyword_scores else 0.0

        candidate_ids = set(vector_scores) | set(keyword_scores)
        if not candidate_ids:
            return []

        fused: List[tuple] = []
        with self._lock:
            documents = self._documents
            for doc_id in candidate_ids:
                document = documents.get(doc_id)
                if not document:
                    continue
                # 知识库按用户隔离: 只检索属于当前用户的文档
                if owner_id is not None:
                    metadata = document.get("metadata") or {}
                    if metadata.get("owner_id") != owner_id:
                        continue
                vector_score = vector_scores.get(doc_id, 0.0)
                keyword_score = (
                    keyword_scores.get(doc_id, 0.0) / max_keyword if max_keyword else 0.0
                )
                score = (
                    settings.VECTOR_WEIGHT * vector_score
                    + settings.KEYWORD_WEIGHT * keyword_score
                )
                fused.append((doc_id, score, vector_score, keyword_score))

        fused.sort(key=lambda item: item[1], reverse=True)
        fused = [item for item in fused if item[1] >= settings.MIN_SCORE][:top_k]

        results = []
        with self._lock:
            documents = self._documents
            for doc_id, score, vector_score, keyword_score in fused:
                document = documents.get(doc_id, {})
                metadata = document.get("metadata", {}) or {}
                results.append({
                    "id": doc_id,
                    "score": round(float(score), 4),
                    "vector_score": round(float(vector_score), 4),
                    "keyword_score": round(float(keyword_score), 4),
                    "filename": metadata.get("source", ""),
                    "chunk_index": int(metadata.get("chunk_index", 0)),
                    "text": clean_preview(document.get("text", ""), 300),
                    "full_text": document.get("text", ""),
                })
        return results

    # ==================== 生成 ====================
    def _build_context(self, results: List[dict]) -> str:
        parts = []
        used = 0
        for index, result in enumerate(results, start=1):
            block = f"[{index}] 来源: {result.get('filename') or '未知文档'}\n{result.get('full_text', '')}"
            if used + len(block) > settings.MAX_CONTEXT_LENGTH and parts:
                break
            parts.append(block)
            used += len(block)
        return "\n\n".join(parts)

    def generate_answer(self, query: str, results: List[dict], history: Optional[List[dict]] = None) -> str:
        assert self.llm is not None

        messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

        if history:
            max_turns = max(1, settings.CHAT_HISTORY_MAX_TURNS)
            for item in history[-max_turns * 2:]:
                role = item.get("role")
                content = (item.get("content") or "").strip()
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})

        context = self._build_context(results)
        if context:
            user_content = (
                f"【参考信息】\n{context}\n\n"
                f"【用户问题】\n{query}\n\n"
                "请基于上述参考信息作答。"
            )
        else:
            user_content = (
                "【参考信息】\n(知识库中没有检索到与该问题相关的内容)\n\n"
                f"【用户问题】\n{query}\n\n"
                "请说明暂时无法从资料中找到答案, 并给出建议。"
            )

        messages.append({"role": "user", "content": user_content})
        return self.llm.chat(messages)

    def chat(
        self,
        query: str,
        history: Optional[List[dict]] = None,
        owner_id: Optional[int] = None,
    ) -> dict:
        self.ensure_ready()
        results = self.search(query, owner_id=owner_id)
        answer = self.generate_answer(query, results, history)
        sources = [
            {
                "id": item["id"],
                "score": item["score"],
                "filename": item.get("filename", ""),
                "text": item.get("text", ""),
                "chunk_index": item.get("chunk_index", 0),
            }
            for item in results
        ]
        return {"answer": answer, "sources": sources}

    # ==================== 状态 ====================
    def count_owner(self, owner_id: int) -> int:
        """统计指定用户的向量片段数量"""
        with self._lock:
            return sum(
                1 for item in self._documents.values()
                if (item.get("metadata") or {}).get("owner_id") == owner_id
            )

    def stats(self) -> dict:
        return {
            "ready": self.ready,
            # 只暴露状态, 具体异常写日志, 避免把内部细节返回给客户端
            "error": "服务初始化失败, 请查看服务端日志" if self.init_error else None,
            "embedding_provider": settings.EMBEDDING_PROVIDER,
            "dimension": self.dimension,
            "vector_backend": self.vector_store.backend if self.vector_store else None,
            "vector_points": self.vector_store.count() if self.vector_store else 0,
            "model": settings.API_MODEL,
            "llm_configured": bool(self.llm and self.llm.is_configured),
        }

    def close(self) -> None:
        if self.vector_store:
            self.vector_store.close()


# 全局 RAG 服务实例
rag_service = RAGService()