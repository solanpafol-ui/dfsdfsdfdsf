"""Browser backend: drives dola.com in a real Chrome window.

  * fetch/XHR body rewrite forcing 30 s
  * FR/EU sessionStorage + cookie injection + overlay removal
  * fingerprint shield, as the bundled extension under ``bypass_ext/``
  * Method 1 — attaches a skill that is already installed on the account
    (Skills page → Manage → Mine → row → 3 dots → Try in New Chat → chip
    check) and only then types the brief. The skill carries the 30 s /
    Seedance 2.5 recipe, so Method 1 requires one and fails loudly without it.
    Skill *registration* on the account stays manual.
  * Method 2 — re-stamps the region and reloads once, for the hard geo gate

Each account gets its own Chrome profile directory, keyed by a stable account id.
A per-profile lock stops two jobs from fighting over the same user-data-dir.
Stale Chromium singleton files are cleaned before every launch.
The render is fetched with a four-step fallback so a stalled CDN URL cannot
hang the job.
"""
import base64
import hashlib
import os
import re
import threading
import time
from pathlib import Path

from .providers import ProviderError, _poster_from_video

try:
    from . import cookies as ck
except ImportError:                                   # frozen / flat layouts
    ck = None

try:
    from . import skills as skills_mod
except ImportError:
    skills_mod = None

try:
    from . import winhide
except ImportError:
    winhide = None

SIGNIN_URL = "https://dola.com/"
CHAT_URL = "https://dola.com/chat"
SKILLS_URLS = ("https://dola.com/chat/skills", "https://www.dola.com/chat/skills")

MODE_WORDS = {
    "i2v": ("image to video", "이미지", "i2v"),
    "legit": ("image to video", "이미지", "i2v"),
    "r2v": ("reference", "레퍼런스", "r2v"),
}

# 스킬 행을 찾을 때 마지막으로 시도하는 기본 이름들. 계정에 설치된 이름이
# 다르면 설정의 "스킬 행 이름"과 SKILL.md 의 name 이 먼저 쓰인다.
SKILL_NAME_FALLBACKS = ("Dola Seedance", "Seedance", "Vidopro", "MianBrothers")

MANAGE_WORDS = ("Manage",)
MINE_WORDS = ("Mine", "My skills", "내 스킬")
NEW_CHAT_WORDS = ("Try in New Chat", "Try in new chat", "Try in chat", "New Chat")

FORCE30_JS = """(() => {
    const TARGET = 30;
    const KEYS = ['duration', 'seconds', 'video_length', 'duration_seconds'];
    const fixText = (t) => {
        for (const k of KEYS) {
            t = t.replace(new RegExp('("' + k + '"\\\\s*:\\\\s*)(\\\\d+)', 'g'), '$1' + TARGET);
        }
        return t;
    };
    const fix = (body) => {
        if (!body) return body;
        if (typeof body === 'string') {
            const s = fixText(body);
            if (s === body) return body;
            try {
                const j = JSON.parse(s);
                for (const k of KEYS) if (k in j) j[k] = TARGET;
                return JSON.stringify(j);
            } catch (e) { return s; }
        }
        if (body instanceof URLSearchParams) {
            for (const k of KEYS) if (body.has(k)) body.set(k, String(TARGET));
            return body;
        }
        return body;
    };
    const _fetch = window.fetch;
    window.fetch = function (input, init) {
        try {
            if (init && init.body) init = Object.assign({}, init, { body: fix(init.body) });
        } catch (e) {}
        return _fetch.apply(this, arguments.length > 1 ? [input, init] : [input]);
    };
    const _send = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function (body) {
        return _send.call(this, fix(body));
    };
})();"""

REGION_JS = """(() => {
    const stamp = () => {
        try { sessionStorage.setItem('country_code', 'FR'); } catch (e) {}
        const set = (k, v) => {
            document.cookie = k + '=' + v +
                '; path=/; domain=.dola.com; max-age=31536000; SameSite=Lax';
        };
        set('country', 'FR');
        set('region', 'EU');
        set('country_code', 'FR');
    };
    stamp();
    window.addEventListener('DOMContentLoaded', stamp);
})();"""

