"""Job runner: a small scheduler with a configurable number of slots.

The original drives dola.com through a browser with an account-rotation,
fingerprint and prompt-laundering layer on top. That whole path is left out.
`BrowserSlot` below is the empty seat where it used to be: it deliberately
refuses to generate. Real renders come only from the official Ark API.
"""
import threading
import time
import traceback

from . import skills as skills_mod
from .providers import Cancelled, Ctx, ProviderError
from .store import now_ms


class BrowserSlot:
    """The original generation slot, intentionally left empty.

    In the deployed app this seat held the browser automation and its
    account/fingerprint layer. It is kept as a named, honest gap so the
    shape of the original is visible without reproducing that behaviour.
    """

    label = "browser engine slot (empty)"

    def run(self, job, ctx):
        ctx.progress(0.0, "Browser slot empty")
        raise ProviderError(
            "Browser engine slot is empty. Use the Ark API backend to render.")

def get(provider_id):
    """Resolve the configured backend. The browser slot stays unimplemented."""
    from . import providers as providers_mod
    return providers_mod.get(provider_id) or BrowserSlot()


class Engine:
    def __init__(self, store, emit):
        self.store = store
        self.emit = emit          # emit(kind, job) -- called from worker threads
        self._queue = []
        self._active = {}
        self._cancel = {}
        self._lock = threading.Lock()
        self._stop = False
        self._thread = threading.Thread(target=self._dispatch, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ public
    def submit(self, job):
        job["status"] = "queued"
        job["stage"] = "Queued"
        with self._lock:
            self.store.add(job)
            self._queue.append(job)
        self.emit("queued", job)
        return job

    def cancel(self, job_id):
        with self._lock:
            flag = self._cancel.get(job_id)
            if flag is not None:
                flag.append(True)
                return True
            for job in self._queue:
                if job["id"] == job_id:
                    self._queue.remove(job)
                    job["status"] = "cancelled"
                    job["stage"] = "Cancelled"
                    job["finished_ms"] = now_ms()
                    return True
        job = self.store.get(job_id)
        if job and job["status"] == "queued":
            job["status"] = "cancelled"
            job["stage"] = "Cancelled"
            job["finished_ms"] = now_ms()
            self.store.save_jobs()
            self.emit("update", job)
            return True
        return False

    def retry(self, job_id):
        job = self.store.get(job_id)
        if not job or job["status"] not in ("failed", "cancelled"):
            return None
        job.update({"status": "queued", "progress": 0.0, "stage": "Queued", "error": "",
                    "started_ms": None, "finished_ms": None, "files": [], "poster": ""})
        with self._lock:
            self._queue.append(job)
        self.emit("queued", job)
        return job

    def stats(self):
        with self._lock:
            return {"running": len(self._active), "queued": len(self._queue),
                    "limit": int(self.store.config.get("work_at_a_time", 2))}

    def shutdown(self):
        self._stop = True

    # ---------------------------------------------------------------- internal
    def _dispatch(self):
        while not self._stop:
            started = []
            with self._lock:
                limit = max(1, int(self.store.config.get("work_at_a_time", 2)))
                while self._queue and len(self._active) < limit:
                    job = self._queue.pop(0)
                    flag = []
                    self._cancel[job["id"]] = flag
                    self._active[job["id"]] = flag
                    started.append((job, flag))
            for job, flag in started:
                threading.Thread(target=self._run, args=(job, flag), daemon=True).start()
            time.sleep(0.2)

    def _run(self, job, flag):
        provider = get(self.store.config.get("provider", "demo"))
        last = [0.0]

        def on_progress(value, stage=None):
            job["progress"] = value
            if stage:
                job["stage"] = stage
            if value - last[0] >= 0.02 or value >= 1.0:
                last[0] = value
                self.store.save_jobs()
                self.emit("update", job)

        ctx = Ctx(job, self.store.config, on_progress)
        job["status"] = "running"
        job["started_ms"] = now_ms()
        job["stage"] = "Starting"
        self.store.job_folder(job)
        self.store.save_jobs()
        self.emit("started", job)
        job["final_prompt"] = skills_mod.compose(job.get("prompt", ""), job.get("skill"))
        try:
            files = provider.run(job, ctx)
            if flag:
                raise Cancelled()
            job["files"] = files or []
            job["status"] = "done"
            job["progress"] = 1.0
            job["stage"] = "Done"
        except Cancelled:
            job["status"] = "cancelled"
            job["stage"] = "Cancelled"
        except ProviderError as exc:
            job["status"] = "failed"
            job["stage"] = "Failed"
            job["error"] = str(exc)
        except Exception as exc:                     # noqa: BLE001 - surface anything
            job["status"] = "failed"
            job["stage"] = "Failed"
            job["error"] = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
        finally:
            job["finished_ms"] = now_ms()
            with self._lock:
                self._active.pop(job["id"], None)
                self._cancel.pop(job["id"], None)
            self.store.save_jobs()
            self.emit("finished", job)
