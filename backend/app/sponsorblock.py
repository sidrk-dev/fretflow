from __future__ import annotations

import httpx

from .schemas import SkipSegment

SPONSORBLOCK_URL = "https://sponsor.ajay.app/api/skipSegments"


def merge_skip_segments(segments: list[SkipSegment], gap_tolerance_ms: int = 1000) -> list[SkipSegment]:
    """Sort and merge overlapping or contiguous (<1s gap) SponsorBlock segments."""
    if not segments:
        return []
    ordered = sorted(segments, key=lambda s: (s.startMs, s.endMs))
    merged: list[SkipSegment] = [ordered[0].model_copy()]
    for seg in ordered[1:]:
        last = merged[-1]
        if seg.startMs <= last.endMs + gap_tolerance_ms:
            last.endMs = max(last.endMs, seg.endMs)
        else:
            merged.append(seg.model_copy())
    return merged


async def fetch_sponsorblock_offsets(
    video_id: str, video_duration_sec: int = 0
) -> tuple[int, int, list[SkipSegment]]:
    """
    Query SponsorBlock `music_offtopic` segments for a YouTube video.

    Returns:
        (auto_offset_ms, effective_song_duration_sec, merged_skip_segments)
    """
    if not video_id:
        return 0, video_duration_sec, []

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(
                SPONSORBLOCK_URL,
                params={
                    "videoID": video_id,
                    "categories": '["music_offtopic"]',
                },
            )
            if resp.status_code != 200:
                return 0, video_duration_sec, []
            data = resp.json()
            if not isinstance(data, list):
                return 0, video_duration_sec, []
    except Exception:
        return 0, video_duration_sec, []

    raw_segments: list[SkipSegment] = []
    inferred_vid_dur = float(video_duration_sec)

    for item in data:
        seg = item.get("segment")
        if not isinstance(seg, list) or len(seg) != 2:
            continue
        start_s, end_s = float(seg[0]), float(seg[1])
        if end_s <= start_s:
            continue
        vid_d = float(item.get("videoDuration") or 0.0)
        if vid_d > inferred_vid_dur:
            inferred_vid_dur = vid_d

        raw_segments.append(
            SkipSegment(
                category=str(item.get("category") or "music_offtopic"),
                startMs=int(round(start_s * 1000)),
                endMs=int(round(end_s * 1000)),
            )
        )

    merged = merge_skip_segments(raw_segments)
    total_skipped_sec = sum((s.endMs - s.startMs) / 1000.0 for s in merged)
    intro_offset_ms = merged[0].endMs if (merged and merged[0].startMs <= 3000) else 0

    effective_dur = int(round(max(0.0, inferred_vid_dur - total_skipped_sec)))
    if effective_dur <= 0:
        effective_dur = video_duration_sec

    return intro_offset_ms, effective_dur, merged