NEUTER_JS = """(() => {
    const RE = /region\\s*restricted|not available in your (region|country)/i;
    const kill = () => {
        const nodes = document.querySelectorAll('div, section, aside, p, span');
        for (const n of nodes) {
            if (n.dataset.mdNeutered) continue;
            const t = (n.innerText || '').trim();
            if (!t || t.length > 400 || !RE.test(t)) continue;
            const box = n.closest('[role="dialog"], .fixed, section') || n;
            if (box && box.parentNode) {
                box.dataset.mdNeutered = '1';
                box.style.display = 'none';
            }
        }
    };
    window.addEventListener('DOMContentLoaded', () => {
        kill();
        new MutationObserver(kill).observe(document.body, { childList: true, subtree: true });
    });
})();"""

SET_MODE_JS = """(words) => {
    const els = Array.from(document.querySelectorAll(
        'button, [role="tab"], [role="radio"], label'));
    for (const w of words) {
        const hit = els.find(e =>
            ((e.innerText || e.getAttribute('aria-label') || '')).toLowerCase().includes(w));
        if (hit) { hit.click(); return w; }
    }
    return null;
}"""

CHECK_LOGIN_JS = """(() => {
    const btnText = Array.from(document.querySelectorAll('button, a, [role="button"]'))
        .map(e => (e.innerText || e.getAttribute('aria-label') || '').toLowerCase())
        .join(' | ');
    const loginRe = /log ?in|sign ?in|sign ?up|get started|continue with|create (an )?account|try for free/;
    const loginBtn = loginRe.test(btnText);
    const composer = !!document.querySelector(
        "#prompt-textarea, form textarea, form div[contenteditable='true'], textarea");
    const onAuthPath = /log-?in|sign-?in|sign-?up|auth|oauth/i.test(location.pathname);
    return { loginBtn, composer, onAuthPath, path: location.pathname };
})()"""

FETCH_B64_JS = """async (u) => {
    const r = await fetch(u, { credentials: 'include' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const b = await r.blob();
    return await new Promise((res, rej) => {
        const fr = new FileReader();
        fr.onload = () => res(fr.result);
        fr.onerror = () => rej(new Error('read failed'));
        fr.readAsDataURL(b);
    });
}"""

# --- Method 1 helpers -------------------------------------------------------
CLICK_WORDS_JS = """(words) => {
    const els = Array.from(document.querySelectorAll(
        'button, [role="button"], [role="tab"], [role="menuitem"], a, li, span, div'));
    for (const w of words) {
        const exact = new RegExp('^\\\\s*' + w + '\\\\s*$', 'i');
        const loose = new RegExp(w, 'i');
        let hit = els.find(e => {
            const t = (e.innerText || '').trim();
            const a = (e.getAttribute('aria-label') || '').trim();
            return (t && t.length < 60 && (exact.test(t) || exact.test(a)));
        });
        if (!hit) {
            hit = els.find(e => {
                const t = (e.innerText || '').trim();
                const a = (e.getAttribute('aria-label') || '').trim();
                const r = e.getBoundingClientRect();
                return r.width > 0 && r.height > 0 && t.length < 80 &&
                       (loose.test(t) || loose.test(a));
            });
        }
        if (hit) { hit.scrollIntoView({ block: 'center' }); hit.click(); return true; }
    }
    return false;
}"""

M1_ROW_JS = """(words) => {
    const els = Array.from(document.querySelectorAll(
        'div, li, tr, section, article, [role="row"], [role="listitem"]'));
    const found = [];
    for (const e of els) {
        const t = (e.innerText || '').trim();
        if (!t || t.length > 400) continue;
        let matched = false;
        for (const w of words) {
            if (new RegExp(w, 'i').test(t)) { matched = true; break; }
        }
        if (!matched) continue;
        const r = e.getBoundingClientRect();
        if (r.width < 60 || r.height < 20 || r.height > 220) continue;
        found.push({ el: e, area: r.width * r.height });
    }
    if (!found.length) return null;
    found.sort((a, b) => a.area - b.area);
    const el = found[0].el;
    document.querySelectorAll('[data-md-skill-row]').forEach(
        n => n.removeAttribute('data-md-skill-row'));
    el.setAttribute('data-md-skill-row', '1');
    el.scrollIntoView({ block: 'center' });
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height,
             text: (el.innerText || '').trim().slice(0, 140) };
}"""

