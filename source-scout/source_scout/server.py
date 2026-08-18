from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import secrets
import sqlite3
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from .analyzer import analyze_metadata
from .analysis_provider import analyze_candidate
from .auth import SessionManager
from .database import Database
from .discovery import fetch_feed
from .metadata import canonicalize_url, ensure_public_url, fetch_metadata
from .meta_api import MetaAPIError, exchange_code, exchange_long_lived_token, inspect_connection, inspect_scopes, revoke_permissions, search_hashtag
from .scoring import SCORE_FIELDS, calculate_score, clamp_rating

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
DATA_DIR = Path(os.environ.get("SOURCE_SCOUT_DATA_DIR", str(ROOT / "data"))).expanduser()
DB = Database(DATA_DIR / "source_scout.db")
AUTH: SessionManager | None = None
META_OAUTH_STATES: dict[str, float] = {}

STATUSES = {"new", "reviewing", "permission_needed", "approved", "rejected"}
RIGHTS_STATUSES = {
    "unknown", "contact_needed", "requested", "permitted", "licensed", "public_domain", "denied"
}
APPROVABLE_RIGHTS = {"permitted", "licensed", "public_domain"}
EDITABLE_FIELDS = {
    "title", "creator", "theme", "status", "rights_status", "notes", "rights_evidence",
    "analysis_summary", "thumbnail_url", *SCORE_FIELDS
}


