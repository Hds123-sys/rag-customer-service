"""
安全工具模块: 密码哈希与校验

使用标准库 hashlib 实现 PBKDF2-HMAC-SHA256, 避免对第三方加密库的依赖,
可在任意 Python 版本上稳定运行。
"""
import base64
import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 260_000
_SALT_BYTES = 16


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def hash_password(password: str) -> str:
    """生成密码哈希, 格式: pbkdf2_sha256$迭代次数$盐$哈希"""
    if not isinstance(password, str) or not password:
        raise ValueError("密码不能为空")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGORITHM}${_ITERATIONS}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, hashed: str) -> bool:
    """校验明文密码与哈希是否匹配"""
    if not password or not hashed:
        return False
    try:
        algorithm, iterations, salt_b64, digest_b64 = hashed.split("$")
        if algorithm != _ALGORITHM:
            return False
        salt = _b64decode(salt_b64)
        expected = _b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(expected, actual)
    except (ValueError, TypeError):
        return False