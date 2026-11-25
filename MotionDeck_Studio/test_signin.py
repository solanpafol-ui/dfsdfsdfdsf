"""Sign-in 을 콘솔에서 직접 돌린다. 결과는 signin_test.log 에도 남는다."""
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, ".")

from motiondeck import browser, store  # noqa: E402

cfg = store.load()
name = (cfg.get("profiles") or ["Profile 1"])[0]
key = store.account_id(cfg, name) or name
log_path = Path(store.home()) / "signin_test.log"
log_path.write_text("", encoding="utf-8")


def say(line):
    print(line)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%H:%M:%S')} {line}\n")


say(f"account : {name}")
say(f"key     : {key}")
say(f"data_dir: {cfg.get('data_dir') or '(default)'}")
say(f"playwright: ", )
try:
    import playwright
    say(f"playwright import ok ({playwright.__file__})")
except Exception as exc:
    say(f"playwright import FAILED: {exc}")
say("-" * 50)

try:
    result = browser.open_signin(key, cfg.get("data_dir", ""), timeout=90, log=say)
    say(f"result  : {result}")
except Exception:
    traceback.print_exc()
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(traceback.format_exc())

print(f"\n로그 파일: {log_path}")
input("엔터를 누르면 닫힙니다...")