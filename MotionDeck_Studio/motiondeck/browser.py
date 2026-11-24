"""Playwright 지속 컨텍스트. 쿠키 부착과 로그인 확인까지.

스텔스: bypass_ext 확장을 메모리 경로에서 로드하고, webdriver 흔적을
init script로 지운다. 프로필은 계정별로 분리해 세션 충돌을 막는다.
"""

import os

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

try:
    from . import cookies as ck
except ImportError:
    import cookies as ck

EXT_DIR = os.path.join(os.path.dirname(__file__), "bypass_ext")
DOLA = "https://www.dola.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

_STEALTH = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = window.chrome || {runtime: {}};
Object.defineProperty(navigator, 'languages', {get: () => ['ko-KR', 'ko', 'en']});
"""

ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-features=IsolateOrigins,site-per-process",
]


class Browser:
    """계정 하나당 하나. start() → attach() → goto() → close()."""

    def __init__(self, profile_dir, headless=False):
        self.profile_dir = profile_dir
        self.headless = headless
        self._pw = None
        self.ctx = None
        self.page = None

    def start(self):
        if sync_playwright is None:
            raise RuntimeError("playwright 미설치: python -m pip install playwright")
        os.makedirs(self.profile_dir, exist_ok=True)
        self._pw = sync_playwright().start()
        args = list(ARGS)
        if os.path.isdir(EXT_DIR):
            args += [f"--disable-extensions-except={EXT_DIR}",
                     f"--load-extension={EXT_DIR}"]
        self.ctx = self._pw.chromium.launch_persistent_context(
            self.profile_dir,
            headless=self.headless,
            args=args,
            user_agent=UA,
            viewport={"width": 1280, "height": 860},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        self.ctx.add_init_script(_STEALTH)
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        return self

    def attach(self, rows):
        jar = ck.to_playwright(rows)
        if jar:
            self.ctx.add_cookies(jar)
        return len(jar)

    def goto(self, url=DOLA):
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        return self.page

    def logged_in(self):
        """로그인 표식 확인. 실패하면 False."""
        try:
            self.page.wait_for_timeout(1500)
            js = """() => {
                const t = document.body ? document.body.innerText : '';
                if (/로그아웃|Log\\s*out|Sign\\s*out|My\\s*page|마이페이지/i.test(t)) return true;
                if (/로그인|Sign\\s*in|Log\\s*in/i.test(t)) return false;
                return !!document.querySelector('img[alt*="avatar" i], [data-testid*="avatar" i]');
            }"""
            return bool(self.page.evaluate(js))
        except Exception:
            return False

    def close(self):
        try:
            if self.ctx:
                self.ctx.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self.ctx = self.page = self._pw = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *a):
        self.close()