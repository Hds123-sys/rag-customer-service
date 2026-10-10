"""
文本处理工具: 分词与特征抽取

针对中文场景: 中文按字符 n-gram 处理, 英文/数字按单词处理。
"""
import re

_CJK_RANGE = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_WORD_RE = re.compile(r"[a-zA-Z0-9]+")
_CJK_RE = re.compile(f"[{_CJK_RANGE}]+")
_PUNCT_RE = re.compile(r"[^\w\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")

# 不同长度 n-gram 的权重(越长越具体, 权重越高)
_NGRAM_WEIGHTS = {1: 0.6, 2: 1.0, 3: 1.3}


def normalize(text: str) -> str:
    """文本归一化"""
    if not text:
        return ""
    return text.replace("\u3000", " ").strip().lower()


def extract_features(text: str, max_n: int = 3):
    """
    抽取用于向量化的特征, 返回 (特征字符串, 权重) 列表。
    """
    text = normalize(text)
    if not text:
        return []

    features = []

    # 英文/数字单词
    for word in _WORD_RE.findall(text):
        if len(word) == 1 and word.isdigit():
            continue
        features.append((f"w:{word}", 1.2))

    # 中文/日文等表意文字: 1~max_n 元
    for run in _CJK_RE.findall(text):
        length = len(run)
        for n in range(1, max_n + 1):
            if length < n:
                break
            weight = _NGRAM_WEIGHTS.get(n, 1.0)
            for i in range(length - n + 1):
                features.append((f"c{n}:{run[i:i + n]}", weight))

    return features


def tokenize(text: str):
    """
    用于 BM25 关键词检索的分词: 英文单词 + 中文二元组。
    """
    text = normalize(text)
    if not text:
        return []

    tokens = list(_WORD_RE.findall(text))
    for run in _CJK_RE.findall(text):
        if len(run) == 1:
            tokens.append(run)
            continue
        for i in range(len(run) - 1):
            tokens.append(run[i:i + 2])
    return tokens


def clean_preview(text: str, limit: int = 200) -> str:
    """生成用于展示的文本摘要"""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."