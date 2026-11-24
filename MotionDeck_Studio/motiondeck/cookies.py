"""Dola 세션 쿠키 — 붙여넣기 텍스트를 Playwright add_cookies() 형식으로.

원본 app6.py 21843~22833을 그대로 옮긴 것. 입력은 JSON → Netscape
→ key=value 순으로 시도하고, `expires`는 0으로 파싱되는 경우에만
기록하며, raw 헤더 폴백은 .dola.com + "/"로 고정한다. 전부
sanitize_playwright_cookies()를 거친다.

원본과 같은 점: 붙여넣기에서 httpOnly·sameSite를 읽지 않는다.
따라서 `#HttpOnly_` 접두 줄은 `#` 주석으로 걸러져 버려진다.
"""

import json
import os
import time

DOMAIN = ".dola.com"
URL = "https://www.dola.com"
_SAMESITE = {"strict": "Strict", "lax": "Lax", "none": "None", "no_restriction": "None"}


class CookieError(Exception):
    """붙여넣기에서 쓸 만한 dola 쿠키를 못 건졌을 때."""


# ------------------------------------------------------------------ sanitizer

def sanitize_playwright_cookies(rows):
    """add_cookies() 직전 마지막 관문. 쓰레기는 버리고 기본값을 채운다."""
    kept = {}
    for c in rows or []:
        if not isinstance(c, dict):
            continue
        name = c.get("name")
        value = c.get("value")
        if name is None or value is None:
            continue

        entry = {"name": str(name), "value": str(value)}

        d = str(c.get("domain") or "")
        if "dola.com" not in d:
            d = DOMAIN
        entry["domain"] = d

        entry["path"] = str(c.get("path") or "/")
        entry["url"] = URL

        if "httpOnly" in c:
            entry["httpOnly"] = bool(c.get("httpOnly"))

        ss = str(c.get("sameSite") or "").strip().lower()
        if ss in _SAMESITE:
            entry["sameSite"] = _SAMESITE[ss]

        secure = c.get("secure")
        if secure is None:
            secure = True
        elif isinstance(secure, str):
            secure = secure.strip().lower() == "true"
        entry["secure"] = bool(secure) or entry.get("sameSite") == "None"

        exp = c.get("expires", c.get("expirationDate"))
        if exp is not None:
            try:
                n = int(float(exp))
            except (TypeError, ValueError):
                n = 0
            if n:
                entry["expires"] = n

        kept[(entry["domain"], entry["name"])] = entry
    return list(kept.values())


# ------------------------------------------------------------------ parsers

def _from_netscape(text):
    lines = [
        l.strip() for l in text.splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    netscape_cookies = []
    for l in lines:
        parts = l.split("\t")
        if len(parts) >= 7:
            domain, _, path, secure, exp, name, val = parts[:7]
            cookie = {
                "name": name,
                "value": val,
                "domain": domain,
                "path": path,
                "secure": secure.strip().lower() == "true",
            }
            try:
                n = int(float(exp))
            except (TypeError, ValueError):
                n = None
            if n:
                cookie["expires"] = n
            netscape_cookies.append(cookie)
    return netscape_cookies


def _from_json(text):
    data = json.loads(text)
    if isinstance(data, dict) and isinstance(data.get("cookies"), list):
        data = data["cookies"]
    if isinstance(data, list):
        return [c for c in data if isinstance(c, dict)]
    if isinstance(data, dict):
        return [{"name": k, "value": v, "domain": DOMAIN, "path": "/"}
                for k, v in data.items()]
    return []


def _from_kv(text):
    rows = []
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        k = k.strip()
        if not k:
            continue
        rows.append({"name": k, "value": v.strip(), "domain": DOMAIN, "path": "/"})
    return rows


def parse(text):
    """붙여넣기 텍스트 → Playwright 쿠키 리스트. 실패하면 CookieError."""
    text = (text or "").strip()
    if not text:
        raise CookieError("쿠키 붙여넣기가 비어 있습니다.")

    rows = []
    if text[:1] in "{[":
        try:
            rows = _from_json(text)
        except ValueError:
            rows = []
    if not rows:
        rows = _from_netscape(text)
    if not rows:
        rows = _from_kv(text)

    jar = sanitize_playwright_cookies(rows)
    if not jar:
        raise CookieError("붙여넣기에서 dola.com 쿠키를 못 찾았습니다.")
    return jar


def parse_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return parse(f.read())


# ------------------------------------------------------------------ helpers

def to_playwright(rows):
    return sanitize_playwright_cookies(rows)


def account_cookies(config, name):
    acc = (config.get("accounts") or {}).get(name) or {}
    return acc.get("cookies") or []


def check(rows):
    """ok / expired / none — 행 배지용."""
    jar = sanitize_playwright_cookies(rows)
    if not jar:
        return "none"
    exps = [c["expires"] for c in jar if c.get("expires")]
    if exps and all(e <= time.time() for e in exps):
        return "expired"
    return "ok"