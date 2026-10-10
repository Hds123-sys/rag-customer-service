"""
轻量级内存限流(滑动窗口)

用于保护注册 / 登录 / 找回密码 / 问答等接口, 缓解暴力破解与滥用。

说明: 计数保存在进程内存中, 适用于单实例部署; 多实例部署时应替换为 Redis 等
集中式存储, 否则每个实例都会独立计数。
"""
import threading
import time
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, Request, status

from app.core.config import settings

# 内存中最多保留的限流键数量, 超过后清理过期键, 防止无限增长
_MAX_KEYS = 20000


class SlidingWindowLimiter:
    """滑动窗口计数器"""

    def __init__(self) -> None:
        self._hits: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window: float) -> Tuple[bool, float]:
        """记录一次访问并判断是否超限, 返回 (是否放行, 建议等待秒数)"""
        if limit <= 0 or window <= 0:
            return True, 0.0

        now = time.time()
        with self._lock:
            timestamps = [stamp for stamp in self._hits.get(key, []) if now - stamp < window]
            if len(timestamps) >= limit:
                retry_after = window - (now - timestamps[0])
                self._hits[key] = timestamps
                return False, max(retry_after, 0.0)

            timestamps.append(now)
            self._hits[key] = timestamps
            if len(self._hits) > _MAX_KEYS:
                self._prune(now, window)
            return True, 0.0

    def _prune(self, now: float, window: float) -> None:
        stale = [key for key, hits in self._hits.items() if not hits or now - hits[-1] >= window]
        for key in stale:
            self._hits.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def parse_rule(rule: str, default: Tuple[int, float] = (0, 0.0)) -> Tuple[int, float]:
    """解析 "次数/窗口秒数" 形式的规则, 例如 "30/60" """
    try:
        limit_text, window_text = str(rule).split("/", 1)
        return max(0, int(limit_text.strip())), max(0.0, float(window_text.strip()))
    except (ValueError, AttributeError, TypeError):
        return default


def client_ip(request: Request) -> str:
    """获取客户端 IP; 位于反向代理之后时优先采用 X-Forwarded-For 的第一跳"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


def enforce(request: Request, scope: str, rule: str, identifier: Optional[str] = None) -> None:
    """
    按 作用域 + 客户端IP(+可选标识) 限流, 超限时抛出 429。

    identifier 一般传用户名 / 邮箱, 这样按账号维度独立计数, 不会因为同一出口 IP
    的其他用户被误伤。
    """
    if not settings.RATE_LIMIT_ENABLED:
        return

    limit, window = parse_rule(rule)
    if limit <= 0:
        return

    key = f"{scope}:{client_ip(request)}:{(identifier or '-').strip().lower()}"
    allowed, retry_after = limiter.check(key, limit, window)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="请求过于频繁，请稍后再试",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )