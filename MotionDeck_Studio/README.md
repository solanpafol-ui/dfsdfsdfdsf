# MotionDeck Studio

A desktop front end for AI video work. Own code, own UI.

Double-click `run.bat` to open it. It picks the system Python 3.12 because the
bundled interpreter has no Tkinter.

```
python main.py                       open the workspace chooser
python main.py --launcher --screenshot out.png
python main.py --page library --screenshot out.png
python main.py --service cloud       open the API workspace tab
```

Requires Python 3.10+ with Tkinter (bundled with the Windows installer), Pillow,
OpenCV and requests. No build step.

## What it does

- **Launcher** - three workspaces, two marked Soon.
- **M1 / M2** - M1 renders on this machine, M2 renders through your own video API key.
- **Accounts** - local profiles (name, defaults). Each one gets its own panel,
  its own credit balance and its own cooldown. A failed or cancelled render
  gives its credit back.
- **Panels** - one card per account, side by side: mode (Standard, Reference,
  Batch), brief, ratio, length (5 to 60 s), up to ten reference stills, skill,
  generate, progress with an estimate, the result with play, save and folder,
  and a per-panel total rendered.
- **Batch wizard** - load a `.txt` of prompts, a folder of stills, ratio and
  length, queue them all.
- **Live view / Log** - F9 or the header buttons. The live view follows the
  current job; the log keeps every job event.
- **Queue** - status, cancel, retry, play, folder.
- **Library** - finished clips as a grid with posters.
- **Settings** - backend, key, endpoint, model, output folder, slots.

State lives in `%LOCALAPPDATA%\MotionDeck` (`config.json`, `jobs.json`); renders
go to `%USERPROFILE%\Videos\MotionDeck` unless you change it. Override the state
folder with `MOTIONDECK_HOME`.

## Backends

The `ark` backend calls ByteDance's Seedance video model through the official Ark /
BytePlus content-generation API using your own key. The base URL and model id
are settings because they differ per region and account; the defaults are
`https://ark.ap-southeast.bytepluses.com/api/v3` and `seedance-1-0-pro-250528`.
Check them against your provider console before the first render.

There is deliberately no browser-driving backend. This app talks to an API you
have an account and a key for; it does not sign into another service for you,
rotate accounts, or try to get around a provider's limits or safeguards.

## Skill packs

A skill is a written recipe that travels with a brief to the renderer. On disk it
is a folder plus a zip so it can be moved between machines:

```
skills/
  manifest.json            index: id, label, version, summary, duration, ratios
  <id>/SKILL.md            the recipe, exactly as its author wrote it
  <id>/manifest.json       metadata, written when the pack is built
  <id>.zip                 <id>/SKILL.md + <id>/manifest.json
```

```
python main.py --pack-skills                       validate every pack, rebuild its zip
python main.py --check-skill path/to/SKILL.md      report problems, change nothing
python main.py --import-skill path/to/folder|zip   copy a pack in byte for byte
python main.py --repair-skill path/to/SKILL.md     add a missing opening --- (keeps .orig)
```

Packs are never rewritten on import: `SKILL.md` goes in exactly as it arrived and
only the metadata `manifest.json` is added beside it. A pack written elsewhere
often opens straight at `name:` with no `---` line, or starts with a byte-order
mark; those are read leniently here, and `--check-skill` still tells you so that
stricter readers will skip it. Pick a skill in the panel and it is appended to
that job's brief only; the queue and library keep showing your original brief.

The panel always reports the length the renderer actually produced, whatever a
pack says the clip should be.