M1_DOTS_JS = """() => {
    const row = document.querySelector('[data-md-skill-row]');
    if (!row) return null;
    const visible = (e) => {
        const r = e.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };
    const dots = (e) => {
        const t = (e.innerText || '').trim();
        const a = (e.getAttribute('aria-label') || '').trim();
        const h = (e.getAttribute('title') || '').trim();
        if (/more|option|menu|dots|kebab/i.test(a + ' ' + h)) return true;
        return ['⋮', '⋯', '•••', '...', '…'].includes(t);
    };
    const cands = Array.from(row.querySelectorAll('button, [role="button"]'))
        .filter(visible);
    let hit = cands.find(dots);
    if (!hit) hit = cands[cands.length - 1] || null;
    if (!hit) {
        const all = Array.from(row.querySelectorAll('*')).filter(visible).filter(dots);
        hit = all[0] || null;
    }
    if (!hit) return null;
    hit.scrollIntoView({ block: 'center' });
    hit.click();
    return true;
}"""

CHIP_JS = """(words) => {
    const scope = document.querySelector('form') || document.body;
    const els = Array.from(scope.querySelectorAll('span, div, button, li'));
    const out = [];
    for (const e of els) {
        const t = (e.innerText || '').trim();
        if (!t || t.length > 60) continue;
        for (const w of words) {
            if (new RegExp(w, 'i').test(t)) { out.push(t); break; }
        }
        if (out.length >= 5) break;
    }
    return out;
}"""

# 좁은 것부터. [role='textbox'] 는 검색창까지 잡으므로 맨 뒤로 뺐다.
SEL = {
    "composer": ["#prompt-textarea", "form div[contenteditable='true']",
                 "form textarea", "textarea[placeholder]",
                 "div[contenteditable='true']", "[role='textbox']"],
    "send": ["button[aria-label*='send' i]", "button[aria-label*='generate' i]",
             "button[type='submit']"],
    "video": ["video[src]", "video source[src]", "a[href*='.mp4']"],
    "captcha": ["iframe[src*='turnstile']", "iframe[src*='hcaptcha']",
                "iframe[src*='recaptcha']", "[id*='captcha' i]"],
    "busy": ["[aria-label*='stop' i]", "[data-state='loading']"],
    "file": ["input[type='file']"],
    "download": ["a[download]", "button[aria-label*='download' i]",
                 "a[aria-label*='download' i]", "[title*='download' i]",
                 "button:has-text('Download')", "a:has-text('Download')"],
    "menu": ["[role='menu']", "[role='menuitem']"],
}

FAIL_TEXT = ("SEEDANCE_UNAVAILABLE", "try again later")

_EXT_DIR = Path(__file__).with_name("bypass_ext")

_LOCKS = {}
_LOCK_GUARD = threading.Lock()


def _lock_for(key):
    with _LOCK_GUARD:
        return _LOCKS.setdefault(str(key), threading.Lock())


def _extension_args():
    """Point Chrome at the bundled shield, when the folder is present."""
    if not (_EXT_DIR / "manifest.json").is_file():
        return []
    return [f"--load-extension={_EXT_DIR}",
            f"--disable-extensions-except={_EXT_DIR}"]


def _slug(key):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(key)).strip("-")[:32]


def _folder_name(key):
    """빈 slug(한글 이름 등)는 해시로 대신한다. 계정마다 폴더가 갈린다."""
    s = _slug(key)
    if s:
        return f"browser_profile-{s}"
    return "browser_profile-h" + hashlib.sha1(
        str(key).encode("utf-8")).hexdigest()[:12]


def profile_folder(data_dir, key, legacy_key=None):
    """Deterministic profile path for an account.

    legacy_key 는 이름 기반 시절 폴더. 있으면 한 번만 새 폴더로 옮긴다.
    """
    raw = data_dir or os.path.join(
        os.environ.get("LOCALAPPDATA") or str(Path.home()), "MotionDeck")
    target = Path(raw) / _folder_name(key)
    if legacy_key and str(legacy_key) != str(key):
        legacy = Path(raw) / _folder_name(legacy_key)
        if not target.exists() and legacy.exists() and legacy != target:
            try:
                legacy.rename(target)
            except OSError:
                pass
    return target


def clean_singleton(folder):
    """죽은 Chrome 이 남긴 프로필 잠금 파일을 지운다. 프로필 데이터는 안 건드린다."""
    removed = []
    try:
        entries = list(Path(folder).iterdir())
    except OSError:
        return removed
    for p in entries:
        if p.name.startswith("Singleton"):
            try:
                p.unlink()
                removed.append(p.name)
            except OSError:
                pass
    return removed


