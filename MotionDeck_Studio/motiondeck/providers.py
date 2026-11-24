"""Render backends.

The app ships with one real backend: the official Ark / BytePlus Seedance API,
using the operator's own key. The browser-driving path from the original app
is intentionally not reproduced here.

- ``ark``   calls ByteDance's Seedance video model through the official
            Volcano/BytePlus Ark content-generation API, using the operator's
            own API key. Endpoint and model id are configuration, because both
            differ by region and by account.
"""
import base64
import json
import mimetypes
import os
import shutil
import tempfile
import time
from pathlib import Path

from . import store as S


class ProviderError(RuntimeError):
    pass


class Cancelled(RuntimeError):
    pass


class Ctx:
    """What a backend gets: progress, cancellation and settings."""

    def __init__(self, job, config, on_progress):
        self.job = job
        self.config = config
        self._on_progress = on_progress
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def check(self):
        if self._cancelled:
            raise Cancelled()

    def progress(self, value, stage=None):
        self._on_progress(max(0.0, min(1.0, value)), stage)

    def sleep(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.check()
            time.sleep(min(0.1, end - time.time()))


def _ascii_temp(suffix):
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="md_",
                                dir=str(Path(tempfile.gettempdir())))
    os.close(fd)
    return path



# ---------------------------------------------------------------------------- ark
class ArkSeedanceProvider:
    """Official Ark / BytePlus Seedance content-generation API."""

    id = "ark"
    label = "Seedance via Ark API (your key)"
    needs_key = True
    note = ("Uses your own Ark API key. Set the base URL and model id from your "
            "provider console; they differ by region and account.")

    def _headers(self, key):
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def _payload(self, job):
        cfg = {"--ratio": job["aspect"], "--duration": str(job["duration"]),
               "--resolution": job["resolution"], "--fps": "24", "--camerafixed": "false"}
        text = (job.get("final_prompt") or job["prompt"]).strip()
        if "--" not in text:
            text = text + " " + " ".join(f"{k} {v}" for k, v in cfg.items())
        content = [{"type": "text", "text": text}]
        ref = job.get("reference") or ""
        if ref:
            content.append({"type": "image_url", "image_url": {"url": self._image_url(ref)}})
        return {"model": job.get("model") or "", "content": content}

    @staticmethod
    def _image_url(ref):
        p = Path(ref)
        if p.exists():
            mime = mimetypes.guess_type(str(p))[0] or "image/jpeg"
            b64 = base64.b64encode(p.read_bytes()).decode("ascii")
            return f"data:{mime};base64,{b64}"
        return ref

    def run(self, job, ctx):
        import requests

        key = (ctx.config.get("ark_api_key") or "").strip()
        if not key:
            raise ProviderError("No Ark API key yet. Add one in Settings, Add one in Settings before generating.")
        base = (ctx.config.get("ark_base_url") or "").rstrip("/")
        if not base:
            raise ProviderError("No Ark base URL set in Settings.")
        if not job.get("model"):
            raise ProviderError("No model id set. Choose one in Settings.")

        url = f"{base}/contents/generations/tasks"
        ctx.progress(0.02, "Sending the brief")
        try:
            r = requests.post(url, headers=self._headers(key),
                              data=json.dumps(self._payload(job), ensure_ascii=False).encode("utf-8"),
                              timeout=90)
        except requests.RequestException as exc:
            raise ProviderError(f"Could not reach {url}: {exc}")
        if r.status_code >= 400:
            raise ProviderError(f"{r.status_code} from the API: {_short(r.text)}")
        task = (r.json() or {}).get("id") or (r.json() or {}).get("task_id")
        if not task:
            raise ProviderError(f"The API answered without a task id: {_short(r.text)}")

        ctx.progress(0.06, "Queued on the provider")
        deadline = time.time() + 60 * 30
        video_url = None
        while time.time() < deadline:
            ctx.sleep(3)
            try:
                g = requests.get(f"{url}/{task}", headers=self._headers(key), timeout=60)
                body = g.json() if g.content else {}
            except Exception:
                continue
            status = str(body.get("status", "")).lower()
            if status in ("queued", "pending", "running", "processing", "in_progress"):
                ctx.progress(0.1 + 0.75 * _task_fraction(body), f"Provider: {status}")
                continue
            if status in ("succeeded", "success", "completed", "done"):
                video_url = (((body.get("content") or {}).get("video_url"))
                             or body.get("video_url"))
                break
            if status in ("failed", "error", "cancelled", "canceled"):
                raise ProviderError(f"The provider refused the job: {_short(json.dumps(body))}")
            ctx.progress(0.3, f"Provider: {status or 'working'}")
        if not video_url:
            raise ProviderError("The provider did not return a video in 30 minutes.")

        ctx.progress(0.9, "Downloading the render")
        folder = Path(job["folder"])
        final = folder / f"{job['id']}.mp4"
        with requests.get(video_url, stream=True, timeout=300) as resp:
            resp.raise_for_status()
            with open(final, "wb") as fh:
                for chunk in resp.iter_content(1 << 20):
                    ctx.check()
                    fh.write(chunk)
        poster = _poster_from_video(final, folder / "poster.png")
        if poster:
            job["poster"] = str(poster)
        ctx.progress(1.0, "Done")
        return [str(final)]

    def healthcheck(self, config):
        import requests
        key = (config.get("ark_api_key") or "").strip()
        base = (config.get("ark_base_url") or "").rstrip("/")
        if not key or not base:
            return False, "Add the base URL and API key first."
        try:
            r = requests.get(f"{base}/contents/generations/tasks?page_size=1",
                             headers=self._headers(key), timeout=20)
        except Exception as exc:
            return False, f"Network error: {exc}"
        if r.status_code < 400:
            return True, "The API accepted your key."
        return False, f"{r.status_code}: {_short(r.text)}"


def _task_fraction(body):
    for key in ("progress", "percent", "percentage"):
        val = body.get(key)
        if isinstance(val, (int, float)):
            return float(val) / 100.0 if val > 1 else float(val)
    return 0.1


def _short(text, limit=240):
    text = " ".join(str(text).split())
    return text[:limit] + ("…" if len(text) > limit else "")


def _poster_from_video(video_path, poster_path):
    try:
        import cv2
        import numpy as np
        data = np.fromfile(str(video_path), dtype=np.uint8)
        cap = cv2.VideoCapture()
        # imdecode route needs a file path, so read the frame via a capture object
        cap.release()
        cap = cv2.VideoCapture(str(video_path))
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            return None
        frame = cv2.resize(frame, (480, int(480 * frame.shape[0] / frame.shape[1])))
        ok, buf = cv2.imencode(".png", frame)
        if not ok:
            return None
        buf.tofile(str(poster_path))
        # data was only needed to prove the file is reachable on non-ASCII paths
        return poster_path
    except Exception:
        return None


PROVIDERS = {p.id: p for p in (ArkSeedanceProvider(),)}


def get(provider_id):
    return PROVIDERS.get(provider_id) or PROVIDERS["ark"]


def options_for(config, provider_id=None):
    """Model choices offered in the composer, per backend."""
    pid = provider_id or config.get("provider", "demo")
    if pid == "ark":
        configured = (config.get("ark_model") or "").strip()
        base = ["seedance-1-0-pro-250528", "seedance-1-0-lite-t2v-250428",
                "seedance-1-0-lite-i2v-250428"]
        return [configured] + [m for m in base if m != configured] if configured else base
    configured = (config.get("ark_model") or "").strip()
    return [configured] if configured else []
