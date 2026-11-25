"""Skill packs: a folder with SKILL.md plus manifest.json, shipped as a zip.

A skill here is a written recipe that travels with a brief to the renderer. It
is plain text on purpose: no code runs from a pack.

Layout on disk:

    skills/
      manifest.json                 index of the packs in this folder
      <id>/SKILL.md                 frontmatter (---) and the recipe body
      <id>/manifest.json            written when the pack is built
      <id>.zip                      <id>/SKILL.md + <id>/manifest.json

A pack that was written elsewhere may open straight at `name:` with no `---`
line. That variant is read as-is (the file is never rewritten); `--check-skill`
reports it, and `--repair-skill` is the only thing that edits a file, on purpose.
"""
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

SCHEMA = "motiondeck.skill/1"
BOM = "\ufeff"


def root() -> Path:
    return Path(__file__).resolve().parent.parent / "skills"


def _index():
    path = root() / "manifest.json"
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return {"schema": SCHEMA, "version": "0", "skills": []}


def catalog():
    """Every pack the index lists, with its summary."""
    out = []
    for entry in _index().get("skills", []):
        out.append({
            "id": entry.get("id", ""),
            "name": entry.get("label") or entry.get("name") or entry.get("id", ""),
            "summary": entry.get("summary", ""),
            "duration_s": entry.get("duration_s"),
            "ratios": entry.get("ratios", []),
        })
    return out


def _split_raw(norm, lenient):
    """Split normalised text into (header_text, body)."""
    if norm.startswith("---\n"):
        end = norm.find("\n---", 4)
        if end == -1:
            raise ValueError("frontmatter has no closing --- line")
        return norm[4:end], norm[end + 4:].lstrip("\n")
    if lenient and re.match(r"^(name|title)\s*:", norm):
        end = norm.find("\n---")
        if end == -1:
            raise ValueError("frontmatter has no closing --- line")
        return norm[:end], norm[end + 4:].lstrip("\n")
    raise ValueError("frontmatter must open with a line containing only ---")


def split_frontmatter(text, lenient=True):
    """Return (meta, body). Free of the BOM, never writes anything."""
    norm = text.lstrip(BOM).replace("\r\n", "\n")
    raw, body = _split_raw(norm, lenient)
    meta = {}
    current = None
    for line in raw.split("\n"):
        if not line.strip():
            continue
        if line.startswith(" ") and current:
            key, _, value = line.strip().partition(":")
            meta[current][key.strip()] = value.strip().strip('"').strip("'")
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if not value.strip():
            meta[key] = {}
            current = key
        else:
            meta[key] = value.strip().strip('"').strip("'")
            current = None
    return meta, body


def load(skill_id):
    entry = root() / skill_id / "SKILL.md"
    if not entry.is_file():
        return None
    text = entry.read_text("utf-8", errors="replace")
    meta, body = split_frontmatter(text)
    if not body.strip():
        raise ValueError(f"{skill_id}: the body after the frontmatter is empty")
    if not meta.get("name"):
        raise ValueError(f"{skill_id}: frontmatter has no name")
    if not meta.get("description"):
        raise ValueError(f"{skill_id}: frontmatter has no description")
    return {"id": skill_id, "meta": meta, "body": body, "path": entry}


def validate(skill_id, quiet=False):
    problems = []
    try:
        skill = load(skill_id)
    except ValueError as exc:
        return [str(exc)]
    if not skill:
        return [f"{skill_id}: SKILL.md is missing"]
    if skill["meta"].get("name") != skill_id:
        problems.append(f"name '{skill['meta'].get('name')}' does not match folder '{skill_id}'")
    if not quiet:
        listed = {s["id"] for s in _index().get("skills", [])}
        if skill_id not in listed:
            problems.append(f"{skill_id} is not listed in skills/manifest.json")
    return problems


def compose(prompt, skill_id, limit=0):
    """Append a pack's recipe to a brief. Unknown ids leave the brief untouched."""
    if not skill_id:
        return prompt
    try:
        skill = load(skill_id)
    except ValueError:
        return prompt
    if not skill:
        return prompt
    body = skill["body"].strip()          # used whole; limit=0 means no cut
    if limit and len(body) > limit:
        body = body[:limit].rsplit("\n", 1)[0] + "\n…"
    return (f"{prompt.strip()}\n\n---\nShot guidance — {skill['meta']['name']}:\n{body}")


