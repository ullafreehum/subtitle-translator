# Subtitle Translator

*Türkçe: [README.md](README.md)*

A Windows program that listens to a video, writes subtitles for it, translates them
into one or more languages, lets you check and correct them, and can burn them into
a new copy of the video. Built for the training videos of **DİLGEM**.

You give it a video. You get back:

- `lecture.en.srt`: subtitles in the spoken language
- `lecture.tr.srt`, `lecture.de.srt`, ...: translated subtitles (one file per language)
- `lecture.tr.subtitled.mp4`, ...: the video with the subtitles drawn on the picture (optional)

---

## Features

- **Speech recognition on the graphics card (GPU).** Uses OpenAI's *Whisper large-v3-turbo*
  model. It is fast and accurate on an NVIDIA graphics card. Without one it runs on the
  processor (CPU), which is slower.
- **Subtitles that are easy to read.** Lines are split at natural places, never more than
  two lines, and each subtitle stays on screen long enough to be read comfortably.
- **Many languages at once.** Pick several target languages (Turkish, English, German,
  Arabic, ... 35 languages) and they are all done in one go.
  - **Offline – NLLB-200** (default): best quality, works without internet, your text never
    leaves the computer, no daily limits.
  - **Online – Google Translate**: no extra download, but needs internet, sends the text
    to Google and may be limited if you translate a lot.
- **Glossary for names and terms.** Tell the program which names to keep exactly as written
  (DİLGEM, JASPER, ...) and how special terms must be translated (*trainee → kursiyer*).
- **Review and edit before burning.** Check every subtitle with a picture from the video,
  play the subtitle's piece of the video, fix the text or timing, and use *Find & Replace*.
- **Burned-in video with style options.** Position (bottom/top), text size, an optional
  dark background box, and the font.
- **Batch queue.** Drag & drop many videos onto the window; they are processed one after another.
- **SRT and VTT** subtitle files (SRT works in almost every player, YouTube, Instagram, Premiere,
  etc.; VTT is for web players).

---

## Installation (once per computer)

You need Windows 10 or 11 (64-bit), an internet connection for the first setup and about
**6 GB of free disk space** (2.3 GB for the program's components, 3 GB for the AI models).

1. Get the program folder:
   - **From GitHub as a ZIP**: on the repository page click **Code → Download ZIP**.
     Then **right-click the ZIP → Extract All…** and extract it somewhere permanent, for
     example `Documents\SubtitleTranslator`. Do not start `setup.bat` from inside the ZIP
     window: it only works in the extracted folder.
   - **Or with git**: `git clone https://github.com/ullafreehum/subtitle-translator.git`
   - **Or** copy an existing **SubtitleTranslator** folder (without its `.venv` folder).

   Do not move the folder after setup, or the shortcut stops working. If you do move it,
   just run `setup.bat` again. Folder names with spaces or Turkish letters are fine.
2. Double-click **`setup.bat`**.
   A black window opens and shows each step:
   1. installs **Python 3.12** if it is missing (other Python versions on the PC are left alone),
   2. installs **FFmpeg** (the video tool) if it is missing,
   3. downloads the program's components (about 1.5 GB download, 2.3 GB on disk, mostly NVIDIA
      GPU libraries). This takes 5 to 20 minutes on a fast connection, longer on a slow one.
      The window may show no new lines for several minutes while the packages are unpacked:
      that is normal, please wait,
   4. checks that everything works and whether an NVIDIA GPU was found,
   5. creates a **Subtitle Translator** shortcut on the Desktop and in the Start menu.
3. When it says **Setup finished successfully!**, press a key to close the window.

Good to know:

- If Windows shows *"Open File – Security Warning"* or *"Windows protected your PC"* for
  `setup.bat` (files downloaded from the internet are marked), click **Run** (or
  **More info → Run anyway**). Setup removes this mark from the program's files.
- If Windows asks *"Do you want to allow this app to make changes?"* during the Python or
  FFmpeg install, click **Yes**.
- If setup says *"Please close this window and double-click setup.bat once more"*, do exactly
  that. Windows sometimes needs a fresh window to see a newly installed program.
- Running `setup.bat` again is always safe: it only adds what is missing. Use it to repair
  an installation, too.
