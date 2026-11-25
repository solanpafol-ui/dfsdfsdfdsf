import io, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
lines = io.open("panel.py",encoding="utf-8",errors="replace").read().split("\n")
print("=== panel.py skill 관련 ===")
for i,s in enumerate(lines,1):
    t=s.rstrip()
    if any(k in t for k in ("skill","Skill","current_skill")):
        print(i,"|",t.strip()[:150])