def pack(skill_id):
    """Write <id>.zip holding <id>/SKILL.md and <id>/manifest.json."""
    skill = load(skill_id)
    if not skill:
        raise FileNotFoundError(f"{skill_id}/SKILL.md")
    folder = root() / skill_id
    per_skill = {
        "schema": SCHEMA,
        "id": skill_id,
        "name": skill["meta"].get("name", skill_id),
        "version": skill["meta"].get("version") or _index_version(skill_id),
        "description": skill["meta"].get("description", ""),
        "entry": "SKILL.md",
        "metadata": skill["meta"].get("metadata", {}),
    }
    manifest_path = folder / "manifest.json"
    manifest_path.write_text(json.dumps(per_skill, indent=2, ensure_ascii=False), "utf-8")

    archive = root() / f"{skill_id}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(folder / "SKILL.md", f"{skill_id}/SKILL.md")
        zf.write(manifest_path, f"{skill_id}/manifest.json")
    return archive


def pack_all():
    report = []
    for entry in _index().get("skills", []):
        skill_id = entry.get("id")
        if not skill_id:
            continue
        problems = validate(skill_id)
        if problems:
            report.append((skill_id, "problems", problems))
            continue
        archive = pack(skill_id)
        report.append((skill_id, "ok", [str(archive)]))
    return report


def _index_version(skill_id):
    for entry in _index().get("skills", []):
        if entry.get("id") == skill_id:
            return entry.get("version", "0")
    return "0"


def import_pack(source, skill_id=None):
    """Copy a folder or zip in beside the others, byte for byte.

    Returns (skill_id, problems). Nothing in the copied file is rewritten.
    """
    src = Path(source)
    temp = None
    if src.is_file() and src.suffix.lower() == ".zip":
        temp = Path(tempfile.mkdtemp(prefix="md_skill_"))
        with zipfile.ZipFile(src) as zf:
            zf.extractall(temp)
        found = list(temp.rglob("SKILL.md"))
        src = found[0].parent if found else temp
    if not src.is_dir():
        raise FileNotFoundError(source)
    if not (src / "SKILL.md").is_file():
        raise FileNotFoundError(f"{src} has no SKILL.md")

    skill_id = skill_id or src.name
    folder = root() / skill_id
    folder.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.is_file():
            shutil.copy2(item, folder / item.name)
    problems = validate(skill_id, quiet=True)
    try:
        pack(skill_id)
    finally:
        if temp:
            shutil.rmtree(temp, ignore_errors=True)
    return skill_id, problems


def repair_format(path):
    """Add a missing opening --- and drop a BOM. Nothing else changes.

    The original is kept as <name>.orig, and this only ever runs when asked for.
    """
    p = Path(path)
    raw = p.read_bytes()
    text = raw.decode("utf-8", errors="replace").lstrip(BOM)
    if not text.replace("\r\n", "\n").startswith("---\n"):
        text = "---\n" + text
    backup = p.with_suffix(p.suffix + ".orig")
    if not backup.exists():
        backup.write_bytes(raw)
    p.write_bytes(text.encode("utf-8"))
    return p


def check_file(path):
    """Validate any SKILL.md on disk; returns a list of human-readable problems."""
    p = Path(path)
    try:
        text = p.read_text("utf-8", errors="replace")
    except Exception as exc:
        return [f"cannot read it: {exc}"]
    problems = []
    if text.startswith(BOM):
        problems.append("starts with a UTF-8 BOM (read fine here; some readers choke on it)")
    if not text.lstrip(BOM).replace("\r\n", "\n").startswith("---\n"):
        problems.append("no opening --- line (read leniently here; stricter readers skip the skill)")
    try:
        meta, body = split_frontmatter(text)
    except ValueError as exc:
        return problems + [str(exc)]
    if not meta.get("name"):
        problems.append("frontmatter has no name")
    if not meta.get("description"):
        problems.append("frontmatter has no description")
    elif len(meta["description"]) > 400:
        problems.append(f"description is {len(meta['description'])} characters; keep it under ~400")
    if not body.strip():
        problems.append("nothing after the frontmatter")
    return problems
