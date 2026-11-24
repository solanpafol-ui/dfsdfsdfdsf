"""dola.com 조작 — 모드 선택, 프롬프트 입력, 제출, 결과 회수.

DOM이 바뀌어도 버티도록 aria-label·role·contenteditable 위주로 찾고,
셀렉터 하나에 의존하지 않는다.
"""

import os
import time
import urllib.request

STUDIO = "https://www.dola.com/studio"

MODES = {
    "t2v": ["text to video", "텍스트", "t2v"],
    "i2v": ["image to video", "이미지", "i2v"],
    "r2v": ["reference", "레퍼런스", "r2v"],
}

_JS_COMPOSER = """() => {
    const cands = Array.from(document.querySelectorAll(
        'textarea, [contenteditable="true"], div[role="textbox"]'));
    const vis = cands.filter(e => { const r = e.getBoundingClientRect(); return r.width > 80 && r.height > 20; });
    if (!vis.length) return null;
    const el = vis[vis.length - 1];
    el.focus();
    return true;
}"""

_JS_SUBMIT = """() => {
    const btns = Array.from(document.querySelectorAll('button, [role="button"]'));
    const hit = btns.find(b => {
        const a = ((b.getAttribute('aria-label') || '') + ' ' + (b.innerText || '')).toLowerCase();
        return a.includes('generate') || a.includes('생성') || a.includes('submit');
    });
    if (hit) { hit.click(); return true; }
    return false;
}"""

_JS_VIDEO = """() => {
    const v = Array.from(document.querySelectorAll('video'));
    for (let i = v.length - 1; i >= 0; i--) {
        const s = v[i].currentSrc || v[i].src;
        if (s && !s.startsWith('blob:')) return s;
        const src = v[i].querySelector('source');
        if (src && src.src) return src.src;
    }
    return null;
}"""


def open_studio(page):
    page.goto(STUDIO, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    return page


def set_mode(page, mode):
    words = MODES.get(mode or "t2v", MODES["t2v"])
    js = """(words) => {
        const els = Array.from(document.querySelectorAll('button, [role="tab"], [role="radio"], label'));
        for (const w of words) {
            const hit = els.find(e => ((e.innerText || e.getAttribute('aria-label') || '')).toLowerCase().includes(w));
            if (hit) { hit.click(); return w; }
        }
        return null;
    }"""
    return page.evaluate(js, words)


def fill_prompt(page, text):
    if not page.evaluate(_JS_COMPOSER):
        raise RuntimeError("프롬프트 입력칸을 못 찾았습니다.")
    page.keyboard.insert_text(text)
    page.wait_for_timeout(400)
    return True


def attach_refs(page, paths):
    """이미지/레퍼런스 모드에서 파일 첨부."""
    if not paths:
        return 0
    inputs = page.query_selector_all('input[type="file"]')
    if not inputs:
        return 0
    target = inputs[-1]
    target.set_input_files(list(paths))
    page.wait_for_timeout(1200)
    return len(paths)


def submit(page):
    if not page.evaluate(_JS_SUBMIT):
        page.keyboard.press("Enter")
    return True


def wait_result(page, timeout=900, on_event=None):
    """결과 영상 URL이 나올 때까지 폴링. 실패 시 None."""
    deadline = time.time() + timeout
    tick = 0
    while time.time() < deadline:
        url = page.evaluate(_JS_VIDEO)
        if url:
            return url
        tick += 1
        if on_event and tick % 10 == 0:
            on_event({"type": "wait", "elapsed": int(time.time() - (deadline - timeout))})
        if _failed(page):
            return None
        page.wait_for_timeout(1500)
    return None


def _failed(page):
    try:
        t = page.inner_text("body", timeout=2000)
    except Exception:
        return False
    return any(k in t for k in ("SEEDANCE_UNAVAILABLE", "currently unavailable", "생성 실패"))


def download(url, dest_dir, name="clip"):
    os.makedirs(dest_dir, exist_ok=True)
    out = os.path.join(dest_dir, f"{name}_{int(time.time())}.mp4")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(out, "wb") as f:
        while True:
            chunk = r.read(262144)
            if not chunk:
                break
            f.write(chunk)
    return out