def _profile_dir(ctx, job):
    name = job.get("account") or job.get("profile") or ""
    key = job.get("account_id") or name or "default"
    return profile_folder(ctx.config.get("data_dir"), key, legacy_key=name or None)


def _first(page, selectors, timeout=4000):
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=timeout):
                return loc
        except Exception:
            continue
    return None


def _any_visible(page, selectors):
    return _first(page, selectors, timeout=800) is not None


def _set_mode(page, mode):
    words = MODE_WORDS.get(mode or "t2v")
    if not words:
        return None
    try:
        return page.evaluate(SET_MODE_JS, list(words))
    except Exception:
        return None


def _attach_refs(page, paths):
    if not paths:
        return 0
    target = _first(page, SEL["file"], timeout=4000)
    if target is None:
        return 0
    try:
        target.set_input_files(list(paths))
    except Exception:
        return 0
    page.wait_for_timeout(1200)
    return len(paths)


def _goto_composer(page, ctx, seconds=45):
    """입력창이 실제로 잡힐 때까지 경로를 해석한다."""
    for url in (CHAT_URL, SIGNIN_URL):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        except Exception:
            continue
        deadline = time.time() + seconds
        while time.time() < deadline:
            ctx.check()
            box = _first(page, SEL["composer"], timeout=300)
            if box is not None:
                return box
            ctx.sleep(0.8)
    return None


def _ensure_signed_in(page, ctx, hider=None, seconds=180):
    """로그인 화면이 걷히고 8초 연속 안정적일 때만 통과.

    랜딩 페이지에 입력창이 있어도 로그인 버튼이 남아 있으면 기다린다.
    """
    deadline = time.time() + seconds
    announced = False
    stable = 0
    while time.time() < deadline:
        ctx.check()
        try:
            state = page.evaluate(CHECK_LOGIN_JS)
        except Exception:
            stable = 0
            ctx.sleep(1.0)
            continue
        if state.get("composer") and not state.get("loginBtn") \
                and not state.get("onAuthPath"):
            stable += 1
            if stable >= 8:
                return True
        else:
            stable = 0
            if not announced:
                if hider:
                    hider.show()
                try:
                    page.bring_to_front()
                except Exception:
                    pass
                ctx.progress(0.1, "Sign in inside the Chrome window — waiting")
                announced = True
        ctx.sleep(1.0)
    return False


def _click_download(page):
    """결과 카드의 다운로드 버튼을 누른다. 맨 마지막(최신) 것을 고른다."""
    for sel in SEL["download"]:
        try:
            loc = page.locator(sel).last
            if loc.count() and loc.is_visible(timeout=800):
                loc.click(timeout=5000)
                return True
        except Exception:
            continue
    return False


def _save_b64(data, final):
    text = str(data)
    if "," not in text:
        raise ValueError("not a data URL")
    final.write_bytes(base64.b64decode(text.split(",", 1)[1]))


def _download(page, browser, src, final, ctx):
    """네 단계로 받는다. 앞 단계가 실패하면 다음으로 넘어간다."""
    if src.startswith("//"):
        src = "https:" + src
    tries = []

    if src.startswith("data:"):
        _save_b64(src, final)
        return

    if src.startswith("blob:"):
        ctx.progress(0.86, "Downloading 1/4 — in-page blob")
        try:
            _save_b64(page.evaluate(FETCH_B64_JS, src), final)
            return
        except Exception as exc:
            tries.append(f"blob {type(exc).__name__}")

    ctx.progress(0.86, "Downloading 2/4 — direct request")
    for attempt in (1, 2):
        try:
            resp = browser.request.get(
                src, timeout=60_000,
                headers={"Referer": "https://dola.com/",
                         "Origin": "https://dola.com"})
            if resp.ok:
                body = resp.body()
                if body:
                    final.write_bytes(body)
                    return
            tries.append(f"HTTP {resp.status}")
        except Exception as exc:
            tries.append(f"req{attempt} {type(exc).__name__}")
        time.sleep(1.5)

    ctx.progress(0.9, "Downloading 3/4 — in-page fetch")
    try:
        _save_b64(page.evaluate(FETCH_B64_JS, src), final)
        return
    except Exception as exc:
        tries.append(f"fetch {type(exc).__name__}")

    ctx.progress(0.94, "Downloading 4/4 — download button")
    try:
        with page.expect_download(timeout=90_000) as info:
            if not _click_download(page):
                raise RuntimeError("no download button")
        info.value.save_as(str(final))
        if final.exists() and final.stat().st_size > 0:
            return
        tries.append("empty file")
    except Exception as exc:
        tries.append(f"button {type(exc).__name__}")

    raise ProviderError("Could not download the render (" + ", ".join(tries) + ")")


