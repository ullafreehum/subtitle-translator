# Subtitle Translator — architecture

Windows desktop app: video in → speech-to-text (faster-whisper, GPU) → subtitle cues →
translation into one or more languages → SRT files → optional review/edit → optional
burned-in video. Python 3.12 venv in `.venv`, ffmpeg/ffprobe/ffplay on PATH.

## Modules (one owner each)

| File | Role |
|------|------|
| `engine.py` | Orchestration: audio extraction, transcription, `process_video`, `burn_video`, CLI. Re-exports `LANGUAGES`, `MODEL_SIZES`, `TRANSLATORS`. |
| `subtitles.py` | `Cue` type, building readable cues from word timestamps, wrapping, SRT read/write. No heavy imports. |
| `translation.py` | All translators (NLLB offline, Google online + MyMemory backup), sentence grouping, glossary enforcement. |
| `glossary.py` | Loading the user's glossary file. No heavy imports. |
| `app.py` | Main window: batch queue, drag & drop, settings, progress. |
| `editor.py` | Subtitle review/edit window and burn trigger. |
| `setup.ps1`, `setup.bat`, `build_exe.bat` | Install on a new PC / build a standalone exe. |

Models are downloaded at runtime: NLLB into `models/` (git-ignored), Whisper into the
Hugging Face cache (`%USERPROFILE%\.cache\huggingface`).

## Interfaces

### subtitles.py
```python
@dataclass
class Cue:
    start: float   # seconds
    end: float     # seconds
    text: str      # may contain "\n" line breaks

def build_cues(segments: list[dict], max_chars_per_line: int = 42, max_lines: int = 2,
               max_duration: float = 6.0, min_duration: float = 1.0,
               max_cps: float = 17.0, min_gap: float = 0.08) -> list[Cue]
# segments: [{"start": float, "end": float, "text": str,
#             "words": [{"start": float, "end": float, "word": str}, ...]}]   # words may be empty/missing
def wrap_text(text: str, width: int = 42, max_lines: int = 2) -> str
def write_srt(cues: list[Cue], path: str, width: int = 42) -> None   # re-wraps each cue's text
def read_srt(path: str) -> list[Cue]      # keeps empty cues, so cue numbering stays aligned
```

### glossary.py
```python
class Glossary:
    keep_terms: list[str]                       # names/terms kept exactly as written
    def translations(self, source: str, target: str) -> dict[str, str]   # forced term translations for a pair
    hints: list[str]                            # [hints]: recognition-only words
    def whisper_prompt(self) -> str             # hints + keep_terms (<= WHISPER_PROMPT_MAX chars), for Whisper initial_prompt
    def fix_terms(self, text: str, lang: str | None = None) -> str   # keep-term spelling + [lang>lang] corrections
def load_glossary(path: str | None = None) -> Glossary
# default path: glossary.txt next to the module; if missing, copy glossary.example.txt there.
# Never raises for a missing/invalid file: returns an empty Glossary.
GLOSSARY_PATH: str   # default glossary.txt path (the GUI opens it for editing)
```
File format (UTF-8):
```
# comments start with #
# Lines outside any section: terms kept exactly as written (also helps speech recognition)
DİLGEM
JASPER

# [source>target] sections: forced translations for that language pair
[en>tr]
trainees = kursiyerler
trainee = kursiyer
```

### translation.py
```python
TRANSLATORS: dict[str, str]   # display name -> id: "nllb", "online"
DEFAULT_TRANSLATOR = "nllb"
class Cancelled(Exception): ...          # engine re-exports this same class
class TranslationError(RuntimeError): ...
def translate_texts(texts: list[str], source: str, target: str, translator: str = DEFAULT_TRANSLATOR,
                    glossary: "Glossary | None" = None,
                    log=print, progress=lambda p: None, cancel: threading.Event | None = None) -> list[str]
# texts: one string per cue (Whisper language codes, e.g. "en", "tr", "zh").
# Returns one translated string per input, same length. progress: 0..1 local to this call.
# Raises Cancelled when `cancel` is set, TranslationError when every translator failed.
```

### engine.py
```python
LANGUAGES: dict[str, str]           # display name -> Whisper code
MODEL_SIZES: list[str]; DEFAULT_MODEL = "large-v3-turbo"
TRANSLATORS, DEFAULT_TRANSLATOR      # re-exported from translation.py
class Cancelled(Exception)           # same class as translation.Cancelled

@dataclass
class BurnStyle:
    position: str = "bottom"        # "bottom" | "top"
    font_size: str = "auto"         # "auto" | "small" | "medium" | "large"
    box: bool = False               # semi-transparent background box behind text
    font: str = "Arial"

def process_video(video_path: str, target_langs: list[str], source_lang: str | None = None,
                  model_size: str = DEFAULT_MODEL, translator: str = DEFAULT_TRANSLATOR,
                  burn: bool = False, burn_style: BurnStyle | None = None,
                  output_dir: str | None = None, glossary_path: str | None = None,
                  log=print, progress=lambda p: None,
                  cancel: threading.Event | None = None, vtt: bool = False,
                  retime_translation: bool = True, resume: bool = True,
                  clean_audio: bool = False, export_formats: tuple[str, ...] = ()) -> dict
# returns {"video": str, "detected_language": str, "original_srt": str,
#          "translated_srts": {lang: path}, "burned_videos": {lang: path},
#          "transcripts": {lang: [paths]}}
# Output names: <stem>.<lang>.srt, <stem>.<lang>.subtitled.mp4, <stem>.<lang>.transcript.docx/.txt
# (output_dir or video folder).
# retime_translation: translated sentences are laid out as their own readable cues
#   (translation.translate_texts(..., return_groups=True)) instead of the original cue times.
# resume: speech-recognition results are checkpointed while running; an interrupted video
#   continues where it stopped on the next run.
# translator "nllb_large" (NLLB-200 3.3B) is offered by translation.available_translators()
#   only when models/nllb-200-3.3B is present; engine.free_speech_model() and
#   translation.free_gpu_models() make room for it on a 4 GB GPU.

### transcript.py
export_transcript(cues, path, title, language, timestamps=True, fmt="docx"|"txt"|"md")
export_srt_transcript(srt_path, out_path, fmt, timestamps)   # used by the editor

def burn_video(video_path: str, srt_path: str, out_path: str | None = None,
               style: BurnStyle | None = None, log=print, progress=lambda p: None,
               cancel: threading.Event | None = None) -> str   # returns output path
# progress 0..1 local. out_path default: <video stem>.<lang from srt name>.subtitled.mp4 next to the SRT.
```
`log`/`progress` are called from the worker thread; the GUI must marshal to Tk via a queue.
