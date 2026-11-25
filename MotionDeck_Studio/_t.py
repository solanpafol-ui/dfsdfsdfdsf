import sys, io
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0,".")
from motiondeck import skills
print("root:", skills.root())
print("catalog:", skills.catalog())
for e in skills.catalog():
    sid = e["id"]
    print("validate", sid, "->", skills.validate(sid))
    print("load", sid, "->", bool(skills.load(sid)))