# ------------------------------------------------------------------ Method 1
def _rx(word):
    return re.escape(str(word).strip())


def _skill_words(ctx, job):
    """스킬 행을 찾을 후보 이름들. 설정 → 선택한 스킬 이름 → 기본값 순."""
    words = []
    explicit = (ctx.config.get("skill_row_name") or "").strip()
    if explicit:
        words.append(explicit)
    row_override = (job.get("skill_row") or "").strip()
    if row_override:
        words.append(row_override)
    skill_id = job.get("skill") or ""
    if skill_id and skills_mod is not None:
        try:
            skill = skills_mod.load(skill_id)
        except Exception:
            skill = None
        if skill:
            meta = skill.get("meta") or {}
            for key in ("name", "title", "label"):
                value = (meta.get(key) or "").strip()
                if value:
                    words.append(value)
            if skill_id:
                words.append(skill_id)
    for word in SKILL_NAME_FALLBACKS:
        words.append(word)
    out = []
    seen = set()
    for word in words:
        key = word.lower()
        if word and key not in seen:
            seen.add(key)
            out.append(word)
    return out


def _chip_words(ctx, job):
    words = []
    explicit = (ctx.config.get("skill_chip_name") or "").strip()
    if explicit:
        words.append(explicit)
    for word in _skill_words(ctx, job)[:3]:
        words.append(word)
    out = []
    seen = set()
    for word in words:
        key = word.lower()
        if word and key not in seen:
            seen.add(key)
            out.append(word)
    return out


def _click_words(page, words, ctx=None, tries=3, delay=0.8):
    """버튼/탭/메뉴 항목을 글자로 누른다. Playwright 실패 시 JS로 재시도."""
    pats = [re.compile(_rx(w), re.I) for w in words if w]
    for attempt in range(max(1, tries)):
        if ctx is not None:
            ctx.check()
        for role in ("button", "tab", "menuitem", "link"):
            for pat in pats:
                try:
                    loc = page.get_by_role(role, name=pat).first
                    if loc.count() and loc.is_visible(timeout=600):
                        loc.click(timeout=5000)
                        return True
                except Exception:
                    continue
        try:
            if page.evaluate(CLICK_WORDS_JS, list(words)):
                return True
        except Exception:
            pass
        time.sleep(delay)
    return False


def _follow_new_page(browser, page):
    """Try in New Chat 이 새 탭을 열면 그 탭으로 옮겨간다."""
    try:
        pages = browser.pages
    except Exception:
        return page
    for candidate in reversed(pages):
        if candidate is not page:
            try:
                if "skills" not in (candidate.url or ""):
                    return candidate
            except Exception:
                continue
    return page


def _find_skill_row(page, ctx, words):
    row = None
    for attempt in range(6):
        ctx.check()
        if attempt in (2, 4):
            _click_words(page, MINE_WORDS, ctx, tries=1, delay=0.4)
            ctx.sleep(0.8)
        try:
            info = page.evaluate(M1_ROW_JS, words)
        except Exception:
            info = None
        if info:
            row = page.locator("[data-md-skill-row]").first
            if row.count():
                return row
            row = None
        ctx.sleep(1.0)
    return None


def _hover_row(page, row):
    try:
        row.hover(timeout=5000)
        return True
    except Exception:
        pass
    try:
        box = row.bounding_box()
        if box:
            page.mouse.move(box["x"] + box["width"] / 2,
                            box["y"] + box["height"] / 2)
            return True
    except Exception:
        pass
    return False


def _open_row_menu(page, row, ctx):
    for attempt in range(3):
        ctx.check()
        clicked = False
        try:
            clicked = bool(page.evaluate(M1_DOTS_JS))
        except Exception:
            clicked = False
        if clicked:
            ctx.sleep(0.6)
            if _any_visible(page, SEL["menu"]):
                return True
            try:
                box = row.bounding_box()
                if box:
                    x = box["x"] + box["width"] - 16
                    y = box["y"] + box["height"] / 2
                    page.mouse.move(x, y)
                    ctx.sleep(0.3)
                    page.mouse.click(x, y)
                    ctx.sleep(0.7)
                    if _any_visible(page, SEL["menu"]):
                        return True
            except Exception:
                pass
        _hover_row(page, row)
        ctx.sleep(1.0)
    return False