- Options (for advanced users, run from a Command Prompt in the folder):
  `setup.bat -SkipShortcuts` (no shortcuts), `setup.bat -DryRun` (only show what would be done).

### First run: model downloads

The first time you process a video, the program downloads the AI models once:

| Model | Size | When | Saved in |
|---|---|---|---|
| Whisper large-v3-turbo (speech recognition) | about 1.6 GB | first video | `%USERPROFILE%\.cache\huggingface` (shared by all copies of the program for this Windows user) |
| NLLB-200 1.3B (offline translation) | about 1.3 GB | first offline translation | `models` folder in the program folder |

After that everything works offline (except the *Online – Google* translator).
The log shows *"still downloading …"* messages while a model downloads.

---

## How to use it

1. Start **Subtitle Translator** from the Desktop shortcut.
2. **Add videos**: drag & drop video files or whole folders onto the window, or use
   **Add videos…** / **Add folder…**. You can add many; they wait in the queue.
3. **Source language**: leave it on *Auto-detect*, or choose it if the program guesses wrong
   (useful for short videos or videos with mixed languages).
4. **Target languages**: click each language you want (click again to unselect).
5. **Translator**: keep *Offline – NLLB* unless you have a reason to use Google.
6. Optional: tick **Burn subtitles into a new video** and choose position, size, font and
   background box. Tick **Review subtitles before burning** to check the text first.
7. Press **Start**. Each video's status, the progress bar and the log show what is happening.
   The subtitle files are saved next to the video (or in the output folder you chose).
8. **Review** (recommended before publishing): double-click a finished video, or select it
   and press **Review / edit…**. (**Open subtitles…** opens any existing video + SRT pair.)
   - Click a subtitle to see the video frame at that moment. Orange rows are hard to read
     (too long or too fast).
   - **▶ Play cue** (F5) plays just that subtitle's part of the video with sound.
   - Change the text or the start/end times; **Split**, **Merge with next**, **Delete**, **Undo**.
   - **Find & replace…** (Ctrl+F) fixes a word everywhere at once (for example a misheard name).
   - **Save** (Ctrl+S), then **Save & burn video** to create the subtitled video with your corrections.

**Your edits are never lost silently.** The editor keeps the very first version of a subtitle
file as `<name>.srt.bak`. If you process the same video again, the program keeps your current
(edited) subtitles as `<name>.srt.bak-<date>-<time>` before writing new ones. To go back, rename
a backup to `<name>.srt`.

---

## The glossary (names and terms)

