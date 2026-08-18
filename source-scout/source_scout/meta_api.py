from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


GRAPH_VERSION = "v26.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"


@dataclass
class MetaAPIError(Exception):
    message: str
    code: int = 0
    error_subcode: int = 0

    def __str__(self) -> str:
        return self.message


def _request_json(url: str, method: str = "GET", timeout: int = 20) -> dict:
    request = Request(url, method=method, headers={"Accept": "application/json", "User-Agent": "SourceScout/0.2"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read())
            error = payload.get("error", {})
            raise MetaAPIError(
                str(error.get("message") or "Meta API 요청에 실패했습니다."),
                int(error.get("code") or 0),
                int(error.get("error_subcode") or 0),
            ) from exc
        except (json.JSONDecodeError, AttributeError):
            raise MetaAPIError("Meta API 요청에 실패했습니다.", exc.code) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise MetaAPIError("Meta API에 연결할 수 없습니다.") from exc


def graph_get(path: str, access_token: str, **params: object) -> dict:
    query = urlencode({**params, "access_token": access_token})
    return _request_json(f"{GRAPH_URL}/{path.lstrip('/')}?{query}")


def exchange_code(app_id: str, app_secret: str, redirect_uri: str, code: str) -> str:
    query = urlencode({
        "client_id": app_id,
        "client_secret": app_secret,
        "redirect_uri": redirect_uri,
        "code": code,
    })
    payload = _request_json(f"{GRAPH_URL}/oauth/access_token?{query}")
    token = str(payload.get("access_token") or "")
    if not token:
        raise MetaAPIError("Meta 액세스 토큰을 발급받지 못했습니다.")
    return token


def exchange_long_lived_token(app_id: str, app_secret: str, short_lived_token: str) -> str:
    query = urlencode({
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_lived_token,
    })
    payload = _request_json(f"{GRAPH_URL}/oauth/access_token?{query}")
    return str(payload.get("access_token") or short_lived_token)


def inspect_connection(user_access_token: str) -> dict:
    payload = graph_get(
        "me/accounts",
        user_access_token,
        fields="id,name,access_token,instagram_business_account{id,username}",
        limit=100,
    )
    pages = payload.get("data") or []
    linked = [page for page in pages if page.get("instagram_business_account")]
    if not linked:
        raise MetaAPIError("연결된 Instagram 프로페셔널 계정이 있는 Facebook 페이지를 찾지 못했습니다.")
    page = linked[0]
    instagram = page["instagram_business_account"]
    return {
        "user_access_token": user_access_token,
        "page_access_token": str(page.get("access_token") or user_access_token),
        "page_id": str(page.get("id") or ""),
        "page_name": str(page.get("name") or ""),
        "ig_user_id": str(instagram.get("id") or ""),
        "ig_username": str(instagram.get("username") or ""),
    }


def inspect_scopes(user_access_token: str, app_access_token: str) -> list[str]:
    payload = graph_get("debug_token", app_access_token, input_token=user_access_token)
    return sorted(str(scope) for scope in payload.get("data", {}).get("scopes", []))


def search_hashtag(connection: dict, hashtag: str, limit: int = 24) -> list[dict]:
    token = connection["user_access_token"]
    ig_user_id = connection["ig_user_id"]
    found = graph_get("ig_hashtag_search", token, user_id=ig_user_id, q=hashtag)
    matches = found.get("data") or []
    if not matches:
        return []
    hashtag_id = str(matches[0]["id"])
    media = graph_get(
        f"{hashtag_id}/recent_media",
        token,
        user_id=ig_user_id,
        fields="id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count",
        limit=max(1, min(limit, 50)),
    )
    items = []
    for item in media.get("data") or []:
        permalink = str(item.get("permalink") or "")
        if not permalink:
            continue
        items.append({
            "id": str(item.get("id") or ""),
            "caption": str(item.get("caption") or "")[:5000],
            "media_type": str(item.get("media_type") or ""),
            "media_url": str(item.get("media_url") or ""),
            "permalink": permalink,
            "thumbnail_url": str(item.get("thumbnail_url") or item.get("media_url") or ""),
            "timestamp": str(item.get("timestamp") or ""),
            "username": str(item.get("username") or ""),
            "like_count": int(item.get("like_count") or 0),
            "comments_count": int(item.get("comments_count") or 0),
        })
    return items


def revoke_permissions(user_access_token: str) -> None:
    query = urlencode({"access_token": user_access_token})
    _request_json(f"{GRAPH_URL}/me/permissions?{query}", method="DELETE")
