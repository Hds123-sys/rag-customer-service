"""
OpenAI 兼容接口客户端

统一封装 base_url 规范化和 /v1/chat/completions 调用。
"""
import logging
import time
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


def normalize_base_url(base_url: str) -> str:
    """将 base_url 规范化为可直接拼接 /chat/completions 的形式"""
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("API_BASE_URL 未配置")
    if not base.lower().endswith("/v1"):
        base = f"{base}/v1"
    return base


class ChatClient:
    """OpenAI 兼容的对话模型客户端"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.3,
        timeout: float = 120.0,
        max_retries: int = 2,
    ):
        self.base_url = normalize_base_url(base_url)
        self.api_key = api_key or ""
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        调用对话接口并返回文本内容。

        Raises:
            RuntimeError: 当接口不可用或返回异常时。
        """
        if not self.is_configured:
            raise RuntimeError("未配置 API_KEY, 无法调用大模型服务")

        payload: Dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "stream": False,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(self.endpoint, headers=self.headers, json=payload)
                if response.status_code >= 400:
                    detail = self._extract_error(response)
                    raise RuntimeError(f"大模型接口返回 {response.status_code}: {detail}")
                data = response.json()
                return self._extract_content(data)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_error = exc
                logger.warning("调用大模型失败(第 %s 次): %s", attempt + 1, exc)
                if attempt < self.max_retries:
                    time.sleep(1.0 * (attempt + 1))

        raise RuntimeError(f"无法连接大模型服务: {last_error}")

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_error(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return response.text[:300]
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):
            return str(error.get("message") or error)
        if error:
            return str(error)
        return str(data)[:300]

    @staticmethod
    def _extract_content(data: dict) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"大模型返回内容为空: {str(data)[:300]}")
        message = choices[0].get("message") or {}
        content = (message.get("content") or "").strip()
        if not content:
            content = (message.get("reasoning_content") or "").strip()
        if not content:
            raise RuntimeError("大模型返回了空回复")
        return content