The glossary is a simple text file, `glossary.txt`, in the program folder. Open it with the
program's **Edit glossary…** button (or with Notepad). The first time, it is created from
`glossary.example.txt`. Save it as **UTF-8** (Notepad's default), so Turkish letters stay correct.

The program comes with a ready glossary of about 5,000 terms for DİLGEM's fields: play therapy
(ÇMOT, filial terapi), autism interventions (JASPER, DIR Floortime, ABA), speech and language
therapy (stuttering, voice, swallowing and IDDSI, hearing, AAC), occupational therapy (sensory
integration, praxis, handwriting), physiotherapy (cerebral palsy, gait, orthoses, kinesio
taping, vestibular rehabilitation), psychology (development, assessment and WISC, ACT, schema
therapy, family therapy), special education (BEP, RAM, single-subject research), diagnoses
(DSM-5) and assessment tools (AGTE, WISC, Denver II, GMFCS, BOT-2). The Turkish terms follow DİLGEM's own materials
first (for example *katılımcı* for "trainee") and the Turkish professional literature second.
How the terms were chosen, and the sources, are in [docs/GLOSSARY.md](docs/GLOSSARY.md).

The file has four kinds of entries:

```text
# 1) At the top: names and terms that must stay exactly as written (never translated).
DİLGEM
JASPER
Landreth

# 2) Words that help the speech recognition (nothing is replaced).
[hints]
çocuk merkezli oyun terapisi
filial terapi

# 3) Corrections of words the speech recognition mishears, in the original subtitles.
[tr>tr]
filaterapi = filial terapi
çocuk merkezi oyun terapisi = çocuk merkezli oyun terapisi

# 4) Forced translations for one language direction (en = English, tr = Turkish).
[en>tr]
trainees = katılımcılar
joint attention = ortak dikkat

[tr>en]
filial terapi = filial therapy
ortak dikkat = joint attention
```

Tips:
- Put the plural form on its own line when it is different (*trainees / trainee*). Turkish
  endings are handled automatically (*filial terapide*, *pekiştireci*).
- Upper/lower case does not matter when searching, except for short abbreviations of up to
  4 capital letters (*ABA*, *CARS*, *DİB*): those only match in capitals.
- Only force technical terms. Everyday words with several meanings (*play*, *prompt*, *session*,
  *dikkat*) would change normal sentences too.
- If the speech recognition keeps writing a word wrongly, add it to the `[tr>tr]` (or `[en>en]`)
  corrections.
- Your own `glossary.txt` can also list your trainers' names; it is never uploaded to GitHub.
  Changes apply to the next video you start.

---

## Tips

- **Model choice**: keep the model on the default (*large-v3-turbo*). It is the
  most accurate and is fast on an NVIDIA GPU. The smaller models (*small*, *medium*) are
  only worth it on a computer without an NVIDIA GPU when speed matters more than accuracy.
- **Vertical videos (Instagram Reels, TikTok, Shorts)**: keep text size on **Auto**; it adapts
  to the narrow picture. Turn on the **background box** if the video is bright or busy.
  Choose **Top** position if the bottom of the picture has important content or will be
  covered by the app's buttons.
- **Long recordings (lectures, webinars)**: they work fine, they just take longer. As a rough
  guide, an hour of video takes a few minutes on a modern NVIDIA GPU, and much longer on CPU.
  Add them to the queue and let the computer work; you can keep using it meanwhile.
  Burning a long video into MP4 takes extra time on top of that.
- **Clear sound gives the best subtitles**: a clip-on microphone beats the camera's microphone.
- **Check names before publishing**: speech recognition is very good but not perfect,
  especially with names. Add frequent names to the glossary so they come out right every time.

---

## Troubleshooting

| Problem | What to do |
|---|---|
| *"Subtitle Translator is not installed on this PC yet"* | Run `setup.bat` first. |
| Setup says *"The Subtitle Translator files are not complete in this folder"* | `setup.bat` was started from inside the ZIP, or files are missing. Right-click the ZIP → **Extract All…**, then double-click `setup.bat` in the extracted folder. |
| Setup stops with *"Installing packages failed"* | Usually the internet connection dropped or is very slow. Run `setup.bat` again: it continues where it stopped (already downloaded parts are reused). Check that there are at least 6 GB free on the disk. In a company network with a proxy, ask IT, or set `HTTPS_PROXY` before running setup. |
| Setup says *"Please close this window and double-click setup.bat once more"* | Python was just installed and this window cannot see it yet. Close it and start `setup.bat` again. If it repeats, restart Windows. |
| Setup says winget is not available | Install **App Installer** from the Microsoft Store, or install Python 3.12 from python.org (tick *Add python.exe to PATH*) and FFmpeg from gyan.dev, then run `setup.bat` again. |
| Very slow / the log says it uses the **CPU** | The program uses the GPU only with an NVIDIA graphics card. Update the NVIDIA driver (from nvidia.com or GeForce Experience / NVIDIA App), restart, and run `setup.bat` again. If no NVIDIA GPU is available, it automatically falls back to the CPU: it still works, just slower. |
| Online translation stops or gives errors | Google limits how much one computer can translate in a short time. Switch the translator to **Offline – NLLB** (no limits), or wait a while. |
| First video "hangs" at the beginning | It is downloading the models (about 3 GB in total). Check your internet connection and wait. |
| A model download was interrupted | Just start again: the download continues. If it keeps failing, close the program and delete the `models` folder in the program folder (translation model) and the folder `%USERPROFILE%\.cache\huggingface\hub` (speech recognition models), then start again. |
| The Desktop shortcut does nothing | The program folder was moved or renamed. Run `setup.bat` again in the new place. |
| "ffmpeg not found" | Run `setup.bat` again. If it still fails, restart Windows (so it sees the new program) and try once more. |
| Turkish letters look wrong in the glossary | Save `glossary.txt` as **UTF-8** in Notepad (*Save As → Encoding: UTF-8*). |
| Something else | Start `run_console.bat` instead of the shortcut. It shows a black window with detailed messages; copy them when asking for help. (Standalone version: see `SubtitleTranslator.log` next to the exe, or use `SubtitleTranslatorCLI.exe`.) |

---

## Command line (advanced)

The engine also works without the window, from a Command Prompt in the program folder:

```bat
.venv\Scripts\python.exe engine.py "C:\Videos\lecture.mp4" --to tr en
.venv\Scripts\python.exe engine.py "C:\Videos\lecture.mp4" --to tr --burn
.venv\Scripts\python.exe engine.py "C:\Videos\lecture.mp4" --to tr en de --translator online
```

Main options: `--to` (one or more target languages), `--from` (spoken language, default
auto-detect), `--translator nllb|online` (default `nllb`), `--burn` (also make subtitled MP4s),
`--out FOLDER`. Run `.venv\Scripts\python.exe engine.py --help` for all options.

---

## Standalone version (optional)

`build_exe.bat` (after `setup.bat`) makes a version that does not need Python on the target
computer: the folder `dist\SubtitleTranslator` (about 2.2 GB, about 1150 files; copy or zip the
whole folder, not only the exe). It contains:

- `SubtitleTranslator.exe`: the program window,
- `SubtitleTranslatorCLI.exe`: the same command line as `engine.py` (see above), for example
  `SubtitleTranslatorCLI.exe "C:\Videos\lecture.mp4" --to tr`.

The AI models are not included. On first use the translation model downloads into a `models`
folder next to the exe and the speech recognition model into `%USERPROFILE%\.cache\huggingface`;
to give a PC the translation model in advance, copy a `models` folder next to the exe.
`settings.json`, `glossary.txt` and `SubtitleTranslator.log` (messages for troubleshooting)
are also kept next to the exe, so put the folder where the user may write (not in
`C:\Program Files`). Rebuilding keeps `models`, `glossary.txt` and `settings.json`.
The target computer still needs FFmpeg (`winget install Gyan.FFmpeg`), or copy `ffmpeg.exe`,
`ffprobe.exe` and `ffplay.exe` next to `SubtitleTranslator.exe`. The exe is not signed, so
Windows SmartScreen may warn the first time: **More info → Run anyway**.

---

## Project structure

```
SubtitleTranslator/
  app.py              main window (queue, settings, progress)
  editor.py           subtitle review/edit window
  engine.py           processing: audio, speech recognition, translation, burning, CLI
  subtitles.py        subtitle timing, line breaking, SRT/VTT files
  translation.py      NLLB offline and Google online translators, glossary use
  glossary.py         reads glossary.txt
  cuda_setup.py       finds the NVIDIA GPU libraries
  glossary.example.txt
  run.bat / run_console.bat     start the program (without / with a log window)
  setup.bat / setup.ps1         installer
  build_exe.bat / SubtitleTranslator.spec   standalone build (PyInstaller):
                      SubtitleTranslator.exe (window) + SubtitleTranslatorCLI.exe (command line)
  assets/             icon (make_icon.py regenerates it)
  docs/ARCHITECTURE.md          how the modules fit together
  tests/              automated tests (run each with .venv\Scripts\python.exe tests\<name>.py)
  .gitattributes      keeps Windows line endings in .bat/.ps1 files
```

Developer details are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Licenses

- **Subtitle Translator (this program's code)**: Copyright © DİLGEM. All rights reserved.
  *(placeholder: replace with the chosen license)*
- **Whisper** speech recognition model (OpenAI): MIT License.
  Runs through **faster-whisper** and **CTranslate2** (both MIT License).
- **NLLB-200** translation model (Meta AI): **CC-BY-NC 4.0, non-commercial use only.**
  This project is non-commercial. If the program is ever used commercially, the offline
  NLLB translator must not be used (use another translator or a commercially licensed model).
- **FFmpeg**: LGPL/GPL (installed separately, not part of this program).
- **NVIDIA CUDA libraries** (cuBLAS, cuDNN): NVIDIA software license.
- **Google Translate** (online option): subject to Google's terms; the subtitle text is sent to Google.
- Other Python packages: see each package's license (all installed from PyPI by `setup.bat`).
