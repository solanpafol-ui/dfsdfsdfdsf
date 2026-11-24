"""구독·지역 잠금 오버레이 감지.

오버레이 문구를 읽어 종류를 돌려주고, 기기 지문에 HMAC을 걸어
같은 기기에서의 통과를 재사용한다.
"""

import hashlib
import hmac
import platform
import time
import uuid

SECRET = b"vp-gate-v1"
GEO_OK = ("KR", "DE", "FR", "ES", "BR")


def machine_id():
    raw = f"{uuid.getnode()}|{platform.machine()}|{platform.system()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def sign(mid, stamp):
    return hmac.new(SECRET, f"{mid}:{stamp}".encode(), hashlib.sha256).hexdigest()


def stamp_now():
    return int(time.time())


def verify(mid, stamp, tag):
    return hmac.compare_digest(sign(mid, int(stamp)), tag or "")


def detect(page):
    """None / 'sub' / 'geo' / 'login'."""
    try:
        t = page.inner_text("body", timeout=3000)
    except Exception:
        return None
    if any(k in t for k in ("구독", "subscription", "플랜", "upgrade")):
        return "sub"
    if any(k in t for k in ("지역", "region", "country", "not available in your")):
        return "geo"
    if any(k in t for k in ("로그인", "sign in", "log in")):
        return "login"
    return None


def blocked(page):
    kind = detect(page)
    if kind in ("sub", "geo"):
        return kind
    return None