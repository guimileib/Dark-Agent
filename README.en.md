# 🎬 DarkAgent Pro

[🇧🇷 Português](README.md) · 🇺🇸 English

A Windows desktop app that downloads videos, generates AI subtitles (Whisper), edits and publishes to TikTok, all from a single window.

## ✨ Features

| Tab | What it does |
|-----|--------------|
| **Download** | Downloads from YouTube and other sites (yt-dlp) with automatic fallback between strategies and an optional text marker |
| **Smart Clips** | Finds the best moments (scene changes + audio energy) and exports short clips |
| **Subtitles** | Transcribes with Whisper (GPU or CPU) and burns animated subtitles, with a real-time preview |
| **Upload** | Publishes or schedules to TikTok with multiple accounts and browsers |
| **Editor** | Timed text and image overlays, plus compilations ("Guess the Song", rankings) |

It ships with 12 subtitle styles: TikTok Classic, TikTok Bold, Instagram Reels, YouTube Shorts, Clean Minimal, Neon Glow, Bold Impact, Gradient Wave, Outline Style, Shadow Pop, Typewriter and Karaoke Style.

> The app interface is in Portuguese.

## 📥 For users

1. Download `DarkAgentLauncher.exe` from **[Releases](https://github.com/guimileib/Dark-Agent/releases/latest)**.
2. Put it in its own folder (e.g. `Documents\DarkAgent`). The app creates `logs/`, `cache/` and `output/` next to it.
3. Open it. If Windows SmartScreen warns you, click **More info → Run anyway**.
4. On the first run, accept the FFmpeg download.

> The first launch can take 1–2 minutes because the executable unpacks itself. Only one window can be open at a time: a second click tells you the app is already running.

**Updates are automatic:** on startup the app checks the latest Release and offers to install the new version.

## 🛠️ Development

Requirements: Windows, Python 3.11 and Git.

```bash
git clone https://github.com/guimileib/Dark-Agent.git
cd Dark-Agent
python -m venv venv
venv\Scripts\activate

# PyTorch first (CPU; for GPU use the CUDA index from pytorch.org)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

copy .env.example .env   # optional
python -m src.main
```

Checks and tests (the same ones CI runs):

```bash
python scripts/check_structure.py --imports
pytest tests/
```

## 📦 Building the .exe

```bash
build_exe.bat
```

The output is `dist\DarkAgentLauncher.exe`. To share it, send **only the `.exe`**: the folders next to it in `dist\` hold your own cookies and keys.

The build always uses `DarkAgentLauncher.spec`, which sets `pathex`, `collect_submodules` and bundles yt-dlp. Without it the `.exe` comes out incomplete.

## 🚀 Releasing a version

The `.github/workflows/ci.yml` workflow works like this:

| Event | What runs |
|-------|-----------|
| PR to `main` | Structural check, imports and pytest |
| Push to `main` | The same; if `__version__` has no tag yet, builds the `.exe` and publishes the Release |
| Push of a `vX.Y.Z` tag | The same, and publishes the Release (the tag must match `__version__`) |

To ship an update:

```bash
# 1. Bump __version__ in src/__init__.py (e.g. 2.0.3 -> 2.0.4)
# 2. Merge/push to main
```

Users get the new version the next time they open the app. Without a version bump, a push only runs CI. The repository must be public, because the update check is anonymous.

## 🧱 Layout

```
src/
├── launcher.py   # .exe entry point (splash, FFmpeg, single instance)
├── main.py       # UI bootstrap
├── config/       # paths.py (single source of paths), settings.py
├── models/       # EstiloLegenda, VideoMetadata, Overlay
├── core/         # downloader, transcriber, video_editor, uploader, ...
├── ui/           # main_window and per-tab widgets
└── utils/        # ffmpeg_utils, single_instance
scripts/check_structure.py   # structural check used by CI
```

Docstrings: Portuguese, at most 3 lines (summary + the why, if needed). CI fails anything longer.

## 🧰 Tech stack

PyQt6 · yt-dlp · OpenAI Whisper · PyTorch · FFmpeg · Selenium · PyInstaller

## 📧 Contact

- Email: visualizepluss@gmail.com
- Website: https://visualizeplus.com
