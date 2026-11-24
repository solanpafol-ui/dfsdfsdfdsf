"""Entry point.

    python main.py                       open the workspace chooser
    python main.py --screenshot out.png  render the window and save a PNG
    python main.py --launcher --screenshot out.png
"""
import argparse
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def parse_args(argv):
    p = argparse.ArgumentParser(prog="motiondeck")
    p.add_argument("--screenshot", default="", help="save a PNG of the window and exit")
    p.add_argument("--launcher", action="store_true", help="screenshot the chooser instead")
    p.add_argument("--size", default="1280x820", help="window size, e.g. 1440x900")
    p.add_argument("--data-dir", default="", help="keep config and jobs somewhere else")
    p.add_argument("--settle", type=float, default=0.4,
                   help="seconds to let the window paint before capture")
    p.add_argument("--pack-skills", action="store_true",
                   help="validate every skill pack and rebuild its zip")
    p.add_argument("--check-skill", default="",
                   help="validate one SKILL.md on disk")
    p.add_argument("--import-skill", default="",
                   help="copy a skill folder or zip in without changing its bytes")
    p.add_argument("--repair-skill", default="",
                   help="add a missing opening --- to a SKILL.md (keeps a .orig copy)")
    p.add_argument("--skill", default="", help="preselect a skill pack by id")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    if args.data_dir:
        os.environ["MOTIONDECK_HOME"] = str(Path(args.data_dir).resolve())
        Path(args.data_dir).mkdir(parents=True, exist_ok=True)

    from motiondeck import skills as skills_mod
    if args.repair_skill:
        path = skills_mod.repair_format(args.repair_skill)
        print(f"repaired {path} (original kept as {path.name}.orig)")
        return 0
    if args.import_skill:
        skill_id, problems = skills_mod.import_pack(args.import_skill)
        print(f"imported {skill_id}")
        print("problems: none" if not problems
              else "problems:\n  - " + "\n  - ".join(problems))
        return 0
    if args.check_skill:
        problems = skills_mod.check_file(args.check_skill)
        print(args.check_skill)
        print("ok" if not problems else "problems:\n  - " + "\n  - ".join(problems))
        return 0 if not problems else 1
    if args.pack_skills:
        for skill_id, status, detail in skills_mod.pack_all():
            print(f"{status:<9} {skill_id:<20} {detail[0] if status == 'ok' else '; '.join(detail)}")
        return 0

    from motiondeck import store as S
    from motiondeck.engine import Engine
    from motiondeck.launcher import Launcher
    from motiondeck.workspace import Workspace

    store = S.Store()

    try:
        w, h = (int(x) for x in args.size.lower().split("x"))
    except Exception:
        w, h = 1280, 820

    if args.screenshot and args.launcher:
        launcher = Launcher(lambda page: None)
        path = launcher.capture(args.screenshot)
        print(path)
        launcher.destroy()
        return 0

    if args.screenshot:
        engine = Engine(store, lambda kind, job: None)
        win = Workspace(store, engine, size=(w, h), position=(20, 10))
        path = win.capture(args.screenshot, settle=args.settle)
        print(path)
        win._alive = False
        engine.shutdown()
        win.destroy()
        return 0

    state = {"win": None}

    def choose(page):
        launcher.destroy()
        engine = Engine(store, lambda kind, job: state["win"] and state["win"].on_event(kind, job))
        win = Workspace(store, engine, size=(w, h))
        state["win"] = win
        win.mainloop()

    launcher = Launcher(choose)
    launcher.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())