def _use_skill(browser, page, ctx, job):
    """설치된 스킬을 골라 새 채팅에 붙이고, 그 페이지를 돌려준다.

    스킬 없이는 30 s / Seedance 2.5 레시피가 실리지 않으므로, 어느 단계든
    실패하면 ProviderError 로 올린다.
    """
    words = [_rx(w) for w in _skill_words(ctx, job)]
    chip_words = [_rx(w) for w in _chip_words(ctx, job)]

    ctx.progress(0.14, "Opening the skills page")
    landed = False
    for url in SKILLS_URLS:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        except Exception:
            continue
        if "/skills" in (page.url or ""):
            landed = True
            break
    if not landed:
        raise ProviderError("Could not open dola.com/chat/skills.")
    ctx.sleep(1.6)

    ctx.progress(0.15, "Skills → Manage")
    if not _click_words(page, MANAGE_WORDS, ctx):
        raise ProviderError(
            "The 'Manage' button was not found on the skills page. "
            "Make sure the account is signed in and the skills page loads.")
    ctx.sleep(1.0)

    ctx.progress(0.16, "Skills → Mine")
    _click_words(page, MINE_WORDS, ctx, tries=2)
    ctx.sleep(1.0)

    ctx.progress(0.17, "Looking for the skill row")
    row = _find_skill_row(page, ctx, words)
    if row is None:
        raise ProviderError(
            "The skill was not found under Manage → Mine. Register the SKILL.md "
            "on this account first, or set the exact row name in Settings.")

    _hover_row(page, row)
    ctx.sleep(0.6)

    ctx.progress(0.18, "Opening the skill menu (3 dots)")
    if not _open_row_menu(page, row, ctx):
        raise ProviderError("The skill's 3-dot menu did not open.")

    ctx.progress(0.19, "Try in New Chat")
    if not _click_words(page, NEW_CHAT_WORDS, ctx, tries=3):
        raise ProviderError("'Try in New Chat' was not in the skill menu.")

    page = _follow_new_page(browser, page)
    deadline = time.time() + 25
    while time.time() < deadline:
        ctx.check()
        if "/skills" not in (page.url or ""):
            break
        ctx.sleep(0.8)
    if "/skills" in (page.url or ""):
        raise ProviderError(
            "The skill was picked but Dola stayed on the skills page, so a "
            "prompt there would be wrong. Retry, or reload dola.com.")

    ctx.progress(0.2, "Verifying the skill chip")
    chip_seen = []
    deadline = time.time() + 12
    while time.time() < deadline:
        ctx.check()
        try:
            chip_seen = page.evaluate(CHIP_JS, chip_words) or []
        except Exception:
            chip_seen = []
        if chip_seen:
            break
        ctx.sleep(0.6)
    if chip_seen:
        ctx.progress(0.21, f"Skill attached: {chip_seen[0][:40]}")
    else:
        ctx.progress(0.21, "Chip not seen — carrying on")

    box = None
    deadline = time.time() + 30
    while time.time() < deadline:
        ctx.check()
        box = _first(page, SEL["composer"], timeout=400)
        if box is not None:
            break
        ctx.sleep(0.6)
    if box is None:
        raise ProviderError("The new chat from the skill never showed a prompt box.")
    return page


