import io, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
lines = io.open("motiondeck/skills.py",encoding="utf-8",errors="replace").read().split("\n")
for i,s in enumerate(lines,1):
    t=s.rstrip()
    if t.strip() and ("def " in t or "root()" in t or "manifest" in t.lower()):
        print(i,"|",t.strip()[:140])
