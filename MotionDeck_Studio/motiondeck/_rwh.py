import io, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for i,t in enumerate(io.open("winhide.py",encoding="utf-8",errors="replace").read().split("\n"),1):
    if t.strip(): print(i,"|",t.rstrip()[:160])
