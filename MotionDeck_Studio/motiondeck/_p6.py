import io, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
lines = io.open("panel.py",encoding="utf-8",errors="replace").read().split("\n")
print("=== 100~120 (Select 생성) ===")
for i in range(99,120):
    s=lines[i].rstrip()
    if s.strip(): print(i+1,"|",s[:160])
print()
print("=== 255~285 (job 생성) ===")
for i in range(254,285):
    s=lines[i].rstrip()
    if s.strip(): print(i+1,"|",s[:160])
