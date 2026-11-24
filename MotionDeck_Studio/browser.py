"""Browser backend: drives dola.com in a real Chrome window.

The bypass layer from the original app rides along, split by where each piece
belongs:

  * fetch/XHR body rewrite forcing 30 s        (app6.py:4922, const TARGET = 30)
  * FR/EU sessionStorage + cookie injection    (app6.py:7062, 7092-7112)
  * "Region Restricted" overlay removal        (app6.py:5212)
  * fingerprint shield, as the bundled extension under ``bypass_ext/``
                                               (app6.py:342, 64614)

Account rotation is the persistent profile directory; watermark-free download
is the direct grab of the <video> source below.
"""
import os
import time
from pathlib import Path

from .providers import ProviderError, _poster_from_video

SITE = "https://dola.com/chat/skills"

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

SEL = {
    "composer": ["textarea", "div[contenteditable='true']", "[role='textbox']"],
    "send": ["button[aria-label*='send' i]", "button[aria-label*='generate' i]",
             "button[type='submit']"],
    "video": ["video[src]", "video source[src]", "a[href*='.mp4']"],
    "captcha": ["iframe[src*='turnstile']", "iframe[src*='hcaptcha']",
                "iframe[src*='recaptcha']", "[id*='captcha' i]"],
    "busy": ["[aria-label*='stop' i]", "[data-state='loading']"],
}

FAIL_TEXT = ("SEEDANCE_UNAVAILABLE", "currently unavailable", "try again later")

_EXT_DIR = Path(__file__).with_name("bypass_ext")


def _extension_args():
    """Point Chrome at the bundled shield, when the folder is present."""
    if not (_EXT_DIR / "manifest.json").is_file():
        return []
    return [f"--load-extension={_EXT_DIR}",
            f"--disable-extensions-except={_EXT_DIR}"]


def _data_dir(ctx):
    raw = ctx.config.get("data_dir") or os.path.join(
        os.environ.get("LOCALAPPDATA") or str(Path.home()), "MotionDeck")
    return Path(raw)


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


def run_browser_job(job, ctx):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ProviderError(
            "Playwright is not installed. Run: pip install playwright "
            "then: playwright install chromium") from exc

    profile = _data_dir(ctx) / "browser_profile"
    profile.mkdir(parents=True, exist_ok=True)
    args = ["--start-maximized", "--disable-blink-features=AutomationControlled"]
    args += _extension_args()

    ctx.progress(0.03, "Launching Chrome")
    with sync_playwright() as pw:
        browser = pw.chromium.launch_persistent_context(
            str(profile), headless=False, args=args, no_viewport=True,
            accept_downloads=True)
        try:
            page = browser.pages[0] if browser.pages else browser.new_page()
            for script in (FORCE30_JS, REGION_JS, NEUTER_JS):
                browser.add_init_script(script)

            ctx.progress(0.06, "Opening dola.com")
            page.goto(SITE, wait_until="domcontentloaded", timeout=90_000)

            box = _first(page, SEL["composer"], timeout=15_000)
            if box is None:
                ctx.progress(0.1, "Sign in inside the Chrome window")
                deadline = time.time() + 300
                while time.time() < deadline:
                    ctx.check()
                    box = _first(page, SEL["composer"], timeout=1000)
                    if box is not None:
                        break
                    ctx.sleep(1.0)
                if box is None:
                    raise ProviderError("No prompt box appeared. Sign in, then retry.")

            if _any_visible(page, SEL["captcha"]):
                ctx.progress(0.15, "Captcha — solve it in the Chrome window")
                deadline = time.time() + 300
                while time.time() < deadline and _any_visible(page, SEL["captcha"]):
                    ctx.check()
                    ctx.sleep(1.0)
                if _any_visible(page, SEL["captcha"]):
                    raise ProviderError("The captcha was not solved in time.")

            text = (job.get("final_prompt") or job.get("prompt") or "").strip()
            if not text:
                raise ProviderError("The brief is empty.")

            ctx.progress(0.2, "Typing the brief")
            box.click()
            try:
                box.fill(text)
            except Exception:
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
                ctx.sleep(3.0)
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

            ctx.progress(0.85, "Downloading the render")
            folder = Path(job["folder"])
            final = folder / f"{job['id']}.mp4"
            resp = browser.request.get(src, timeout=300_000)
            if not resp.ok:
                raise ProviderError(f"Download failed: HTTP {resp.status}")
            final.write_bytes(resp.body())

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