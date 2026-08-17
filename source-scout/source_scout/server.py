from __future__ import annotations

import csv
import io
import json
import os
import secrets
import sqlite3
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .analyzer import analyze_metadata
from .auth import SessionManager
from .database import Database
from .scoring import SCORE_FIELDS, calculate_score, clamp_rating

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
DB = Database(ROOT / "data" / "source_scout.db")
AUTH: SessionManager | None = None

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
    return url


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

    def is_secure_request(self) -> bool:
        return self.headers.get("X-Forwarded-Proto", "").lower() == "https"

    def is_authenticated(self) -> bool:
        if AUTH is None:
            return False
        token = AUTH.token_from_cookie(self.headers.get("Cookie"))
        return AUTH.validate(token)

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
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
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
        if parsed.path.startswith("/api/") and not self.require_auth():
            return
        if parsed.path == "/" and not self.require_auth(api=False):
            return
        if parsed.path == "/api/candidates":
            query = parse_qs(parsed.query)
            candidates = DB.list_candidates(query.get("status", [""])[0], query.get("theme", [""])[0])
            self.send_json({"items": candidates, "count": len(candidates)})
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
        if not self.require_auth():
            return
        if self.path != "/api/candidates":
            self.send_error_json("경로를 찾을 수 없습니다.", 404)
            return
        try:
            payload = self.read_json()
            url = validate_url(payload.get("url"))
            platform = detect_platform(url)
            title = str(payload.get("title") or "제목 미정").strip()[:500]
            creator = str(payload.get("creator") or "").strip()[:200]
            description = str(payload.get("description") or "").strip()[:5000]
            data = normalize_payload(payload, creating=True)
            if payload.get("auto_analyze"):
                suggestion = analyze_metadata(title, description, creator, platform)
                for field in ("theme", "analysis_summary", *SCORE_FIELDS):
                    if field not in payload:
                        data[field] = suggestion[field]
            data.update({
                "url": url,
                "platform": platform,
                "title": title,
                "creator": creator,
                "theme": str(data.get("theme") or payload.get("theme") or "직업·공정").strip(),
                "status": str(payload.get("status") or "new"),
                "rights_status": str(payload.get("rights_status") or "unknown"),
                "source": "browser_extension" if payload.get("source") == "browser_extension" else "manual",
                "thumbnail_url": str(payload.get("thumbnail_url") or "").strip()[:2000],
            })
            if description and not data.get("notes"):
                data["notes"] = description
            data["total_score"] = calculate_score(data)
            self.send_json(DB.create_candidate(data), HTTPStatus.CREATED)
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
        candidate_id = self.parse_candidate_id()
        if candidate_id is None:
            return
        if DB.delete_candidate(candidate_id):
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
        else:
            self.send_error_json("후보를 찾을 수 없습니다.", 404)

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
        if not AUTH.verify_password(payload.get("password")):
            self.send_error_json("비밀번호가 올바르지 않습니다.", HTTPStatus.UNAUTHORIZED)
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
        content_types = {".html": "text/html", ".css": "text/css", ".js": "text/javascript"}
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
    password = os.environ.get("SOURCE_SCOUT_PASSWORD", "")
    session_secret = os.environ.get("SOURCE_SCOUT_SESSION_SECRET", "")
    if not session_secret:
        session_secret = secrets.token_urlsafe(48)
        print("경고: SOURCE_SCOUT_SESSION_SECRET이 없어 임시 키를 사용합니다. 재시작하면 세션이 종료됩니다.")
    session_hours = max(12, int(os.environ.get("SOURCE_SCOUT_SESSION_HOURS", "24")))
    AUTH = SessionManager(password, session_secret, session_hours * 3600)
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
