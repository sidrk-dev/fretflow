# FretFlow — Guitar Karaoke Studio

A YouTube-powered Guitar Karaoke web app combining **Ultimate Guitar**-style chords-over-lyrics with **Apple Music Sing** word-by-word karaoke highlighting and **Dual-Mode AI Chord Recognition**.

## Features
- **Hybrid YouTube Music & Video Search:** Pulls clean Studio Audio (`0:00`), Official Music Videos, and Live/Acoustic covers (`ytmusicapi` + `yt-dlp`) without API keys.
- **Multi-Source Synced Lyrics Waterfall:** Queries **BetterLyrics (TTML word-sync + Verse/Chorus headers)**, **LRCLIB (native word-sync YAML + LRC)**, and **`syncedlyrics` (NetEase / Musixmatch / Megalobiz)**.
- **Automatic Music Video Offset Sync:** Uses **SponsorBlock (`music_offtopic`)** to detect non-music intro/outro skits on official music videos and shifts studio lyrics automatically.
- **Dual-Mode Audio Chord Recognition:**
  1. **Fast Preview (~1.5s):** Tuning-compensated `librosa` 144-bin CQT Chroma + Viterbi HMM + BPM beat tracker.
  2. **Neural HD Upgrade (~3s):** **ChordMini PyTorch BTC** 170-chord Bi-Directional Transformer (`maj7`, `m7`, `7`, `sus4`, `sus2`, `dim7`, `m7b5`, `aug`, `6`).
- **Smart Capo Optimizer & Beginner Simplify:** Scores Capo frets `0–7` for open guitar chord ergonomics, with instant `0ms` client-side Capo, Transpose, and Simplify toggles.
- **Interactive SVG Guitar Fretboards + WebAudio Strummer:** Live "Playing Now" & "Up Next" diagrams, multiple neck voicings (open + E/A barre shapes), Left-Handed fretboard mirror (`Lefty`), and a native `popover` Song Chord Dictionary.
- **Practice Transport:** A–B section looping, `0.5x–1.25x` pitch-preserved speed trainer, `±250ms` lyric sync nudges (`[` / `]`), Tap-1st-Word sync, and automatic local MP3 Range-streaming fallback if YouTube restricts iframe embedding.

## Quick Start (Local Development)

Prerequisites: **Python 3.12+**, **[uv](https://docs.astral.sh/uv/)**, **Node.js 22+ / pnpm 11+**, and **`ffmpeg`**.

```bash
chmod +x dev.sh
./dev.sh
```

`dev.sh` automatically runs `uv sync` and `pnpm install` on first launch, starts the FastAPI backend on `http://127.0.0.1:8000`, and serves the Studio UI at **http://127.0.0.1:5173** (`http://localhost:5173`).

## Production Deployment (Docker)

Build and run the self-contained single-port production container (serves both the compiled React SPA and FastAPI + PyTorch BTC chord engine on port `8000`):

```bash
docker compose up --build -d
```

Then open **http://localhost:8000**.
