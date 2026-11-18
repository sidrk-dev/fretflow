from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Annotated, AsyncGenerator, Optional

import librosa
import numpy as np
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from .acr_fast import extract_beats, run_fast_chord_recognition
from .acr_neural import _load_bundle, run_neural_chord_recognition
from .aligner import align_lyrics_and_chords
from .audio import (
    SAMPLE_RATE,
    ensure_youtube_audio,
    extract_audio_and_cqt,
    has_cached_audio,
    sweep_temp_audio_files,
)
from .db import (
    delete_session_if_no_chords,
    get_cached_session,
    init_db,
    save_chords_payload,
    update_manual_offset,
    upsert_metadata_and_lyrics,
)
from .lyrics import fetch_best_lyrics
from .schemas import (
    YOUTUBE_ID_PATTERN,
    ChordsPayload,
    LyricsPayload,
    OffsetUpdateRequest,
    SearchResponse,
    SkipSegment,
    SongSession,
)
from .search import clean_track_metadata, resolve_video_metadata, search_songs_and_videos
from .sponsorblock import fetch_sponsorblock_offsets

logger = logging.getLogger("fretflow")

VideoIdPath = Annotated[
    str, Path(pattern=YOUTUBE_ID_PATTERN, min_length=11, max_length=11)
]

_ACR_SEMAPHORE = asyncio.Semaphore(2)
_session_locks: dict[str, asyncio.Lock] = {}
_session_lock_refs: dict[str, int] = {}
_bg_tasks: set[asyncio.Task] = set()


def _warmup_models_and_numba() -> None:
    """Preload PyTorch BTC weights and warm Numba CQT/beat kernels single-threaded."""
    try:
        _load_bundle()
        dummy = np.sin(2 * np.pi * 220.0 * np.linspace(0, 1.6, int(SAMPLE_RATE * 1.6), dtype=np.float32))
        librosa.cqt(dummy, sr=SAMPLE_RATE, n_bins=144, bins_per_octave=24, hop_length=2048)
        librosa.beat.beat_track(y=dummy, sr=SAMPLE_RATE)
    except Exception as exc:
        logger.warning("Startup warmup warning: %s", exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    sweep_temp_audio_files()
    await asyncio.to_thread(_warmup_models_and_numba)
    yield


app = FastAPI(title="FretFlow Guitar Karaoke API", version="0.2.0", lifespan=lifespan)

_allowed_origins = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000",
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "PATCH", "HEAD", "OPTIONS"],
    allow_headers=["*"],
)


def _sse_event(event_name: str, payload: dict) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"


def _sanitize_thumbnail_url(url: str, video_id: str) -> str:
    u = url.strip()
    if u.startswith(("https://i.ytimg.com/", "https://img.youtube.com/", "https://lh3.googleusercontent.com/")):
        return u
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def _spawn_bg_audio_warmup(video_id: str) -> None:
    async def _runner() -> None:
        try:
            await ensure_youtube_audio(video_id)
        except Exception:
            pass

    t = asyncio.create_task(_runner())
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/search", response_model=SearchResponse)
async def api_search(q: str = Query(..., min_length=1, max_length=200)) -> SearchResponse:
    results = await search_songs_and_videos(q)
    return SearchResponse(query=q, results=results)


