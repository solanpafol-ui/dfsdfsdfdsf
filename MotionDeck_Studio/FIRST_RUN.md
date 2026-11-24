# First run

This build renders through a real Chrome window on dola.com, or through the
Ark API with your own key. This file covers the first one only, because it is
the path that needs setting up.

## 0. What you need

- Windows 10 or 11, 64-bit
- Python 3.10 or newer on PATH (`python --version` must answer)
- A dola.com account
- ~600 MB of disk for the Chromium that Playwright downloads

## 1. Install

From the project root (`MotionDeck_Studio\MotionDeck_Studio`):

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

`playwright install chromium` is a separate step and is not covered by
`pip install`. Without it the backend fails with "Executable doesn't exist".

If Windows Defender flags the downloaded Chromium, allow it — Playwright
stores browsers under `%LOCALAPPDATA%\ms-playwright`.

## 2. Pick the backend

Start the app, open **Settings**, set **Backend** to
`Seedance via dola.com (browser)`, and press **Save settings**.

Do not press **Test connection** expecting a network probe here — for this
backend it only checks that Playwright is importable and answers
"Playwright is installed". That is the whole test.

The API fields (Base URL, Model id, API key) stay visible but are ignored while
the browser backend is selected. Model choice happens on dola.com itself, so
the composer's model dropdown stays empty on this backend.

## 3. First sign-in

Queue one short job. Chrome opens on `https://dola.com/chat/skills`.

The app waits up to 5 minutes for a prompt box to appear. If you are signed
out, sign in inside that window. The job only proceeds once a prompt box is
visible.

The session lives in a persistent profile at:

```
%LOCALAPPDATA%\MotionDeck\browser_profile
```

Every later job reuses it, so sign-in is a one-time cost. Treat that folder as
credentials: it holds live cookies.

## 4. Captcha

If a Turnstile / hCaptcha / reCAPTCHA frame is present, the job parks at
`Captcha — solve it in the Chrome window` for up to 5 minutes. Solve it in the
window by hand; the job resumes on its own. If it times out, the job fails with
"The captcha was not solved in time" and a retry usually passes, because the
profile now carries the clearance cookie.

The backend is not headless, and cannot be — a human has to be able to reach
the window.

## 5. What the job does

1. Launches Chrome with the shield extension from `motiondeck\bypass_ext`.
2. Injects three scripts before any page script runs: 30 s body rewrite, FR/EU
   region stamp, region-overlay removal.
3. Opens the skills page and waits for the composer.
4. Types the brief, submits, then polls for a `<video>` element for up to
   20 minutes.
5. Grabs the video source directly and writes `%job_id%.mp4` plus
   `poster.png` into the job folder.

Cancelling from the queue stops the poll loop and closes the window.

## 6. Output

Clips land under the configured output folder, in per-job subfolders. The
**Library** page shows them; **Folder** opens the containing directory.

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Executable doesn't exist" | Chromium not downloaded | `playwright install chromium` |
| "No prompt box appeared" | Not signed in, or the page never loaded | Sign in in the window, then retry |
| Prompt box never detected though it is on screen | Site markup moved | Edit `SEL["composer"]` in `motiondeck\browser.py` |
| Send never fires | Same | Edit `SEL["send"]` |
| "SEEDANCE_UNAVAILABLE" | Site-side refusal | Retry; if it repeats, the account is out of quota |
| Chrome will not start, profile error | Another Chrome still holds the profile | Close every Chrome window using it, retry |
| Region overlay comes back | Cookies cleared | The stamp re-applies on the next launch; do not clear site data |
| Extension missing from `chrome://extensions` | Folder absent or path broken | Check `motiondeck\bypass_ext\manifest.json` exists |
| Video never appears, no failure text | Generation genuinely slow, or a new failure string | Raise the 20-minute cap in `browser.py`; add the string to `FAIL_TEXT` |

## 8. Reset

To force a fresh sign-in and a fresh fingerprint:

```
rmdir /s /q "%LOCALAPPDATA%\MotionDeck\browser_profile"
```

Nothing else is stored there, so job history and settings survive.

## 9. Packaging

`bypass_ext` and `skills` are package data. A PyInstaller build must carry both
— see `build.spec` and `build.bat`. Without them the app still starts, but
silently loses the shield extension and the skill prompts.

After a build, verify both of these exist:

```
dist\MotionDeck\_internal\motiondeck\bypass_ext\manifest.json
dist\MotionDeck\_internal\motiondeck\skills\
```

The bundled exe does **not** carry Chromium. On the target PC,
`playwright install chromium` is still required once.

## 10. Known limits

- One profile means one account. A second account needs a second profile
  directory, which this build does not manage for you.
- Selectors are shape-based, not scraped from a live DOM. A site redesign
  breaks detection until `SEL` is updated.
- The 20-minute poll cap and the two 5-minute waits are constants, not
  settings.
- The browser backend never runs headless, so a job needs a desktop session.