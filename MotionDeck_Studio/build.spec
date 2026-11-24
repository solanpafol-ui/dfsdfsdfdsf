# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MotionDeck Studio (onedir, windowed).

Package data that must survive into the build:
  * motiondeck/bypass_ext  - the shield extension. Without it the browser
                             backend still runs, but loses the fingerprint
                             layer and the extension args become a no-op.
  * motiondeck/skills      - skill markdown, read by skills_mod.compose.

Datas land under _internal/motiondeck/<name> in the frozen tree, which is
exactly where browser.py's Path(__file__).with_name("bypass_ext") looks.
"""
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH)
PKG = ROOT / "motiondeck"

ENTRY_CANDIDATES = ("main.py", "run.py", "app.py", "MotionDeck.py")

entry = next((ROOT / n for n in ENTRY_CANDIDATES if (ROOT / n).is_file()), None)
if entry is None:
    raise SystemExit(
        "No entry script found. Expected one of: " + ", ".join(ENTRY_CANDIDATES))

if not PKG.is_dir():
    raise SystemExit(f"Package folder not found: {PKG}")

datas = []
missing = []
for extra in ("bypass_ext", "skills"):
    src = PKG / extra
    if src.is_dir():
        datas.append((str(src), os.path.join("motiondeck", extra)))
    else:
        missing.append(extra)

# Playwright ships a driver (node binary + package) next to the Python code.
datas += collect_data_files("playwright")

hiddenimports = collect_submodules("playwright")
hiddenimports += ["cv2", "numpy", "PIL", "PIL.Image", "PIL.ImageTk"]

a = Analysis(
    [str(entry)],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "unittest", "pydoc", "setuptools", "pip"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MotionDeck",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MotionDeck",
)

print("")
print("=" * 70)
print("spec: entry      =", entry.name)
print("spec: datas      =", len(datas), "entries")
if missing:
    print("spec: MISSING    =", ", ".join(missing))
    print("spec: the build will run but lose the layer those folders carry.")
print("=" * 70)
print("")