import io, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
s = io.open("browser.py", encoding="utf-8", errors="replace").read()
lines = s.split("\n")
print("lines:", len(lines))
for i, t in enumerate(lines, 1):
    if t.strip():
        print(i, "|", t.rstrip()[:150])