def run_browser_job(job, ctx):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ProviderError(
            "Playwright is not installed. Run: pip install playwright "
            "then: playwright install chromium") from exc

    profile = _profile_dir(ctx, job)
    profile.mkdir(parents=True, exist_ok=True)
    args = ["--start-maximized", "--disable-blink-features=AutomationControlled"]
    args += _extension_args()
    method = int(job.get("method") or 1)
    name = job.get("account") or job.get("profile") or "this account"

    if method == 1 and not (job.get("skill") or "").strip():
        raise ProviderError(
            "Method 1 renders through a Dola skill — pick a skill in the "
            "workspace's skill menu (or switch to M2).")

    lock = _lock_for(profile)
    if not lock.acquire(blocking=False):
        ctx.progress(0.02, "Waiting for this account's browser")
        while not lock.acquire(timeout=0.5):
            ctx.check()

    hider = None
    try:
        clean_singleton(profile)
        if ctx.config.get("hide_window", True) and winhide is not None and winhide.IS_WIN:
            try:
                hider = winhide.Hider()
            except Exception:
                hider = None

        ctx.progress(0.03, "Launching Chrome")
        with sync_playwright() as pw:
            browser = pw.chromium.launch_persistent_context(
                str(profile), headless=False, args=args, no_viewport=True,
                accept_downloads=True)
            try:
                page = browser.pages[0] if browser.pages else browser.new_page()
                for script in (FORCE30_JS, REGION_JS, NEUTER_JS):
                    browser.add_init_script(script)

                rows = job.get("cookies") or []
                if rows and ck is not None:
                    try:
                        jar = ck.to_playwright(rows)
                        if jar:
                            browser.add_cookies(jar)
                            ctx.progress(0.05, f"{len(jar)} saved cookie(s) loaded")
                    except Exception:
                        pass

                ctx.progress(0.06, "Opening dola.com")
                box = _goto_composer(page, ctx)
                if box is None:
                    if not _ensure_signed_in(page, ctx, hider):
                        raise ProviderError(
                            f"{name} is not signed in. Open the account badge → "
                            f"Manage accounts → Sign in, then retry.")
                    box = _goto_composer(page, ctx)
                elif not _ensure_signed_in(page, ctx, hider, seconds=40):
                    ctx.progress(0.12, "Login still open — carrying on")
                if box is None:
                    raise ProviderError("The prompt box never appeared.")

                if _any_visible(page, SEL["captcha"]):
                    if hider:
                        hider.show()
                    ctx.progress(0.15, "Captcha — solve it in the Chrome window")
                    deadline = time.time() + 300
                    while time.time() < deadline and _any_visible(page, SEL["captcha"]):
                        ctx.check()
                        ctx.sleep(1.0)
                    if _any_visible(page, SEL["captcha"]):
                        raise ProviderError("The captcha was not solved in time.")

                if method == 1:
                    page = _use_skill(browser, page, ctx, job)
                    box = _first(page, SEL["composer"], timeout=5000)
                    if box is None:
                        raise ProviderError("The skill chat has no prompt box.")
                elif method >= 2:
                    ctx.progress(0.17, "Method 2 — re-stamping the region")
                    try:
                        page.evaluate(REGION_JS)
                    except Exception:
                        pass
                    ctx.sleep(0.6)
                    page.reload(wait_until="domcontentloaded", timeout=90_000)
                    box = _first(page, SEL["composer"], timeout=15_000)
                    if box is None:
                        raise ProviderError("The composer did not come back after the reload.")

                mode = job.get("mode") or "t2v"
                refs = [p for p in (job.get("references") or []) if p]
                if mode != "t2v" and (method != 1 or refs):
                    picked = _set_mode(page, mode)
                    ctx.progress(0.22, f"Mode: {picked or mode}")
                    ctx.sleep(0.8)
                if refs:
                    sent = _attach_refs(page, refs[:10])
                    if sent:
                        ctx.progress(0.23, f"{sent} reference image(s) attached")

                if method == 1:
                    # 스킬이 이미 레시피를 들고 있으므로 원문 브리프만 넣는다.
                    text = (job.get("prompt") or "").strip()
                else:
                    text = (job.get("final_prompt") or job.get("prompt") or "").strip()
                if not text:
                    raise ProviderError("The brief is empty.")

                ctx.progress(0.24, "Typing the brief")
                box.click()
                try:
                    box.fill(text)
                except Exception:
                    page.keyboard.type(text, delay=4)
                if len((box.inner_text() or "").strip()) < max(8, len(text) // 4):
                    box = _first(page, SEL["composer"][:4], timeout=4000) or box
                    box.click()
                    page.keyboard.type(text, delay=4)

                send = _first(page, SEL["send"], timeout=4000)
                if send is not None:
                    send.click()
                else:
                    page.keyboard.press("Enter")

                ctx.progress(0.25, "Submitted — waiting for the clip")
                deadline = time.time() + 60 * 20
                src = None
                while time.time() < deadline:
                    ctx.check()
                    ctx.sleep(6.0)
                    body = (page.inner_text("body") or "")[:20000]
                    if any(f in body for f in FAIL_TEXT) and not _any_visible(page, SEL["busy"]):
                        raise ProviderError("dola.com answered SEEDANCE_UNAVAILABLE.")
                    loc = _first(page, SEL["video"], timeout=800)
                    if loc is not None:
                        src = loc.get_attribute("src")
                        if src:
                            break
                if not src:
                    raise ProviderError("No video appeared within 20 minutes.")

                ctx.progress(0.85, "Render ready — saving")
                folder = Path(job["folder"])
                final = folder / f"{job['id']}.mp4"
                _download(page, browser, src, final, ctx)

                poster = _poster_from_video(final, folder / "poster.png")
                if poster:
                    job["poster"] = str(poster)
                ctx.progress(1.0, "Done")
                return [str(final)]
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
    finally:
        if hider:
            hider.stop()
        try:
            lock.release()
        except RuntimeError:
            pass


def open_signin(profile_key, data_dir="", timeout=600, log=None):
    """Open dola.com in that account's own Chrome profile.

    페이지 상태 때문에 창이 죽지 않는다. goto 가 실패해도 창은 남는다.
    로그인이 확인되면 스스로 닫고 True, 사용자가 창을 닫거나 시간이 다 되면 False.
    """
    from playwright.sync_api import sync_playwright

    def say(msg):
        if log:
            try:
                log(msg)
            except Exception:
                pass

    folder = profile_folder(data_dir, profile_key)
    folder.mkdir(parents=True, exist_ok=True)
    say(f"signin: profile {folder}")
    args = ["--start-maximized", "--disable-blink-features=AutomationControlled"]
    args += _extension_args()

    lock = _lock_for(folder)
    got = lock.acquire(blocking=False)
    if not got:
        say("signin: profile is busy — waiting 25s")
        got = lock.acquire(timeout=25)
    if not got:
        say("signin: still busy — clearing stale profile locks")
        removed = clean_singleton(folder)
        say(f"signin: removed {removed or 'nothing'}")
        got = lock.acquire(timeout=10)
    if not got:
        raise ProviderError(
            "This account is busy: another sign-in or render is using it. "
            "Close every chrome.exe in Task Manager and try again.")
    try:
        removed = clean_singleton(folder)
        if removed:
            say(f"signin: cleared {removed}")

        with sync_playwright() as pw:
            say("signin: launching chrome")
            try:
                browser = pw.chromium.launch_persistent_context(
                    str(folder), headless=False, args=args, no_viewport=True)
            except Exception as exc:
                text = str(exc)
                say(f"signin: launch failed ({type(exc).__name__}: {text[:300]})")
                say("signin: retrying once after a lock clean")
                clean_singleton(folder)
                time.sleep(1.5)
                try:
                    browser = pw.chromium.launch_persistent_context(
                        str(folder), headless=False, args=args, no_viewport=True)
                except Exception as exc2:
                    say(f"signin: launch failed twice ({type(exc2).__name__}: {str(exc2)[:300]})")
                    raise ProviderError(f"Chrome could not start: {exc2}") from exc2
            say("signin: chrome started")
            try:
                for script in (FORCE30_JS, REGION_JS, NEUTER_JS):
                    try:
                        browser.add_init_script(script)
                    except Exception as exc:
                        say(f"signin: init script skipped ({exc})")
                try:
                    page = browser.pages[0] if browser.pages else browser.new_page()
                except Exception as exc:
                    say(f"signin: no page ({exc})")
                    return False
                say("signin: window up")
                try:
                    page.goto(SIGNIN_URL, wait_until="domcontentloaded", timeout=60_000)
                    say("signin: page loaded")
                except Exception as exc:
                    say(f"signin: goto failed ({type(exc).__name__}: {exc}) — window stays open")

                start = time.time()
                deadline = start + timeout
                stable = 0
                while time.time() < deadline:
                    try:
                        pages = browser.pages
                    except Exception:
                        say("signin: context gone")
                        break
                    if not pages:
                        say("signin: window closed by user")
                        break
                    if time.time() - start < 12:
                        time.sleep(1.0)
                        continue
                    try:
                        state = page.evaluate(CHECK_LOGIN_JS)
                    except Exception:
                        stable = 0
                        time.sleep(1.0)
                        continue
                    if state.get("composer") and not state.get("loginBtn") \
                            and not state.get("onAuthPath"):
                        stable += 1
                        if stable >= 8:
                            say("signin: logged in")
                            time.sleep(1.5)
                            return True
                    else:
                        stable = 0
                    time.sleep(1.0)
                say("signin: timed out without a login")
                return False
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
    finally:
        try:
            lock.release()
        except RuntimeError:
            pass