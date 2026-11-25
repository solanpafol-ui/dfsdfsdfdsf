import io, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for f in ("cookies.py",):
    print("="*20, f)
    for i,t in enumerate(io.open(f,encoding="utf-8",errors="replace").read().split("\n"),1):
        if t.strip(): print(i,"|",t.rstrip()[:150])
