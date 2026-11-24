"""큐 소비 워커. 계정 하나를 잡아 브라우저를 열고 생성까지 돌린다.

이벤트는 dict로 on_event에 흘린다. 실패·취소 시 크레딧을 돌려준다.
"""

import os
import threading
import time

from . import browser as br
from . import captcha, cookies as ck, dola, gate, store


class Engine:
    def __init__(self, cfg, on_event=None, headless=False):
        self.cfg = cfg
        self.on_event = on_event or (lambda e: None)
        self.headless = headless
        self.queue = []
        self.stop = threading.Event()
        self._t = None
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- queue
    def enqueue(self, job):
        with self._lock:
            self.queue.append(job)
        self.on_event({"type": "queued", "job": job.get("id")})

    def cancel(self, job_id):
        with self._lock:
            for j in self.queue:
                if j.get("id") == job_id:
                    j["cancelled"] = True
                    self.on_event({"type": "cancelled", "job": job_id})
                    return True
        return False

    # ---------------------------------------------------------------- run
    def start(self):
        if self._t and self._t.is_alive():
            return
        self.stop.clear()
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def _loop(self):
        while not self.stop.is_set():
            job = self._next()
            if not job:
                time.sleep(0.5)
                continue
            self._run(job)

    def _next(self):
        with self._lock:
            while self.queue:
                job = self.queue.pop(0)
                if not job.get("cancelled"):
                    return job
        return None

    def _run(self, job):
        jid = job.get("id")
        acc = job.get("account")
        try:
            self.on_event({"type": "start", "job": jid, "account": acc})
            path = self._generate(job)
            job["file"] = path
            self.on_event({"type": "done", "job": jid, "file": path})
        except Exception as e:
            store.credit(self.cfg, acc, 1)
            self.on_event({"type": "error", "job": jid, "error": str(e)})
        finally:
            store.save(self.cfg)

    def _generate(self, job):
        acc = job.get("account")
        rows = store.get_cookies(self.cfg, acc)
        if not rows:
            raise RuntimeError(f"{acc}: 저장된 쿠키가 없습니다.")

        profile = os.path.join(store.home(), "profiles", acc)
        with br.Browser(profile, headless=self.headless) as b:
            b.attach(rows)
            dola.open_studio(b.page)
            if gate.blocked(b.page) == "login" or not b.logged_in():
                raise RuntimeError(f"{acc}: 세션이 만료됐습니다. 쿠키를 다시 넣어주세요.")
            captcha.wait_clear(b.page, on_manual=lambda box: self.on_event(
                {"type": "captcha", "job": job.get("id")}))

            dola.set_mode(b.page, job.get("mode"))
            dola.attach_refs(b.page, job.get("refs") or [])
            dola.fill_prompt(b.page, job.get("brief") or "")
            dola.submit(b.page)

            url = dola.wait_result(b.page, on_event=lambda e: self.on_event(
                {**e, "job": job.get("id")}))
            if not url:
                raise RuntimeError("결과 영상이 안 나왔습니다.")
            return dola.download(url, job.get("output_dir") or store.home(), job.get("id", "clip"))