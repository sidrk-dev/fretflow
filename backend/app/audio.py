from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np

AUDIO_CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "audio"
SAMPLE_RATE = 22050
HOP_LENGTH = 2048
N_BINS = 144
BINS_PER_OCTAVE = 24

_download_locks: dict[str, asyncio.Lock] = {}


@dataclass
class AudioFeatures:
    audio_path: Path
    samples: np.ndarray
    sr: int
    cqt_mag: np.ndarray        # shape: (144, T)
    log_cqt_frames: np.ndarray # shape: (T, 144), float32 for BTC
    frame_duration: float      # hop_length / sr (~0.09288s)


def get_cached_audio_path(video_id: str) -> Path:
    AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return AUDIO_CACHE_DIR / f"{video_id}.mp3"


async def ensure_youtube_audio(video_id: str) -> Path:
    """Download lightweight mono audio for YouTube video_id using yt-dlp + ffmpeg."""
    target_path = get_cached_audio_path(video_id)
    if target_path.exists() and target_path.stat().st_size > 16_384:
        return target_path

    lock = _download_locks.setdefault(video_id, asyncio.Lock())
    async with lock:
        if target_path.exists() and target_path.stat().st_size > 16_384:
            return target_path

        temp_template = str(AUDIO_CACHE_DIR / f"{video_id}.temp.%(ext)s")
        url = f"https://www.youtube.com/watch?v={video_id}"

        proc = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "-f",
            "ba[abr<=160]/ba/b",
            "--no-playlist",
            "--no-warnings",
            "-x",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "5",
            "--postprocessor-args",
            "ffmpeg:-ac 1 -ar 22050",
            "-o",
            temp_template,
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        temp_mp3 = AUDIO_CACHE_DIR / f"{video_id}.temp.mp3"

        if proc.returncode != 0 or not temp_mp3.exists():
            err_msg = stderr.decode("utf-8", errors="ignore")[-400:]
            raise RuntimeError(f"Failed to extract YouTube audio for {video_id}: {err_msg}")

        temp_mp3.replace(target_path)
        return target_path


def _compute_cqt_sync(audio_path: Path) -> AudioFeatures:
    samples, sr = librosa.load(str(audio_path), sr=SAMPLE_RATE, mono=True)
    cqt = librosa.cqt(
        samples,
        sr=sr,
        n_bins=N_BINS,
        bins_per_octave=BINS_PER_OCTAVE,
        hop_length=HOP_LENGTH,
        fmin=float(librosa.note_to_hz("C1")),
    )
    cqt_mag = np.abs(cqt).astype(np.float32)
    log_cqt_frames = np.log(cqt_mag + 1e-6).T.astype(np.float32)
    frame_duration = float(HOP_LENGTH) / float(sr)
    return AudioFeatures(
        audio_path=audio_path,
        samples=samples,
        sr=sr,
        cqt_mag=cqt_mag,
        log_cqt_frames=log_cqt_frames,
        frame_duration=frame_duration,
    )


async def extract_audio_and_cqt(video_id: str) -> AudioFeatures:
    audio_path = await ensure_youtube_audio(video_id)
    return await asyncio.to_thread(_compute_cqt_sync, audio_path)
