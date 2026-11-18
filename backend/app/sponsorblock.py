from __future__ import annotations

import httpx

from .schemas import SkipSegment

SPONSORBLOCK_URL = "https://sponsor.ajay.app/api/skipSegments"


async def fetch_sponsorblock_offsets(
    video_id: str, video_duration_sec: int = 0
) -> tuple[int, int, list[SkipSegment]]:
    """
    Query SponsorBlock `music_offtopic` segments for a YouTube video.

    Returns:
        (auto_offset_ms, effective_song_duration_sec, skip_segments)
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

    segments: list[SkipSegment] = []
    intro_offset_ms = 0
    total_skipped_sec = 0.0
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

        start_ms = int(round(start_s * 1000))
        end_ms = int(round(end_s * 1000))
        segments.append(
            SkipSegment(
                category=str(item.get("category") or "music_offtopic"),
                startMs=start_ms,
                endMs=end_ms,
            )
        )
        total_skipped_sec += end_s - start_s
        # Non-music intro starting near 0:00 shifts studio lyrics forward by end_ms
        if start_s <= 2.0 and end_ms > intro_offset_ms:
            intro_offset_ms = end_ms

    effective_dur = int(round(max(0.0, inferred_vid_dur - total_skipped_sec)))
    if effective_dur <= 0:
        effective_dur = video_duration_sec

    return intro_offset_ms, effective_dur, segments
