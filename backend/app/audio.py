from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np

from .schemas import YOUTUBE_ID_RE

AUDIO_CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "audio"
SAMPLE_RATE = 22050
HOP_LENGTH = 2048
N_BINS = 144
BINS_PER_OCTAVE = 24
MIN_VALID_AUDIO_BYTES = 1024

_download_locks: dict[str, asyncio.Lock] = {}
_lock_refcounts: dict[str, int] = {}


@dataclass
class AudioFeatures:
    audio_path: Path
    samples: np.ndarray
    sr: int
    cqt_mag: np.ndarray        # shape: (144, T)
    log_cqt_frames: np.ndarray # shape: (T, 144), float32 for BTC
    frame_duration: float      # hop_length / sr (~0.09288s)


def get_cached_audio_path(video_id: str) -> Path:
    if not YOUTUBE_ID_RE.fullmatch(video_id):
        raise ValueError("Invalid YouTube video ID")
    base = AUDIO_CACHE_DIR.resolve()
    base.mkdir(parents=True, exist_ok=True)
    candidate = (base / f"{video_id}.mp3").resolve()
    if not candidate.is_relative_to(base):
        raise ValueError("Invalid cache path")
    return candidate


def has_cached_audio(video_id: str) -> bool:
    try:
        path = get_cached_audio_path(video_id)
        return path.is_file() and path.stat().st_size > MIN_VALID_AUDIO_BYTES
    except ValueError:
        return False


def _cleanup_temp_files(video_id: str) -> None:
    if not YOUTUBE_ID_RE.fullmatch(video_id):
        return
    base = AUDIO_CACHE_DIR.resolve()
    if not base.exists():
        return
    for p in base.glob(f"{video_id}.temp.*"):
        p.unlink(missing_ok=True)


MAX_CACHED_AUDIO_FILES = 30


def prune_audio_cache(max_files: int = MAX_CACHED_AUDIO_FILES) -> None:
    base = AUDIO_CACHE_DIR.resolve()
    if not base.exists():
        return
    mp3s = sorted(
        (p for p in base.glob("*.mp3") if not p.name.endswith(".temp.mp3")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for stale in mp3s[max_files:]:
        stale.unlink(missing_ok=True)


def sweep_temp_audio_files() -> None:
    base = AUDIO_CACHE_DIR.resolve()
    base.mkdir(parents=True, exist_ok=True)
    for p in base.glob("*.temp.*"):
        p.unlink(missing_ok=True)
    prune_audio_cache()


async def ensure_youtube_audio(video_id: str) -> Path:
    """Download lightweight mono audio for YouTube video_id with timeout & cancellation cleanup."""
    target_path = get_cached_audio_path(video_id)
    if target_path.is_file() and target_path.stat().st_size > MIN_VALID_AUDIO_BYTES:
        return target_path

    lock = _download_locks.setdefault(video_id, asyncio.Lock())
    _lock_refcounts[video_id] = _lock_refcounts.get(video_id, 0) + 1
    try:
        async with lock:
            if target_path.is_file() and target_path.stat().st_size > MIN_VALID_AUDIO_BYTES:
                return target_path

            _cleanup_temp_files(video_id)
            temp_template = str(AUDIO_CACHE_DIR.resolve() / f"{video_id}.temp.%(ext)s")
            url = f"https://www.youtube.com/watch?v={video_id}"

            proc = await asyncio.create_subprocess_exec(
                "yt-dlp",
                "-f",
                "ba[abr<=160]/ba/b",
                "--no-playlist",
                "--no-warnings",
                "--max-filesize",
                "50M",
                "--match-filter",
                "duration <= 1200 & !is_live",
                "-x",
                "--audio-format",
                "mp3",
                "--audio-quality",
                "5",
                "--postprocessor-args",
                "ffmpeg:-ac 1 -ar 22050",
                "-o",
                temp_template,
                "--",
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, _ = await asyncio.wait_for(proc.communicate(), timeout=90.0)
            except BaseException:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()
                _cleanup_temp_files(video_id)
                raise

            temp_mp3 = AUDIO_CACHE_DIR.resolve() / f"{video_id}.temp.mp3"
            if proc.returncode != 0 or not temp_mp3.is_file():
                _cleanup_temp_files(video_id)
                raise RuntimeError(f"Audio unavailable for YouTube video {video_id}")

            temp_mp3.replace(target_path)
            _cleanup_temp_files(video_id)
            prune_audio_cache()
            return target_path
    finally:
        rem = _lock_refcounts.get(video_id, 1) - 1
        if rem <= 0:
            _lock_refcounts.pop(video_id, None)
            _download_locks.pop(video_id, None)
        else:
            _lock_refcounts[video_id] = rem


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