@app.get("/api/session/{video_id}/stream")
async def stream_song_session(
    video_id: VideoIdPath,
    title: str = Query("", max_length=300),
    artist: str = Query("", max_length=300),
    album: str = Query("", max_length=300),
    duration_sec: int = Query(0, ge=0, le=1800),
    thumbnail_url: str = Query("", max_length=500),
) -> StreamingResponse:
    """Progressive SSE stream: lyrics_ready -> chords_fast -> chords_neural -> done."""

    async def event_generator() -> AsyncGenerator[str, None]:
        vid_lock = _session_locks.setdefault(video_id, asyncio.Lock())
        _session_lock_refs[video_id] = _session_lock_refs.get(video_id, 0) + 1
        try:
            async with vid_lock:
                cached = await asyncio.to_thread(get_cached_session, video_id)
                audio_ready = await asyncio.to_thread(has_cached_audio, video_id)

                cur_title = title.strip() or (cached["title"] if cached else "")
                cur_artist = artist.strip() or (cached["artist"] if cached else "")
                cur_album = album.strip() or (cached["album"] if cached else "")
                cur_dur = duration_sec or (int(cached["duration_sec"]) if cached else 0)
                cur_thumb = _sanitize_thumbnail_url(
                    thumbnail_url or (cached["thumbnail_url"] if cached else ""),
                    video_id,
                )

                trusted_artist = bool(artist.strip() and album.strip())
                if not cur_title:
                    meta = await resolve_video_metadata(video_id)
                    if meta:
                        cur_title = meta.title
                        cur_artist = cur_artist or meta.artist
                        cur_album = cur_album or meta.album
                        cur_dur = cur_dur or meta.durationSec
                        cur_thumb = _sanitize_thumbnail_url(meta.thumbnailUrl, video_id)
                        trusted_artist = True

                clean_t, clean_a = clean_track_metadata(
                    cur_title, cur_artist, trusted_artist=trusted_artist
                )
                lookup_title = clean_t or cur_title
                lookup_artist = clean_a or cur_artist

                lyrics_payload: Optional[LyricsPayload] = None
                skip_segments: list[SkipSegment] = []
                auto_offset_ms = 0
                manual_offset_ms = int(cached["manual_offset_ms"]) if cached else 0

                if cached and cached.get("lyrics_json"):
                    try:
                        lyrics_payload = LyricsPayload.model_validate_json(cached["lyrics_json"])
                        auto_offset_ms = int(cached.get("auto_offset_ms") or 0)
                        skip_raw = json.loads(cached.get("skip_segments_json") or "[]")
                        skip_segments = [SkipSegment.model_validate(s) for s in skip_raw]
                    except Exception:
                        lyrics_payload = None

                if lyrics_payload is None:
                    auto_offset_ms, eff_dur, skip_segments = await fetch_sponsorblock_offsets(
                        video_id, cur_dur
                    )
                    lyrics_payload = await fetch_best_lyrics(
                        title=lookup_title,
                        artist=lookup_artist,
                        album=cur_album,
                        effective_duration_sec=eff_dur,
                    )
                    manual_offset_ms = await asyncio.to_thread(
                        upsert_metadata_and_lyrics,
                        video_id,
                        lookup_title,
                        lookup_artist,
                        cur_album,
                        cur_dur,
                        cur_thumb,
                        auto_offset_ms,
                        skip_segments,
                        lyrics_payload,
                    )

                total_offset_ms = auto_offset_ms + manual_offset_ms
                dur_ms = cur_dur * 1000

                # Fast path: complete cached neural session
                if cached and cached.get("chords_neural_json"):
                    chords_neural = ChordsPayload.model_validate_json(
                        cached["chords_neural_json"]
                    )
                    if not audio_ready:
                        _spawn_bg_audio_warmup(video_id)
                    aligned = align_lyrics_and_chords(
                        lyrics_payload,
                        chords_neural,
                        total_offset_ms,
                        dur_ms,
                        skip_segments=skip_segments,
                        auto_offset_ms=auto_offset_ms,
                        manual_offset_ms=manual_offset_ms,
                    )
                    full_session = SongSession(
                        videoId=video_id,
                        title=lookup_title,
                        artist=lookup_artist,
                        album=cur_album,
                        durationSec=cur_dur,
                        thumbnailUrl=cur_thumb,
                        autoOffsetMs=auto_offset_ms,
                        manualOffsetMs=manual_offset_ms,
                        skipSegments=skip_segments,
                        lyrics=lyrics_payload,
                        chords=chords_neural,
                        alignedSections=aligned,
                        audioReady=audio_ready,
                    )
                    yield _sse_event("chords_neural", full_session.model_dump())
                    yield _sse_event("done", {"cached": True})
                    return

                # Stage 1: Emit synced lyrics + SponsorBlock offset immediately
                initial_aligned = align_lyrics_and_chords(
                    lyrics_payload,
                    None,
                    total_offset_ms,
                    dur_ms,
                    skip_segments=skip_segments,
                    auto_offset_ms=auto_offset_ms,
                    manual_offset_ms=manual_offset_ms,
                )
                stage1 = SongSession(
                    videoId=video_id,
                    title=lookup_title,
                    artist=lookup_artist,
                    album=cur_album,
                    durationSec=cur_dur,
                    thumbnailUrl=cur_thumb,
                    autoOffsetMs=auto_offset_ms,
                    manualOffsetMs=manual_offset_ms,
                    skipSegments=skip_segments,
                    lyrics=lyrics_payload,
                    chords=None,
                    alignedSections=initial_aligned,
                    audioReady=audio_ready,
                )
                yield _sse_event("lyrics_ready", stage1.model_dump())

                # Honor partial chords_fast_json cache if already computed
                cached_fast: Optional[ChordsPayload] = None
                if cached and cached.get("chords_fast_json"):
                    try:
                        cached_fast = ChordsPayload.model_validate_json(
                            cached["chords_fast_json"]
                        )
                    except Exception:
                        cached_fast = None

                if cached_fast is not None:
                    aligned_fast = align_lyrics_and_chords(
                        lyrics_payload,
                        cached_fast,
                        total_offset_ms,
                        dur_ms,
                        skip_segments=skip_segments,
                        auto_offset_ms=auto_offset_ms,
                        manual_offset_ms=manual_offset_ms,
                    )
                    yield _sse_event(
                        "chords_fast",
                        stage1.model_copy(
                            update={
                                "chords": cached_fast,
                                "alignedSections": aligned_fast,
                                "audioReady": audio_ready,
                            }
                        ).model_dump(),
                    )

                try:
                    features = await extract_audio_and_cqt(video_id)
                except RuntimeError:
                    await asyncio.to_thread(delete_session_if_no_chords, video_id)
                    yield _sse_event(
                        "error",
                        {"message": "Could not load audio for this YouTube video."},
                    )
                    return

                actual_dur_sec = cur_dur or int(
                    round(len(features.samples) / float(features.sr))
                )
                dur_ms = actual_dur_sec * 1000

                async with _ACR_SEMAPHORE:
                    if cached_fast is not None:
                        bpm, beats_ms = cached_fast.bpm, cached_fast.beatsMs
                        chords_fast = cached_fast
                    else:
                        bpm, beats_ms = await asyncio.to_thread(extract_beats, features)
                        chords_fast = await asyncio.to_thread(
                            run_fast_chord_recognition, features, bpm, beats_ms
                        )
                        await asyncio.to_thread(
                            save_chords_payload, video_id, chords_fast, actual_dur_sec
                        )

                        aligned_fast = align_lyrics_and_chords(
                            lyrics_payload,
                            chords_fast,
                            total_offset_ms,
                            dur_ms,
                            skip_segments=skip_segments,
                            auto_offset_ms=auto_offset_ms,
                            manual_offset_ms=manual_offset_ms,
                        )
                        yield _sse_event(
                            "chords_fast",
                            stage1.model_copy(
                                update={
                                    "durationSec": actual_dur_sec,
                                    "chords": chords_fast,
                                    "alignedSections": aligned_fast,
                                    "audioReady": True,
                                }
                            ).model_dump(),
                        )

                    chords_neural = await asyncio.to_thread(
                        run_neural_chord_recognition, features, bpm, beats_ms
                    )
                    await asyncio.to_thread(
                        save_chords_payload, video_id, chords_neural, actual_dur_sec
                    )

                aligned_neural = align_lyrics_and_chords(
                    lyrics_payload,
                    chords_neural,
                    total_offset_ms,
                    dur_ms,
                    skip_segments=skip_segments,
                    auto_offset_ms=auto_offset_ms,
                    manual_offset_ms=manual_offset_ms,
                )
                stage3 = stage1.model_copy(
                    update={
                        "durationSec": actual_dur_sec,
                        "chords": chords_neural,
                        "alignedSections": aligned_neural,
                        "audioReady": True,
                    }
                )
                yield _sse_event("chords_neural", stage3.model_dump())
                yield _sse_event("done", {"cached": False})

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("SSE session failure for %s: %s", video_id, exc)
            yield _sse_event(
                "error", {"message": "Failed to analyze this track. Please try another version."}
            )
        finally:
            rem = _session_lock_refs.get(video_id, 1) - 1
            if rem <= 0:
                _session_lock_refs.pop(video_id, None)
                _session_locks.pop(video_id, None)
            else:
                _session_lock_refs[video_id] = rem

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.patch("/api/session/{video_id}/offset", response_model=SongSession)
async def patch_session_offset(
    video_id: VideoIdPath, body: OffsetUpdateRequest
) -> SongSession:
    updated = await asyncio.to_thread(
        update_manual_offset, video_id, body.manualOffsetMs
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Session not found")

    cached = await asyncio.to_thread(get_cached_session, video_id)
    if not cached:
        raise HTTPException(status_code=404, detail="Session not found")

    lyrics_payload = (
        LyricsPayload.model_validate_json(cached["lyrics_json"])
        if cached.get("lyrics_json")
        else None
    )
    chords_json = cached.get("chords_neural_json") or cached.get("chords_fast_json")
    chords_payload = (
        ChordsPayload.model_validate_json(chords_json) if chords_json else None
    )
    skip_segments = [
        SkipSegment.model_validate(s)
        for s in json.loads(cached.get("skip_segments_json") or "[]")
    ]

    auto_off = int(cached.get("auto_offset_ms") or 0)
    man_off = int(body.manualOffsetMs)
    dur_sec = int(cached.get("duration_sec") or 0)

    aligned = align_lyrics_and_chords(
        lyrics_payload,
        chords_payload,
        auto_off + man_off,
        dur_sec * 1000,
        skip_segments=skip_segments,
        auto_offset_ms=auto_off,
        manual_offset_ms=man_off,
    )
    audio_ready = await asyncio.to_thread(has_cached_audio, video_id)

    return SongSession(
        videoId=video_id,
        title=cached.get("title") or "",
        artist=cached.get("artist") or "",
        album=cached.get("album") or "",
        durationSec=dur_sec,
        thumbnailUrl=cached.get("thumbnail_url") or "",
        autoOffsetMs=auto_off,
        manualOffsetMs=man_off,
        skipSegments=skip_segments,
        lyrics=lyrics_payload,
        chords=chords_payload,
        alignedSections=aligned,
        audioReady=audio_ready,
    )


@app.api_route("/api/audio/{video_id}", methods=["GET", "HEAD"])
async def stream_cached_audio(video_id: VideoIdPath) -> FileResponse:
    """Serve cached MP3 via Starlette FileResponse (RFC 9110 Range, suffix, HEAD, 416, chunked async I/O)."""
    try:
        path = await ensure_youtube_audio(video_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail="Audio unavailable for this video") from exc

    if not path.is_file():
        raise HTTPException(status_code=404, detail="Audio not available")

    return FileResponse(
        path=path,
        media_type="audio/mpeg",
        content_disposition_type="inline",
    )


# Serve compiled React SPA in production when `frontend/dist` exists
_FRONTEND_DIST = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
)
if os.path.isdir(_FRONTEND_DIST):
    from fastapi.staticfiles import StaticFiles

    class _ImmutableStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope):  # type: ignore[override]
            resp = await super().get_response(path, scope)
            if resp.status_code == 200:
                resp.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
            return resp

    _assets_dir = os.path.join(_FRONTEND_DIST, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", _ImmutableStaticFiles(directory=_assets_dir), name="assets")

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = os.path.realpath(os.path.join(_FRONTEND_DIST, full_path))
        if (
            full_path
            and candidate.startswith(os.path.realpath(_FRONTEND_DIST) + os.sep)
            and os.path.isfile(candidate)
        ):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_FRONTEND_DIST, "index.html"))

