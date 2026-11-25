import io, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
lines = io.open("browser.py",encoding="utf-8",errors="replace").read().split("\n")
print("=== 1~60 (imports) ===")
for i in range(0,60):
    s=lines[i].rstrip()
    if s.strip(): print(i+1,"|",s[:150])
print()
print("=== run_browser_job 시작부 찾기 ===")
for i,s in enumerate(lines,1):
    if "def run_browser_job" in s: print("at",i)
