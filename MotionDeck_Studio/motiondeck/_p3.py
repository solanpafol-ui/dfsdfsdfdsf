import io, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
lines = io.open("browser.py",encoding="utf-8",errors="replace").read().split("\n")
print("=== 800~870 ===")
for i in range(799,870):
    s=lines[i].rstrip()
    if s.strip(): print(i+1,"|",s[:160])
