"""Local state: settings, job list, output folders.

Everything lives under %LOCALAPPDATA%\\MotionDeck (override with MOTIONDECK_HOME)
so the app never needs a server to run.
"""
import json
import os
import time
import uuid
from pathlib import Path

APP_NAME = "MotionDeck Studio"
VERSION = "0.2.0"

# Each local profile starts with this many renders. A render that fails or is
# cancelled is refunded, so the number only goes down for clips that exist.
CREDITS_START = 40


def data_dir() -> Path:
    root = os.environ.get("MOTIONDECK_HOME")
    base = Path(root) if root else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MotionDeck"
    base.mkdir(parents=True, exist_ok=True)
    return base


DEFAULT_CONFIG = {
    "provider": "demo",
    "ark_api_key": "",
    "ark_base_url": "https://ark.ap-southeast.bytepluses.com/api/v3",
    "ark_model": "seedance-1-0-pro-250528",
    "output_dir": str(Path.home() / "Videos" / "MotionDeck"),
    "work_at_a_time": 2,
    "duration": 5,
    "resolution": "720p",
    "aspect": "16:9",
    "activation": "",
    "theme": "dark",
    "credits": {},
    "credits_start": CREDITS_START,
    "cooldown_seconds": 20,
}

def now_ms() -> int:
    return int(time.time() * 1000)


def new_job(prompt, opts):
    jid = "job_" + uuid.uuid4().hex[:10]
    return {
        "id": jid,
        "prompt": prompt,
        "provider": opts.get("provider", "demo"),
        "model": opts.get("model", ""),
        "mode": opts.get("mode", "Text to video"),
        "reference": opts.get("reference", ""),
        "references": list(opts.get("references", [])),
        "skill": opts.get("skill") or "",
        "duration": int(opts.get("duration", 5)),
        "resolution": opts.get("resolution", "720p"),
        "aspect": opts.get("aspect", "16:9"),
        "variant": int(opts.get("variant", 1)),
        "status": "queued",
        "progress": 0.0,
        "stage": "Queued",
        "created_ms": now_ms(),
        "started_ms": None,
        "finished_ms": None,
        "files": [],
        "poster": "",
        "error": "",
        "folder": "",
    }


class Store:
    def __init__(self):
        self.dir = data_dir()
        self.config_path = self.dir / "config.json"
        self.jobs_path = self.dir / "jobs.json"
        self.config = dict(DEFAULT_CONFIG)
        self.jobs = []
        self._load()

    def _load(self):
        try:
            self.config.update(json.loads(self.config_path.read_text("utf-8")))
        except Exception:
            pass
        try:
            self.jobs = json.loads(self.jobs_path.read_text("utf-8"))
        except Exception:
            self.jobs = []

    def save_config(self):
        try:
            self.config_path.write_text(json.dumps(self.config, indent=2, ensure_ascii=False),
                                        "utf-8")
        except Exception:
            pass

    def save_jobs(self):
        try:
            tmp = self.jobs_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.jobs[-300:], indent=1, ensure_ascii=False), "utf-8")
            tmp.replace(self.jobs_path)
        except Exception:
            pass

    def add(self, job):
        self.jobs.insert(0, job)
        self.save_jobs()
        return job

    def get(self, job_id):
        for j in self.jobs:
            if j["id"] == job_id:
                return j
        return None

    # ------------------------------------------------------------------ credits
    def credits(self, profile):
        """Renders left on this local profile."""
        book = self.config.setdefault("credits", {})
        if profile not in book:
            book[profile] = int(self.config.get("credits_start", CREDITS_START))
            self.save_config()
        return int(book[profile])

    def spend_credit(self, profile, amount=1):
        book = self.config.setdefault("credits", {})
        left = self.credits(profile)
        if left < amount:
            return False
        book[profile] = left - amount
        self.save_config()
        return True

    def refund_credit(self, profile, amount=1):
        book = self.config.setdefault("credits", {})
        book[profile] = self.credits(profile) + amount
        self.save_config()

    def rendered_count(self, profile=None, panel=None):
        """How many clips this profile (or one panel of it) has finished."""
        total = 0
        for job in self.jobs:
            if job.get("status") != "done":
                continue
            if profile is not None and job.get("profile") != profile:
                continue
            if panel is not None and job.get("panel") != panel:
                continue
            total += 1
        return total

    def cooldown_left(self, profile):
        """Seconds before this profile may render again (0 when free)."""
        window = int(self.config.get("cooldown_seconds", 45)) * 1000
        if window <= 0:
            return 0
        newest = 0
        for job in self.jobs:
            if job.get("profile") != profile:
                continue
            stamp = job.get("finished_ms") or job.get("started_ms") or 0
            if stamp > newest:
                newest = stamp
        if not newest:
            return 0
        left = (newest + window - now_ms()) / 1000
        return max(0, int(left + 0.999))

    def output_root(self) -> Path:
        p = Path(self.config["output_dir"])
        p.mkdir(parents=True, exist_ok=True)
        return p

    def job_folder(self, job) -> Path:
        if job.get("folder"):
            return Path(job["folder"])
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(job["created_ms"] / 1000))
        folder = self.output_root() / f"{stamp}_{job['id'][-6:]}"
        folder.mkdir(parents=True, exist_ok=True)
        job["folder"] = str(folder)
        return folder
