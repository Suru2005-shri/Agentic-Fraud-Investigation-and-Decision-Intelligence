"""Password hashing and signed session tokens using only the standard library."""
import base64
import hashlib
import hmac
import json
import secrets
import time

from .config import SECRET, TOKEN_HOURS


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return digest, salt


def verify_password(password: str, digest: str, salt: str) -> bool:
    return hmac.compare_digest(hash_password(password, salt)[0], digest)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: str) -> str:
    return _b64(hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest())


def make_token(username: str, hours: int = TOKEN_HOURS) -> str:
    payload = _b64(json.dumps({"u": username, "exp": int(time.time()) + hours * 3600}).encode())
    return f"{payload}.{_sign(payload)}"


def read_token(token: str) -> str | None:
    try:
        payload, sig = token.split(".", 1)
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        data = json.loads(_unb64(payload))
        return data["u"] if data["exp"] > time.time() else None
    except Exception:
        return None


def request_token(request_id: int) -> str:
    """Link token that lets a customer answer one evidence request without signing in."""
    return _sign(f"evidence-request:{request_id}")[:22]
