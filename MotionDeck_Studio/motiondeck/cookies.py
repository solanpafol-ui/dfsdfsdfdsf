"""Cookie jar parsing for the browser backend.

Ported 1:1 from app6.py (the netscape_cookies block) so the paste formats
people already have keep working:

  * a Netscape cookies.txt export  (7 tab fields, optional #HttpOnly_ prefix)
  * a raw `Cookie:` header          ("a=1; b=2")
  * a JSON array                    (tried first)

Original behaviour is preserved on purpose, quirks included: fields past the
7th are ignored (partitionKey/CHIPS dropped), no httpOnly/sameSite is taken
from the paste, `expires` is only written when it parses to a non-zero int,
and the raw-header fallback pins .dola.com + "/". Everything funnels through
sanitize_playwright_cookies().
"""
import json
import time

DOMAIN = ".dola.com"

_SAME_SITE = {"strict": "Strict", "lax": "Lax", "none": "None", "no_restriction": "None"}


class CookieError(ValueError):
    pass


# ------------------------------------------------------------------ sanitizer
def sanitize_playwright_cookies(rows):
    """Last gate before add_cookies(): drop junk, fill Playwright defaults."""
    kept = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        domain = str(row.get("domain") or DOMAIN).strip()
        http_only = bool(row.get("httpOnly"))
        if domain.startswith("#HttpOnly_"):
            domain = domain[len("#HttpOnly_"):]
            http_only = True
        if not domain:
            domain = DOMAIN
        path = str(row.get("path") or "/") or "/"
        secure = bool(row.get("secure"))
        if name.startswith("__Secure-"):
            secure = True
        if name.startswith("__Host-"):
            secure, path, domain = True, "/", domain.lstrip(".") or "dola.com"

        cookie = {
            "name": name,
            "value": "" if row.get("value") is None else str(row.get("value")),
            "domain": domain,
            "path": path,
            "secure": secure,
            "httpOnly": http_only,
        }
        exp = row.get("expires")
        if exp not in (None, ""):
            try:
                exp = int(float(exp))
            except (TypeError, ValueError):
                exp = None
            if exp and exp > 0:
                cookie["expires"] = exp
        same_site = _SAME_SITE.get(str(row.get("sameSite") or "").lower())
        if not same_site:
            same_site = "Lax"
        if same_site == "None":
            secure = True
        cookie["secure"] = secure
        cookie["sameSite"] = same_site
        kept[(cookie["domain"], cookie["path"], cookie["name"])] = cookie
    return list(kept.values())


# --------------------------------------------------------------------- formats
def _lines(text):
    out = []
    for raw in text.split("\n"):
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        if line.startswith("#HttpOnly_"):
            out.append(line)
            continue
        if line.lstrip().startswith("#"):
            continue
        out.append(line)
    return out


def _from_netscape(text):
    cookies = []
    for line in _lines(text):
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, path, secure, exp, name, val = parts[:7]
        try:
            exp_val = int(float(exp))
        except Exception:
            exp_val = None
        cookie = {
            "name": name,
            "value": val,
            "domain": domain,
            "path": path,
            "secure": secure.lower() == "true",
        }
        if exp_val:
            cookie["expires"] = exp_val
        cookies.append(cookie)
    return cookies


def _from_kv(text):
    cookies = []
    for pair in text.split(";"):
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        key, value = key.strip(), value.strip()
        if key:
            cookies.append({"name": key, "value": value, "domain": DOMAIN, "path": "/"})
    return cookies


def _from_json(text):
    try:
        data = json.loads(text)
    except ValueError:
        return []
    if isinstance(data, dict):
        data = data.get("cookies") or data.get("data") or [data]
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict) and item.get("name")]


# ----------------------------------------------------------------------- entry
def parse(text):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise CookieError("Nothing pasted.")
    lowered = text.lower()
    if lowered.startswith("cookie:"):
        text = text.split(":", 1)[1].strip()
    elif lowered.startswith("set-cookie:"):
        text = text.split(":", 1)[1].strip()

    rows = []
    if text[:1] in ("[", "{"):
        rows = _from_json(text)
    if not rows:
        rows = _from_netscape(text)
    if not rows:
        rows = _from_kv(text)

    jar = sanitize_playwright_cookies(rows)
    if not jar:
        raise CookieError("No dola.com cookies found in that paste.")
    return jar


def parse_file(path):
    try:
        text = path.read_text("utf-8", errors="replace")
    except OSError as exc:
        raise CookieError(f"Could not read {path}: {exc}") from exc
    return parse(text)


def to_playwright(rows):
    out = []
    for row in rows or []:
        row = dict(row)
        if row.get("sameSite") == "None":
            row["secure"] = True
        if row.get("expires") in (None, ""):
            row.pop("expires", None)
        out.append(row)
    return out


def account_cookies(config, name):
    account = (config.get("accounts") or {}).get(name) or {}
    return list(account.get("cookies") or [])


def check(rows):
    """('none'|'session'|'ok'|'expiring'|'expired', seconds_left)."""
    if not rows:
        return "none", None
    stamps = [int(c["expires"]) for c in rows if c.get("expires")]
    if not stamps:
        return "session", None
    left = min(stamps) - int(time.time())
    if left <= 0:
        return "expired", left
    if left < 86400:
        return "expiring", left
    return "ok", left