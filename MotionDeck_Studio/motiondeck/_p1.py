import io, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
lines = io.open("browser.py",encoding="utf-8",errors="replace").read().split("\n")
print("=== progress 문구 전부 ===")
for i,s in enumerate(lines,1):
    t=s.rstrip()
    if "ctx.progress" in t or "Method" in t:
        print(i,"|",t.strip()[:150])
