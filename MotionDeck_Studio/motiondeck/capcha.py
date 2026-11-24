"""슬라이더·캡차 감지와 해결.

자동으로 안 풀리면 on_manual()로 넘겨 사용자가 직접 풀게 한다.
"""

import time

SLIDER_JS = """() => {
    const ifr = Array.from(document.querySelectorAll('iframe'))
        .find(f => /captcha|turnstile|hcaptcha|recaptcha/i.test(f.src || ''));
    if (ifr) {
        const r = ifr.getBoundingClientRect();
        return { kind: 'iframe', x: r.left, y: r.top, w: r.width, h: r.height };
    }
    const knob = document.querySelector('[class*="slider" i] [class*="thumb" i], [class*="slider" i] [role="slider"]');
    if (knob) {
        const r = knob.getBoundingClientRect();
        return { kind: 'slider', x: r.left, y: r.top, w: r.width, h: r.height };
    }
    return null;
}"""


def detect(page):
    try:
        return page.evaluate(SLIDER_JS)
    except Exception:
        return None


def solve_slider(page, box):
    """thumb을 트랙 오른쪽 끝까지 끈다."""
    if not box or box.get("kind") != "slider":
        return False
    x = box["x"] + box["w"] / 2
    y = box["y"] + box["h"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    for i in range(1, 26):
        page.mouse.move(x + i * 9, y + (1 if i % 3 else 0))
        page.wait_for_timeout(22)
    page.mouse.up()
    page.wait_for_timeout(1800)
    return detect(page) is None


def wait_clear(page, timeout=90, on_manual=None):
    """캡차가 사라질 때까지. 오래 걸리면 수동 요청."""
    deadline = time.time() + timeout
    asked = False
    while time.time() < deadline:
        box = detect(page)
        if not box:
            return True
        if box.get("kind") == "slider":
            solve_slider(page, box)
        elif not asked and on_manual:
            on_manual(box)
            asked = True
        page.wait_for_timeout(1500)
    return detect(page) is None