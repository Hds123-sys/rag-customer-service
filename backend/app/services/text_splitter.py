"""
文档切分器

按语义边界(段落 -> 换行 -> 句号 -> 逗号 -> 空格)递归切分, 并保留重叠内容,
避免将同一语义单元硬切断。
"""
from typing import List

DEFAULT_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "!", "?", ";", "，", ",", " ", ""]


class RecursiveTextSplitter:
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 80, separators=None):
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap 必须大于等于 0 且小于 chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = list(separators) if separators else list(DEFAULT_SEPARATORS)

    def split_text(self, text: str) -> List[str]:
        if not text:
            return []
        text = text.strip()
        if not text:
            return []

        base_chunks = self._split(text, self.separators)
        base_chunks = [c.strip() for c in base_chunks if c and c.strip()]
        if not base_chunks:
            return []
        if self.chunk_overlap <= 0:
            return base_chunks
        return self._add_overlap(base_chunks)

    # ------------------------------------------------------------------
    def _split(self, text: str, separators: List[str]) -> List[str]:
        if len(text) <= self.chunk_size:
            return [text]

        if not separators:
            return self._hard_split(text)

        sep = separators[0]
        rest = separators[1:]

        if sep == "":
            return self._hard_split(text)

        parts = text.split(sep)
        if len(parts) == 1:
            return self._split(text, rest)

        chunks: List[str] = []
        buffer = ""
        for part in parts:
            candidate = part if not buffer else f"{buffer}{sep}{part}"
            if len(candidate) <= self.chunk_size:
                buffer = candidate
                continue

            if buffer:
                if len(buffer) <= self.chunk_size:
                    chunks.append(buffer)
                else:
                    chunks.extend(self._split(buffer, rest))
                buffer = ""

            if len(part) > self.chunk_size:
                chunks.extend(self._split(part, rest))
            else:
                buffer = part

        if buffer:
            if len(buffer) <= self.chunk_size:
                chunks.append(buffer)
            else:
                chunks.extend(self._split(buffer, rest))

        return chunks

    def _hard_split(self, text: str) -> List[str]:
        step = max(1, self.chunk_size)
        return [text[i:i + step] for i in range(0, len(text), step)]

    def _add_overlap(self, chunks: List[str]) -> List[str]:
        result = [chunks[0]]
        for chunk in chunks[1:]:
            previous = result[-1]
            tail = previous[-self.chunk_overlap:]
            merged = f"{tail}{chunk}"
            result.append(merged)
        return result