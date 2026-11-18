from __future__ import annotations

import asyncio
import json
import os
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from .acr_fast import extract_beats, run_fast_chord_recognition
from .acr_neural import run_neural_chord_recognition
from .aligner import align_lyrics_and_chords
from .audio import ensure_youtube_audio, extract_audio_and_cqt, get_cached_audio_path
from .db import (
    get_cached_session,
    init_db,
    save_chords_payload,
    update_manual_offset,
    upsert_metadata_and_lyrics,
)
from .lyrics import fetch_best_lyrics
from .schemas import (
    ChordsPayload,
    LyricsPayload,
    OffsetUpdateRequest,
    SearchResponse,
    SkipSegment,
    SongSession,
)
from .search import clean_track_metadata, resolve_video_metadata, search_songs_and_videos
from .sponsorblock import fetch_sponsorblock_offsets

app = FastAPI(title="FretFlow Guitar Karaoke API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _on_startup() -> None:
    init_db()


def _sse_event(event_name: str, payload: dict) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/search", response_model=SearchResponse)
async def api_search(q: str = Query(..., min_length=1, max_length=200)) -> SearchResponse:
    results = await search_songs_and_videos(q)
    return SearchResponse(query=q, results=results)


@app.get("/api/session/{video_id}/stream")
async def stream_song_session(
    video_id: str,
    title: str = Query(""),
    artist: str = Query(""),
    album: str = Query(""),
    duration_sec: int = Query(0),
    thumbnail_url: str = Query(""),
) -> StreamingResponse:
    """
    Progressive Server-Sent Events (SSE) stream for loading a Guitar Karaoke session:
      1. `lyrics_ready` (~300ms): Metadata + SponsorBlock auto-offset + Synced Lyrics
      2. `chords_fast` (~1.5s): Librosa BPM/beats + CQT-HMM chords + Smart Capo + Aligned Sections
      3. `chords_neural` (~3.0s): PyTorch BTC 170-chord HD upgrade + Aligned Sections
      4. `done`
    Replays from SQLite in <20ms when cached!
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            cached = get_cached_session(video_id)
            audio_file = get_cached_audio_path(video_id)
            has_audio = audio_file.exists() and audio_file.stat().st_size > 16_384

            # Resolve metadata if missing
            cur_title = title.strip() or (cached["title"] if cached else "")
            cur_artist = artist.strip() or (cached["artist"] if cached else "")
            cur_album = album.strip() or (cached["album"] if cached else "")
            cur_dur = duration_sec or (int(cached["duration_sec"]) if cached else 0)
            cur_thumb = (
                thumbnail_url.strip()
                or (cached["thumbnail_url"] if cached else "")
                or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
            )

            if not cur_title:
                meta = await resolve_video_metadata(video_id)
                if meta:
                    cur_title = meta.title
                    cur_artist = cur_artist or meta.artist
                    cur_album = cur_album or meta.album
                    cur_dur = cur_dur or meta.durationSec
                    cur_thumb = meta.thumbnailUrl or cur_thumb

            clean_t, clean_a = clean_track_metadata(cur_title, cur_artist)
            lookup_title = clean_t or cur_title
            lookup_artist = clean_a or cur_artist

            # Check cached lyrics + SponsorBlock
            lyrics_payload: Optional[LyricsPayload] = None
            skip_segments: list[SkipSegment] = []
            auto_offset_ms = 0
            manual_offset_ms = int(cached["manual_offset_ms"]) if cached else 0

            if cached and cached.get("lyrics_json"):
                try:
                    parsed_lyr = LyricsPayload.model_validate_json(cached["lyrics_json"])
                    if parsed_lyr.source != "none":
                        lyrics_payload = parsed_lyr
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
                manual_offset_ms = upsert_metadata_and_lyrics(
                    video_id=video_id,
                    title=lookup_title,
                    artist=lookup_artist,
                    album=cur_album,
                    duration_sec=cur_dur,
                    thumbnail_url=cur_thumb,
                    auto_offset_ms=auto_offset_ms,
                    skip_segments=skip_segments,
                    lyrics=lyrics_payload,
                )

            total_offset_ms = auto_offset_ms + manual_offset_ms
            dur_ms = cur_dur * 1000

            # Fast path: if neural chords are ALREADY cached in SQLite, emit full session immediately!
            if cached and cached.get("chords_neural_json"):
                chords_neural = ChordsPayload.model_validate_json(cached["chords_neural_json"])
                # Ensure audio file is warm in background if ever evicted
                if not has_audio:
                    asyncio.create_task(ensure_youtube_audio(video_id))
                aligned = align_lyrics_and_chords(
                    lyrics_payload, chords_neural, total_offset_ms, dur_ms
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
                    audioReady=has_audio,
                )
                yield _sse_event("chords_neural", full_session.model_dump())
                yield _sse_event("done", {"cached": True})
                return

            # Stage 1: Emit lyrics + SponsorBlock offset immediately (~300ms)
            initial_aligned = align_lyrics_and_chords(
                lyrics_payload, None, total_offset_ms, dur_ms
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
                audioReady=has_audio,
            )
            yield _sse_event("lyrics_ready", stage1.model_dump())

            # Extract shared 22.05kHz audio + 144-bin CQT spectrogram
            features = await extract_audio_and_cqt(video_id)
            actual_dur_sec = cur_dur or int(round(len(features.samples) / float(features.sr)))
            dur_ms = actual_dur_sec * 1000

            # Stage 2: Fast Librosa Beat Tracker + CQT-HMM Chords
            bpm, beats_ms = await asyncio.to_thread(extract_beats, features)
            chords_fast = await asyncio.to_thread(
                run_fast_chord_recognition, features, bpm, beats_ms
            )
            save_chords_payload(video_id, chords_fast)

            aligned_fast = align_lyrics_and_chords(
                lyrics_payload, chords_fast, total_offset_ms, dur_ms
            )
            stage2 = stage1.model_copy(
                update={
                    "durationSec": actual_dur_sec,
                    "chords": chords_fast,
                    "alignedSections": aligned_fast,
                    "audioReady": True,
                }
            )
            yield _sse_event("chords_fast", stage2.model_dump())

            # Stage 3: Neural PyTorch BTC 170-Chord Transformer Upgrade
            chords_neural = await asyncio.to_thread(
                run_neural_chord_recognition, features, bpm, beats_ms
            )
            save_chords_payload(video_id, chords_neural)

            aligned_neural = align_lyrics_and_chords(
                lyrics_payload, chords_neural, total_offset_ms, dur_ms
            )
            stage3 = stage2.model_copy(
                update={
                    "chords": chords_neural,
                    "alignedSections": aligned_neural,
                    "audioReady": True,
                }
            )
            yield _sse_event("chords_neural", stage3.model_dump())
            yield _sse_event("done", {"cached": False})

        except Exception as exc:
            yield _sse_event("error", {"message": str(exc)})

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
async def patch_session_offset(video_id: str, body: OffsetUpdateRequest) -> SongSession:
    update_manual_offset(video_id, body.manualOffsetMs)
    cached = get_cached_session(video_id)
    if not cached:
        raise HTTPException(status_code=404, detail="Session not found")

    lyrics_payload = (
        LyricsPayload.model_validate_json(cached["lyrics_json"])
        if cached.get("lyrics_json")
        else None
    )
    chords_json = cached.get("chords_neural_json") or cached.get("chords_fast_json")
    chords_payload = ChordsPayload.model_validate_json(chords_json) if chords_json else None
    skip_segments = [
        SkipSegment.model_validate(s)
        for s in json.loads(cached.get("skip_segments_json") or "[]")
    ]

    auto_off = int(cached.get("auto_offset_ms") or 0)
    man_off = int(body.manualOffsetMs)
    dur_sec = int(cached.get("duration_sec") or 0)

    aligned = align_lyrics_and_chords(
        lyrics_payload, chords_payload, auto_off + man_off, dur_sec * 1000
    )
    audio_file = get_cached_audio_path(video_id)

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
        audioReady=audio_file.exists(),
    )


@app.get("/api/audio/{video_id}")
async def stream_cached_audio(video_id: str, request: Request) -> Response:
    """Serve cached MP3 with HTTP 206 Range support for seamless fallback playback & seeking."""
    path = await ensure_youtube_audio(video_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio not available")

    file_size = os.path.getsize(path)
    range_header = request.headers.get("range")

    if range_header:
        m = range_header.strip().lower().replace("bytes=", "").split("-", 1)
        start = int(m[0]) if m[0] else 0
        end = int(m[1]) if (len(m) > 1 and m[1]) else file_size - 1
        end = min(end, file_size - 1)
        if start >= file_size or start > end:
            raise HTTPException(status_code=416, detail="Requested Range Not Satisfiable")
        chunk_len = end - start + 1
        with open(path, "rb") as f:
            f.seek(start)
            data = f.read(chunk_len)
        return Response(
            content=data,
            status_code=206,
            media_type="audio/mpeg",
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_len),
            },
        )

    with open(path, "rb") as f:
        data = f.read()
    return Response(
        content=data,
        status_code=200,
        media_type="audio/mpeg",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        },
    )
