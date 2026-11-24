"""계정·설정 저장. %LOCALAPPDATA%\\MotionDeck\\config.json.

계정 하나는 이름, 기본값, 쿠키 배열, 크레딧, 쿨다운을 가진다.
쿠키는 cookies.py가 만든 Playwright 형식 그대로 보관한다.
"""

import json
import os
import time

APP_DIR = "MotionDeck"


def home():
    override = os.environ.get("MOTIONDECK_HOME")
    if override:
        return override
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    return os.path.join(base, APP_DIR)


def config_path():
    return os.path.join(home(), "config.json")


DEFAULTS = {
    "backend": "dola",
    "mode": "t2v",
    "ratio": "9:16",
    "length": 5,
    "output_dir": "",
    "slots": 1,
    "accounts": {},
    "active": "",
}


def _ensure():
    os.makedirs(home(), exist_ok=True)


def load():
    """설정 로드. 없거나 깨졌으면 기본값 복사본."""
    _ensure()
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    cfg = json.loads(json.dumps(DEFAULTS))
    if isinstance(data, dict):
        cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    if not isinstance(cfg.get("accounts"), dict):
        cfg["accounts"] = {}
    return cfg


def save(cfg):
    """임시 파일에 쓰고 교체. 중간에 죽어도 원본이 안 깨진다."""
    _ensure()
    tmp = config_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, config_path())


def _account(cfg, name, create=False):
    accs = cfg.setdefault("accounts", {})
    if name not in accs and create:
        accs[name] = {
            "name": name,
            "cookies": [],
            "credit": 0,
            "cooldown_until": 0.0,
            "defaults": {},
            "created": time.time(),
        }
    return accs.get(name)


def add_account(cfg, name, cookies=None):
    name = (name or "").strip()
    if not name:
        raise ValueError("계정 이름이 비어 있습니다.")
    acc = _account(cfg, name, create=True)
    acc["cookies"] = list(cookies or [])
    acc["credit"] = int(acc.get("credit") or 0)
    if not cfg.get("active"):
        cfg["active"] = name
    return acc


def remove_account(cfg, name):
    cfg.get("accounts", {}).pop(name, None)
    if cfg.get("active") == name:
        cfg["active"] = next(iter(cfg.get("accounts", {})), "")


def set_cookies(cfg, name, cookies):
    acc = _account(cfg, name, create=True)
    acc["cookies"] = list(cookies or [])


def get_cookies(cfg, name):
    acc = _account(cfg, name)
    return list((acc or {}).get("cookies") or [])


def credit(cfg, name, delta):
    acc = _account(cfg, name, create=True)
    acc["credit"] = max(0, int(acc.get("credit") or 0) + int(delta))
    return acc["credit"]


def cooldown(cfg, name, seconds):
    acc = _account(cfg, name, create=True)
    acc["cooldown_until"] = time.time() + float(seconds)
    return acc["cooldown_until"]


def ready_in(cfg, name):
    acc = _account(cfg, name) or {}
    return max(0.0, float(acc.get("cooldown_until") or 0) - time.time())


def available(cfg):
    """쿨다운이 끝났고 쿠키가 있는 계정 이름들."""
    out = []
    for name, acc in (cfg.get("accounts") or {}).items():
        if acc.get("cookies") and ready_in(cfg, name) <= 0:
            out.append(name)
    return out

# --- names other modules import from here ---
APP_NAME = "MotionDeck Studio"
VERSION = "0.4"


def now_ms():
    """Milliseconds since the epoch."""
    import time
    return int(time.time() * 1000)

