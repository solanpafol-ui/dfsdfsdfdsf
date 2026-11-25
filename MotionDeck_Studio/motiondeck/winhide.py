"""렌더 도중 Chrome 창을 숨긴다. 로그인·캡차 구간에서만 다시 보여준다.

Windows 전용. 실패해도 앱은 그대로 돌아간다(창이 보이는 상태로 남을 뿐).
"""
import ctypes
import threading
import time

IS_WIN = hasattr(ctypes, "windll")
_user32 = ctypes.windll.user32 if IS_WIN else None

SW_HIDE = 0
SW_SHOWMAXIMIZED = 3


def _titled_windows(fragment):
    """제목에 fragment 가 들어간 최상위 창들. 숨겨진 창도 찾는다."""
    if not IS_WIN:
        return []
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _lparam):
        n = _user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            _user32.GetWindowTextW(hwnd, buf, n + 1)
            if fragment.lower() in buf.value.lower():
                found.append(hwnd)
        return True

    try:
        _user32.EnumWindows(cb, 0)
    except Exception:
        return []
    return found


class Hider:
    def __init__(self, fragment="dola"):
        self.fragment = fragment
        self._visible = False
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop:
            if not self._visible:
                for hwnd in _titled_windows(self.fragment):
                    try:
                        _user32.ShowWindow(hwnd, SW_HIDE)
                    except Exception:
                        pass
            time.sleep(0.4)

    def show(self):
        """사용자가 봐야 할 때 — 꺼내서 맨 앞으로."""
        self._visible = True
        for hwnd in _titled_windows(self.fragment):
            try:
                _user32.ShowWindow(hwnd, SW_SHOWMAXIMIZED)
                _user32.SetForegroundWindow(hwnd)
            except Exception:
                pass

    def hide(self):
        self._visible = False

    def stop(self):
        self._stop = True