def detect_platform(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "instagram.com" in host:
        return "instagram"
    if "tiktok.com" in host:
        return "tiktok"
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "reddit.com" in host or "redd.it" in host:
        return "reddit"
    return "web"


def validate_url(value: object) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("http 또는 https 형식의 URL을 입력하세요.")
    return canonicalize_url(url)


def normalize_payload(payload: dict, creating: bool = False) -> dict:
    data = {key: payload[key] for key in EDITABLE_FIELDS if key in payload}
    for field in SCORE_FIELDS:
        if field in data or creating:
            data[field] = clamp_rating(data.get(field))
    if "status" in data and data["status"] not in STATUSES:
        raise ValueError("유효하지 않은 작업 상태입니다.")
    if "rights_status" in data and data["rights_status"] not in RIGHTS_STATUSES:
        raise ValueError("유효하지 않은 권리 상태입니다.")
    if data.get("status") == "approved" and data.get("rights_status") not in APPROVABLE_RIGHTS:
        raise ValueError("사용 허락·라이선스·퍼블릭 도메인이 확인되어야 승인할 수 있습니다.")
    return data


def candidate_from_payload(payload: dict, source: str) -> dict:
    url = validate_url(payload.get("url"))
    platform = detect_platform(url)
    title = str(payload.get("title") or "제목 미정").strip()[:500]
    creator = str(payload.get("creator") or "").strip()[:200]
    description = str(payload.get("description") or "").strip()[:5000]
    thumbnail_url = str(payload.get("thumbnail_url") or "").strip()[:2000]
    if payload.get("auto_enrich") or source == "mobile_share":
        try:
            enriched = fetch_metadata(url)
            url = enriched["url"]
            platform = detect_platform(url)
            if title in {"", "제목 미정", "모바일 공유 후보"}:
                title = enriched["title"][:500] or title
            creator = creator or enriched["creator"][:200]
            description = description or enriched["description"][:5000]
            thumbnail_url = thumbnail_url or enriched["thumbnail_url"][:2000]
        except (OSError, ValueError):
            pass
    data = normalize_payload(payload, creating=True)
    if payload.get("auto_analyze"):
        suggestion = analyze_metadata(title, description, creator, platform)
        for field in ("theme", "analysis_summary", *SCORE_FIELDS):
            if field not in payload:
                data[field] = suggestion[field]
        data["analysis_status"] = "metadata_only"
        data["analysis_detail"] = "제목·설명·게시자 정보만 분석했습니다."
    data.update({
        "url": url,
        "platform": platform,
        "title": title,
        "creator": creator,
        "theme": str(data.get("theme") or payload.get("theme") or "직업·공정").strip(),
        "status": str(payload.get("status") or "new"),
        "rights_status": str(payload.get("rights_status") or "unknown"),
        "source": payload.get("source") if payload.get("source") in {"browser_extension", "instagram_api"} else source,
        "thumbnail_url": thumbnail_url,
    })
    if description and not data.get("notes"):
        data["notes"] = description
    data["total_score"] = calculate_score(data)
    return DB.create_candidate(data)


def run_discovery_source(source: dict) -> dict:
    created = duplicates = errors = 0
    try:
        for entry in fetch_feed(source["feed_url"]):
            payload = {
                **entry,
                "theme": source["theme"],
                "rights_status": "unknown",
                "auto_analyze": True,
            }
            try:
                candidate_from_payload(payload, f"feed:{source['id']}")
                created += 1
            except sqlite3.IntegrityError:
                duplicates += 1
            except (OSError, ValueError):
                errors += 1
        DB.mark_discovery_checked(source["id"])
        return {"created": created, "duplicates": duplicates, "errors": errors}
    except Exception as exc:
        DB.mark_discovery_checked(source["id"], str(exc))
        return {"created": created, "duplicates": duplicates, "errors": errors + 1, "error": str(exc)}


def discovery_loop(interval_minutes: int) -> None:
    while True:
        for source in DB.list_discovery_sources(enabled_only=True):
            run_discovery_source(source)
        threading.Event().wait(interval_minutes * 60)


class Handler(BaseHTTPRequestHandler):
    server_version = "SourceScout/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def send_json(self, data: object, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message: str, status: int = 400) -> None:
        self.send_json({"error": message}, status)

    def redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def meta_settings(self) -> tuple[str, str, str]:
        app_id = os.environ.get("SOURCE_SCOUT_META_APP_ID", "").strip()
        app_secret = os.environ.get("SOURCE_SCOUT_META_APP_SECRET", "").strip()
        public_url = os.environ.get("SOURCE_SCOUT_PUBLIC_URL", "http://127.0.0.1:8765").strip().rstrip("/")
        if not app_id or not app_secret:
            raise ValueError("Meta 앱 ID와 시크릿이 설정되지 않았습니다.")
        return app_id, app_secret, f"{public_url}/api/meta/callback"

    def ensure_meta_connection(self) -> dict | None:
        connection = DB.get_meta_connection(include_tokens=True)
        if connection:
            return connection
        token = os.environ.get("SOURCE_SCOUT_META_USER_ACCESS_TOKEN", "").strip()
        if not token:
            return None
        details = inspect_connection(token)
        app_id, app_secret, _ = self.meta_settings()
        details["scopes"] = ",".join(inspect_scopes(token, f"{app_id}|{app_secret}"))
        DB.save_meta_connection(details)
        return DB.get_meta_connection(include_tokens=True)

    def is_secure_request(self) -> bool:
        return self.headers.get("X-Forwarded-Proto", "").lower() == "https"

    def is_authenticated(self) -> bool:
        if AUTH is None:
            return False
        token = AUTH.token_from_cookie(self.headers.get("Cookie"))
        return AUTH.validate(token)

    def has_mobile_token(self) -> bool:
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return False
        raw_token = authorization[7:].strip()
        if not raw_token:
            return False
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        return DB.validate_mobile_token(token_hash)

    def require_auth(self, api: bool = True) -> bool:
        if self.is_authenticated():
            return True
        if api:
            self.send_error_json("로그인이 필요합니다.", HTTPStatus.UNAUTHORIZED)
        else:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/login")
            self.end_headers()
        return False

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("요청 크기가 너무 큽니다.")
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            raise ValueError("JSON 형식이 올바르지 않습니다.") from exc

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        public_pages = {
            "/privacy": "privacy.html",
            "/terms": "terms.html",
            "/data-deletion": "data-deletion.html",
        }
        if parsed.path in public_pages:
            self.serve_static_file(public_pages[parsed.path])
            return
        if parsed.path == "/share":
            self.serve_static_file("share.html")
            return
        if parsed.path == "/login":
            if self.is_authenticated():
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", "/")
                self.end_headers()
            else:
                self.serve_static_file("login.html")
            return
        if parsed.path == "/api/health":
            self.send_json({"status": "ok"})
            return
        if parsed.path == "/api/session":
            self.send_json({"authenticated": self.is_authenticated()}, 200 if self.is_authenticated() else 401)
            return
        if parsed.path == "/api/meta/callback":
            self.meta_callback(parsed)
            return
        if parsed.path.startswith("/api/") and not self.require_auth():
            return
        if parsed.path == "/" and not self.require_auth(api=False):
            return
        if parsed.path == "/api/candidates":
            query = parse_qs(parsed.query)
            candidates = DB.list_candidates(query.get("status", [""])[0], query.get("theme", [""])[0])
            self.send_json({"items": candidates, "count": len(candidates)})
            return
        if parsed.path == "/api/mobile-tokens":
            self.send_json({"items": DB.list_mobile_tokens()})
            return
        if parsed.path == "/api/discovery-sources":
            self.send_json({"items": DB.list_discovery_sources()})
            return
        if parsed.path == "/api/meta/status":
            try:
                connection = self.ensure_meta_connection()
                public = DB.get_meta_connection(include_tokens=False) if connection else None
                self.send_json({"configured": bool(os.environ.get("SOURCE_SCOUT_META_APP_ID")), "connected": bool(public), "connection": public})
            except (MetaAPIError, ValueError) as exc:
                self.send_json({"configured": True, "connected": False, "error": str(exc)})
            return
        if parsed.path == "/api/meta/connect":
            self.meta_connect()
            return
        if parsed.path == "/api/export.csv":
            self.export_csv()
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        if self.path == "/api/login":
            self.login()
            return
        if self.path == "/api/logout":
            self.logout()
            return
        if self.path == "/api/mobile-share":
            if not (self.is_authenticated() or self.has_mobile_token()):
                self.send_error_json("유효한 모바일 토큰 또는 로그인이 필요합니다.", HTTPStatus.UNAUTHORIZED)
                return
            self.create_candidate_request("mobile_share")
            return
        if not self.require_auth():
            return
        if self.path == "/api/mobile-tokens":
            try:
                payload = self.read_json()
                label = str(payload.get("label") or "모바일 기기").strip()[:100]
                raw_token = f"ss_{secrets.token_urlsafe(32)}"
                token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
                item = DB.create_mobile_token(label, token_hash)
                self.send_json({**item, "token": raw_token}, HTTPStatus.CREATED)
            except ValueError as exc:
                self.send_error_json(str(exc))
            return
        if self.path == "/api/discovery-sources":
            try:
                payload = self.read_json()
                label = str(payload.get("label") or "새 피드").strip()[:100]
                feed_url = validate_url(payload.get("feed_url"))
                ensure_public_url(feed_url)
                theme = str(payload.get("theme") or "기타").strip()[:100]
                self.send_json(DB.create_discovery_source(label, feed_url, theme), HTTPStatus.CREATED)
            except sqlite3.IntegrityError:
                self.send_error_json("이미 등록된 피드입니다.", HTTPStatus.CONFLICT)
            except ValueError as exc:
                self.send_error_json(str(exc))
            return
        if self.path == "/api/meta/hashtag-search":
            self.meta_hashtag_search()
            return
        if self.path.startswith("/api/discovery-sources/") and self.path.endswith("/run"):
            try:
                source_id = int(self.path.strip("/").split("/")[2])
            except (ValueError, IndexError):
                self.send_error_json("잘못된 소스 ID입니다.")
                return
            source = DB.get_discovery_source(source_id)
            if not source:
                self.send_error_json("탐색 소스를 찾을 수 없습니다.", 404)
                return
            self.send_json(run_discovery_source(source))
            return
        if self.path.startswith("/api/candidates/") and self.path.endswith("/analyze"):
            try:
                candidate_id = int(self.path.strip("/").split("/")[2])
            except (ValueError, IndexError):
                self.send_error_json("잘못된 후보 ID입니다.")
                return
            current = DB.get_candidate(candidate_id)
            if not current:
                self.send_error_json("후보를 찾을 수 없습니다.", 404)
                return
            try:
                suggestion = analyze_candidate(current)
                update = {field: suggestion[field] for field in ("theme", "analysis_summary", *SCORE_FIELDS) if field in suggestion}
                update["analysis_status"] = suggestion["analysis_status"]
                update["analysis_detail"] = str(suggestion.get("analysis_detail") or "")[:5000]
                ideas = suggestion.get("script_ideas") or []
                update["script_ideas"] = json.dumps(ideas, ensure_ascii=False) if isinstance(ideas, list) else str(ideas)[:10000]
                update["total_score"] = calculate_score({**current, **update})
                self.send_json(DB.update_candidate(candidate_id, update))
            except Exception as exc:
                DB.update_candidate(candidate_id, {"analysis_status": "failed", "analysis_detail": str(exc)[:1000]})
                self.send_error_json("분석 작업에 실패했습니다.", 502)
            return
        if self.path == "/api/candidates":
            self.create_candidate_request("manual")
            return
        self.send_error_json("경로를 찾을 수 없습니다.", 404)

    def create_candidate_request(self, source: str) -> None:
        try:
            payload = self.read_json()
            self.send_json(candidate_from_payload(payload, source), HTTPStatus.CREATED)
        except sqlite3.IntegrityError:
            self.send_error_json("이미 등록된 URL입니다.", HTTPStatus.CONFLICT)
        except ValueError as exc:
            self.send_error_json(str(exc))

    def do_PATCH(self) -> None:
        if not self.require_auth():
            return
        candidate_id = self.parse_candidate_id()
        if candidate_id is None:
            return
        current = DB.get_candidate(candidate_id)
        if not current:
            self.send_error_json("후보를 찾을 수 없습니다.", 404)
            return
        try:
            payload = self.read_json()
            merged = {**current, **payload}
            data = normalize_payload(payload)
            if merged.get("status") == "approved" and merged.get("rights_status") not in APPROVABLE_RIGHTS:
                raise ValueError("사용 권리가 확인되어야 승인할 수 있습니다.")
            scoring_values = {**current, **data}
            data["total_score"] = calculate_score(scoring_values)
            self.send_json(DB.update_candidate(candidate_id, data))
        except ValueError as exc:
            self.send_error_json(str(exc))

    def do_DELETE(self) -> None:
        if not self.require_auth():
            return
        if urlparse(self.path).path == "/api/meta/connection":
            connection = DB.delete_meta_connection()
            if connection:
                try:
                    revoke_permissions(connection["user_access_token"])
                except MetaAPIError:
                    pass
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        if urlparse(self.path).path.startswith("/api/mobile-tokens/"):
            try:
                token_id = int(urlparse(self.path).path.rsplit("/", 1)[1])
            except ValueError:
                self.send_error_json("잘못된 토큰 ID입니다.")
                return
            if DB.revoke_mobile_token(token_id):
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
            else:
                self.send_error_json("활성 토큰을 찾을 수 없습니다.", 404)
            return
        if urlparse(self.path).path.startswith("/api/discovery-sources/"):
            try:
                source_id = int(urlparse(self.path).path.rsplit("/", 1)[1])
            except ValueError:
                self.send_error_json("잘못된 소스 ID입니다.")
                return
            if DB.delete_discovery_source(source_id):
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
            else:
                self.send_error_json("탐색 소스를 찾을 수 없습니다.", 404)
            return
        candidate_id = self.parse_candidate_id()
        if candidate_id is None:
            return
        if DB.delete_candidate(candidate_id):
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
        else:
            self.send_error_json("후보를 찾을 수 없습니다.", 404)

    def meta_connect(self) -> None:
        try:
            app_id, _, redirect_uri = self.meta_settings()
        except ValueError as exc:
            self.send_error_json(str(exc), 503)
            return
        now = time.time()
        for state, expires_at in list(META_OAUTH_STATES.items()):
            if expires_at < now:
                META_OAUTH_STATES.pop(state, None)
        state = secrets.token_urlsafe(32)
        META_OAUTH_STATES[state] = now + 600
        params = {
            "client_id": app_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": "code",
            "scope": "instagram_basic,pages_show_list,pages_read_engagement,business_management",
        }
        config_id = os.environ.get("SOURCE_SCOUT_META_CONFIG_ID", "").strip()
        if config_id:
            params["config_id"] = config_id
            params["override_default_response_type"] = "true"
        query = urlencode(params)
        self.redirect(f"https://www.facebook.com/v26.0/dialog/oauth?{query}")

    def meta_callback(self, parsed) -> None:
        if not self.is_authenticated():
            self.redirect("/login")
            return
        query = parse_qs(parsed.query)
        if query.get("error"):
            self.redirect("/?meta=cancelled")
            return
        state = query.get("state", [""])[0]
        code = query.get("code", [""])[0]
        expires_at = META_OAUTH_STATES.pop(state, 0)
        if not state or not code or expires_at < time.time():
            self.redirect("/?meta=invalid_state")
            return
        try:
            app_id, app_secret, redirect_uri = self.meta_settings()
            short_lived_token = exchange_code(app_id, app_secret, redirect_uri, code)
            token = exchange_long_lived_token(app_id, app_secret, short_lived_token)
            details = inspect_connection(token)
            details["scopes"] = ",".join(inspect_scopes(token, f"{app_id}|{app_secret}"))
            DB.save_meta_connection(details)
            self.redirect("/?meta=connected")
        except (MetaAPIError, ValueError):
            self.redirect("/?meta=error")

    def meta_hashtag_search(self) -> None:
        try:
            payload = self.read_json()
            hashtag = str(payload.get("hashtag") or "").strip().lstrip("#")
            if not hashtag or len(hashtag) > 100 or not hashtag.replace("_", "").isalnum():
                raise ValueError("문자와 숫자로 된 해시태그를 입력하세요.")
            connection = self.ensure_meta_connection()
            if not connection:
                self.send_error_json("먼저 Meta 계정을 연결하세요.", HTTPStatus.CONFLICT)
                return
            items = search_hashtag(connection, hashtag, int(payload.get("limit") or 24))
            self.send_json({"hashtag": hashtag, "items": items, "count": len(items)})
        except ValueError as exc:
            self.send_error_json(str(exc))
        except MetaAPIError as exc:
            if exc.code == 10:
                self.send_json({
                    "error": "Meta 앱 검수가 필요합니다.",
                    "review_required": True,
                    "detail": str(exc),
                }, HTTPStatus.FORBIDDEN)
            else:
                self.send_error_json(str(exc), HTTPStatus.BAD_GATEWAY)

    def parse_candidate_id(self) -> int | None:
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) != 3 or parts[:2] != ["api", "candidates"]:
            self.send_error_json("경로를 찾을 수 없습니다.", 404)
            return None
        try:
            return int(parts[2])
        except ValueError:
            self.send_error_json("잘못된 후보 ID입니다.")
            return None

    def export_csv(self) -> None:
        rows = DB.list_candidates()
        output = io.StringIO()
        fields = list(rows[0].keys()) if rows else ["id", "url", "title", "status", "rights_status", "total_score"]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        body = ("\ufeff" + output.getvalue()).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", "attachment; filename=source-scout.csv")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def login(self) -> None:
        global AUTH
        if AUTH is None:
            self.send_error_json("로그인 설정이 준비되지 않았습니다.", 503)
            return
        try:
            payload = self.read_json()
        except ValueError as exc:
            self.send_error_json(str(exc))
            return
        if not AUTH.verify_credentials(payload.get("username"), payload.get("password")):
            self.send_error_json("아이디 또는 비밀번호가 올바르지 않습니다.", HTTPStatus.UNAUTHORIZED)
            return
        token = AUTH.issue()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie", AUTH.cookie_header(token, self.is_secure_request()))
        body = json.dumps({"authenticated": True, "expires_in": AUTH.lifetime_seconds}).encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def logout(self) -> None:
        global AUTH
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if AUTH is not None:
            self.send_header("Set-Cookie", AUTH.clear_cookie_header(self.is_secure_request()))
        body = b'{"authenticated":false}'
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_static(self, path: str) -> None:
        requested = "index.html" if path in {"", "/"} else path.lstrip("/")
        self.serve_static_file(requested)

    def serve_static_file(self, requested: str) -> None:
        target = (STATIC / requested).resolve()
        if STATIC.resolve() not in target.parents and target != STATIC.resolve():
            self.send_error_json("경로를 찾을 수 없습니다.", 404)
            return
        if not target.is_file():
            self.send_error_json("경로를 찾을 수 없습니다.", 404)
            return
        content_types = {
            ".html": "text/html", ".css": "text/css", ".js": "text/javascript",
            ".webmanifest": "application/manifest+json", ".svg": "image/svg+xml",
        }
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_types.get(target.suffix, "application/octet-stream") + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run() -> None:
    global AUTH
    host = os.environ.get("SOURCE_SCOUT_HOST", "127.0.0.1")
    port = int(os.environ.get("SOURCE_SCOUT_PORT", "8765"))
    username = os.environ.get("SOURCE_SCOUT_USERNAME", "")
    password = os.environ.get("SOURCE_SCOUT_PASSWORD", "")
    session_secret = os.environ.get("SOURCE_SCOUT_SESSION_SECRET", "")
    if not session_secret:
        session_secret = secrets.token_urlsafe(48)
        print("경고: SOURCE_SCOUT_SESSION_SECRET이 없어 임시 키를 사용합니다. 재시작하면 세션이 종료됩니다.")
    session_hours = max(12, int(os.environ.get("SOURCE_SCOUT_SESSION_HOURS", "24")))
    discovery_interval = max(0, int(os.environ.get("SOURCE_SCOUT_DISCOVERY_INTERVAL_MINUTES", "60")))
    AUTH = SessionManager(username, password, session_secret, session_hours * 3600)
    if discovery_interval:
        threading.Thread(target=discovery_loop, args=(discovery_interval,), daemon=True, name="source-discovery").start()
    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"Source Scout 실행 중: {url}")
    if os.environ.get("SOURCE_SCOUT_NO_BROWSER") != "1":
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSource Scout를 종료합니다.")
    finally:
        server.server_close()
