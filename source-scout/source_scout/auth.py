from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from http.cookies import SimpleCookie


class SessionManager:
    cookie_name = "source_scout_session"

    def __init__(self, username: str, password: str, secret: str, lifetime_seconds: int = 86_400):
        if not username:
            raise ValueError("SOURCE_SCOUT_USERNAME 환경변수가 필요합니다.")
        if not password:
            raise ValueError("SOURCE_SCOUT_PASSWORD 환경변수가 필요합니다.")
        if len(secret) < 32:
            raise ValueError("SOURCE_SCOUT_SESSION_SECRET은 32자 이상이어야 합니다.")
        if lifetime_seconds < 43_200:
            raise ValueError("세션 유지 시간은 최소 12시간이어야 합니다.")
        self.username = username
        self.password = password
        self.secret = secret.encode("utf-8")
        self.lifetime_seconds = lifetime_seconds

    def verify_credentials(self, username: object, password: object) -> bool:
        username_valid = hmac.compare_digest(str(username or "").encode("utf-8"), self.username.encode("utf-8"))
        password_valid = hmac.compare_digest(str(password or "").encode("utf-8"), self.password.encode("utf-8"))
        return username_valid and password_valid

    def issue(self, now: int | None = None) -> str:
        issued_at = int(time.time() if now is None else now)
        payload = {
            "iat": issued_at,
            "exp": issued_at + self.lifetime_seconds,
            "nonce": secrets.token_urlsafe(12),
        }
        encoded = self._encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signature = self._sign(encoded)
        return f"{encoded}.{signature}"

    def validate(self, token: str, now: int | None = None) -> bool:
        try:
            encoded, signature = token.split(".", 1)
            if not hmac.compare_digest(signature, self._sign(encoded)):
                return False
            payload = json.loads(self._decode(encoded))
            current = int(time.time() if now is None else now)
            return int(payload["iat"]) <= current < int(payload["exp"])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return False

    def token_from_cookie(self, cookie_header: str | None) -> str:
        if not cookie_header:
            return ""
        cookie = SimpleCookie()
        try:
            cookie.load(cookie_header)
            morsel = cookie.get(self.cookie_name)
            return morsel.value if morsel else ""
        except Exception:
            return ""

    def cookie_header(self, token: str, secure: bool) -> str:
        attributes = [
            f"{self.cookie_name}={token}",
            "Path=/",
            "HttpOnly",
            "SameSite=Lax",
            f"Max-Age={self.lifetime_seconds}",
        ]
        if secure:
            attributes.append("Secure")
        return "; ".join(attributes)

    def clear_cookie_header(self, secure: bool) -> str:
        attributes = [f"{self.cookie_name}=", "Path=/", "HttpOnly", "SameSite=Lax", "Max-Age=0"]
        if secure:
            attributes.append("Secure")
        return "; ".join(attributes)

    def _sign(self, value: str) -> str:
        digest = hmac.new(self.secret, value.encode("ascii"), hashlib.sha256).digest()
        return self._encode(digest)

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    @staticmethod
    def _decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
