"""계정·설정·작업 저장.

%LOCALAPPDATA%\\MotionDeck 아래에 config.json 과 jobs.json 을 둔다.
쓰기는 항상 임시 파일에 하고 os.replace 로 갈아끼운다 — 중간에 죽어도 원본이 안 깨진다.
"""
import json
import os
import time
import uuid
from pathlib import Path

APP_NAME = "MotionDeck Studio"
VERSION = "0.5"

APP_DIR = "MotionDeck"

DEFAULTS = {
    "provider": "browser",
    "profiles": ["Profile 1"],
    "accounts": {},
    "data_dir": "",
    "hide_window": True,
    "mode": "t2v",
    "duration": 5,
    "aspect": "9:16",
    "resolution": "720p",
    "credits_start": 40,
    "credits": {},
    "cooldown_seconds": 20,
    "cooldown_until": {},
    "output_dir": "",
    "work_at_a_time": 2,
    "ark_base_url": "",
    "ark_model": "",
    "ark_api_key": "",
}


def home():
    override = os.environ.get("MOTIONDECK_HOME")
    if override:
        return override
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    return os.path.join(base, APP_DIR)


def config_path():
    return os.path.join(home(), "config.json")


def jobs_path():
    return os.path.join(home(), "jobs.json")


def now_ms():
    return int(time.time() * 1000)


def _write_atomic(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ------------------------------------------------------------------ accounts
def account_entry(config, name, create=False):
    """계정 하나의 고정 id 와 쿠키 자리. 이름이 바뀌어도 id 는 그대로다."""
    accs = config.setdefault("accounts", {})
    acc = accs.get(name)
    if acc is None:
        if not create:
            return {}
        acc = {"id": uuid.uuid4().hex[:10], "cookies": []}
        accs[name] = acc
    if not acc.get("id"):
        acc["id"] = uuid.uuid4().hex[:10]
    if not isinstance(acc.get("cookies"), list):
        acc["cookies"] = []
    return acc


def account_id(config, name):
    """폴더 이름에 쓰는 안정적인 키. 한글 이름도 겹치지 않는다."""
    acc = (config.get("accounts") or {}).get(name) or {}
    return acc.get("id") or ""


def new_job(prompt, opts=None):
    opts = opts or {}
    job = {
        "id": uuid.uuid4().hex[:12],
        "prompt": prompt,
        "final_prompt": "",
        "status": "queued",
        "stage": "Queued",
        "progress": 0.0,
        "error": "",
        "files": [],
        "poster": "",
        "folder": "",
        "created_ms": now_ms(),
        "started_ms": None,
        "finished_ms": None,
        "mode": opts.get("mode", "t2v"),
        "duration": int(opts.get("duration", 5)),
        "aspect": opts.get("aspect", "9:16"),
        "resolution": opts.get("resolution", "720p"),
        "reference": opts.get("reference", ""),
        "references": list(opts.get("references") or []),
        "skill": opts.get("skill", ""),
        "method": int(opts.get("method", 1) or 1),
        "model": opts.get("model", ""),
        "profile": opts.get("profile", ""),
        "account": opts.get("account", ""),
        "account_id": opts.get("account_id", ""),
        "panel": opts.get("panel", 0),
        "credit_spent": 0,
        "cookies": list(opts.get("cookies") or []),
    }
    return job


class Store:
    def __init__(self):
        self.dir = Path(home())
        self.dir.mkdir(parents=True, exist_ok=True)
        self.config = self._load_config()
        self.jobs = self._load_jobs()

    # ------------------------------------------------------------- config
    def _load_config(self):
        cfg = json.loads(json.dumps(DEFAULTS))
        try:
            with open(config_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        if isinstance(data, dict):
            for k, v in data.items():
                if k in DEFAULTS:
                    cfg[k] = v
        if not isinstance(cfg.get("profiles"), list) or not cfg["profiles"]:
            cfg["profiles"] = ["Profile 1"]
        for k in ("credits", "cooldown_until", "accounts"):
            if not isinstance(cfg.get(k), dict):
                cfg[k] = {}
        for name in cfg["profiles"]:
            account_entry(cfg, name, create=True)
        return cfg

    def save_config(self):
        _write_atomic(config_path(), self.config)

    # --------------------------------------------------------------- jobs
    def _load_jobs(self):
        try:
            with open(jobs_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = []
        return [j for j in data if isinstance(j, dict)] if isinstance(data, list) else []

    def save_jobs(self):
        _write_atomic(jobs_path(), self.jobs)

    def add(self, job):
        self.jobs.insert(0, job)
        self.save_jobs()
        return job

    def get(self, job_id):
        for job in self.jobs:
            if job.get("id") == job_id:
                return job
        return None

    # ------------------------------------------------------------ folders
    def output_root(self):
        raw = (self.config.get("output_dir") or "").strip()
        root = Path(raw) if raw else (self.dir / "output")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def job_folder(self, job):
        folder = Path(job.get("folder") or (self.output_root() / job["id"]))
        folder.mkdir(parents=True, exist_ok=True)
        job["folder"] = str(folder)
        return folder

    # ------------------------------------------------------------ credits
    def credits(self, name=None):
        start = int(self.config.get("credits_start", 40) or 0)
        if name is None:
            return sum(self._credit_of(n, start) for n in self.config["profiles"])
        return self._credit_of(name, start)

    def _credit_of(self, name, start):
        return int(self.config["credits"].get(name, start))

    def spend_credit(self, name, amount=1):
        left = self.credits(name)
        if left < amount:
            return False
        self.config["credits"][name] = left - amount
        self.save_config()
        return True

    def refund_credit(self, name, amount=1):
        self.config["credits"][name] = self.credits(name) + amount
        self.save_config()

    # ----------------------------------------------------------- cooldown
    def cooldown_left(self, name):
        until = float(self.config["cooldown_until"].get(name, 0) or 0)
        return max(0, int(round(until - time.time())))

    def start_cooldown(self, name):
        seconds = float(self.config.get("cooldown_seconds", 20) or 0)
        if name and seconds > 0:
            self.config["cooldown_until"][name] = time.time() + seconds
            self.save_config()

    # ----------------------------------------------------------- counters
    def rendered_count(self, name=None):
        return sum(1 for j in self.jobs
                   if j.get("status") == "done"
                   and (name is None or j.get("profile") == name))


# --------------------------------------------------- 구버전 이름 호환 shim
def load():
    return Store().config


def save(cfg):
    _write_atomic(config_path(), cfg)


def ready_in(cfg, name):
    until = float((cfg.get("cooldown_until") or {}).get(name, 0) or 0)
    return max(0.0, until - time.time())


def available(cfg):
    return [n for n in (cfg.get("profiles") or [])
            if ready_in(cfg, n) <= 0]