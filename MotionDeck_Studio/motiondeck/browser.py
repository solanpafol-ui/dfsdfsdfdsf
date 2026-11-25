"""Browser backend: drives dola.com in a real Chrome window.

  * fetch/XHR body rewrite forcing 30 s
  * FR/EU sessionStorage + cookie injection + overlay removal
  * fingerprint shield, as the bundled extension under ``bypass_ext/``
  * M2 re-stamps and reloads once, for the hard geo gate

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
    from . import winhide
except ImportError:
    winhide = None

SIGNIN_URL = "https://dola.com/"
CHAT_URL = "https://dola.com/chat"

MODE_WORDS = {
    "i2v": ("image to video", "이미지", "i2v"),
    "legit": ("image to video", "이미지", "i2v"),
    "r2v": ("reference", "레퍼런스", "r2v"),
}

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

                if method >= 2:
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
                if mode != "t2v":
                    picked = _set_mode(page, mode)
                    ctx.progress(0.18, f"Mode: {picked or mode}")
                    ctx.sleep(0.8)
                    refs = [p for p in (job.get("references") or []) if p]
                    if refs:
                        sent = _attach_refs(page, refs[:10])
                        if sent:
                            ctx.progress(0.19, f"{sent} reference image(s) attached")

                text = (job.get("final_prompt") or job.get("prompt") or "").strip()
                if not text:
                    raise ProviderError("The brief is empty.")

                ctx.progress(0.2, "Typing the brief")
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