from __future__ import annotations

import asyncio
import json
import re
from typing import Optional

from ytmusicapi import YTMusic

from .schemas import SearchResultItem

_ytm: Optional[YTMusic] = None

NOISE_PATTERNS = [
    r"\(\s*official\s+(music\s+)?video\s*\)",
    r"\[\s*official\s+(music\s+)?video\s*\]",
    r"\(\s*official\s+audio\s*\)",
    r"\[\s*official\s+audio\s*\]",
    r"\(\s*official\s+lyric\s+video\s*\)",
    r"\(\s*lyrics?\s*\)",
    r"\[\s*lyrics?\s*\]",
    r"\(\s*hd\s*(remaster(ed)?)?\s*\)",
    r"\[\s*hd\s*(remaster(ed)?)?\s*\]",
    r"\(\s*\d{4}\s*remaster(ed)?\s*\)",
    r"\[\s*4k\s*.*?\]",
    r"\(\s*visualizer\s*\)",
]


def _get_ytm() -> YTMusic:
    global _ytm
    if _ytm is None:
        _ytm = YTMusic()
    return _ytm


def clean_track_metadata(raw_title: str, raw_artist: str = "") -> tuple[str, str]:
    """Clean YouTube video title/channel into clean (title, artist) for lyrics lookup."""
    title = raw_title.strip()
    artist = raw_artist.strip()

    artist = re.sub(r"\s*-\s*Topic$", "", artist, flags=re.IGNORECASE)
    artist = re.sub(r"VEVO$", "", artist, flags=re.IGNORECASE).strip()

    for pat in NOISE_PATTERNS:
        title = re.sub(pat, "", title, flags=re.IGNORECASE).strip()

    # Split "Artist - Track" if title embeds artist name
    if " - " in title:
        left, right = title.split(" - ", 1)
        if not artist or left.lower() in artist.lower() or artist.lower() in left.lower():
            artist = left.strip()
            title = right.strip()
        elif len(left) < 40 and not re.search(r"remaster|live|version", right, re.I):
            artist = left.strip()
            title = right.strip()

    # Strip feat. suffixes from title for higher LRCLIB/BetterLyrics hit rate
    title = re.sub(r"\s*[\(\[]\s*(feat\.?|ft\.?)\s+[^\)\]]+[\)\]]", "", title, flags=re.I).strip()
    title = title.strip(" -–—|")
    return title, artist


def _format_duration(seconds: int) -> str:
    if seconds <= 0:
        return ""
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def _parse_duration_str(dur_str: str) -> int:
    if not dur_str:
        return 0
    parts = [int(p) for p in dur_str.split(":") if p.isdigit()]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0


def _search_ytmusic_sync(query: str, limit: int = 8) -> list[SearchResultItem]:
    ytm = _get_ytm()
    items: list[SearchResultItem] = []
    seen_ids: set[str] = set()

    for flt, rtype in (("songs", "studio"), ("videos", "video")):
        try:
            raw_list = ytm.search(query, filter=flt, limit=limit)
        except Exception:
            continue

        for entry in raw_list:
            vid = entry.get("videoId")
            if not vid or vid in seen_ids:
                continue
            seen_ids.add(vid)

            title = entry.get("title") or ""
            artists = entry.get("artists") or []
            artist_name = ", ".join(a.get("name", "") for a in artists if a.get("name"))
            album_obj = entry.get("album")
            album_name = album_obj.get("name", "") if isinstance(album_obj, dict) else ""

            dur_sec = int(entry.get("duration_seconds") or 0)
            dur_txt = entry.get("duration") or _format_duration(dur_sec)
            if not dur_sec and dur_txt:
                dur_sec = _parse_duration_str(dur_txt)

            thumbs = entry.get("thumbnails") or []
            thumb_url = thumbs[-1].get("url", "") if thumbs else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"

            actual_type = rtype
            if re.search(r"\b(live|acoustic|concert|unplugged|cover)\b", title, re.I):
                actual_type = "live"

            items.append(
                SearchResultItem(
                    videoId=vid,
                    title=title,
                    artist=artist_name,
                    album=album_name,
                    durationSec=dur_sec,
                    durationText=dur_txt or _format_duration(dur_sec),
                    thumbnailUrl=thumb_url,
                    resultType=actual_type,  # type: ignore[arg-type]
                    viewsText=str(entry.get("views") or ""),
                )
            )
    return items


async def _search_ytdlp_videos(query: str, limit: int = 6) -> list[SearchResultItem]:
    proc = await asyncio.create_subprocess_exec(
        "yt-dlp",
        f"ytsearch{limit}:{query}",
        "--flat-playlist",
        "--dump-json",
        "--no-warnings",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    results: list[SearchResultItem] = []
    for line in stdout.decode("utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        vid = obj.get("id")
        if not vid or len(vid) != 11:
            continue
        raw_title = obj.get("title") or ""
        channel = obj.get("channel") or obj.get("uploader") or ""
        clean_t, clean_a = clean_track_metadata(raw_title, channel)
        dur_sec = int(round(float(obj.get("duration") or 0)))
        rtype = "live" if re.search(r"\b(live|acoustic|cover|unplugged)\b", raw_title, re.I) else "video"
        view_cnt = obj.get("view_count")
        views_txt = f"{view_cnt:,} views" if isinstance(view_cnt, int) else ""

        results.append(
            SearchResultItem(
                videoId=vid,
                title=clean_t or raw_title,
                artist=clean_a or channel,
                album="",
                durationSec=dur_sec,
                durationText=_format_duration(dur_sec),
                thumbnailUrl=f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                resultType=rtype,  # type: ignore[arg-type]
                viewsText=views_txt,
            )
        )
    return results


async def search_songs_and_videos(query: str) -> list[SearchResultItem]:
    q = query.strip()
    if not q:
        return []

    # Direct YouTube URL / Video ID support
    yt_match = re.search(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})", q)
    if yt_match or re.fullmatch(r"[A-Za-z0-9_-]{11}", q):
        vid = yt_match.group(1) if yt_match else q
        meta = await resolve_video_metadata(vid)
        return [meta] if meta else []

    ytm_task = asyncio.to_thread(_search_ytmusic_sync, q, 8)
    ytdlp_task = _search_ytdlp_videos(q, 6)
    ytm_items, ytdlp_items = await asyncio.gather(ytm_task, ytdlp_task, return_exceptions=True)

    merged: list[SearchResultItem] = []
    seen: set[str] = set()

    for group in (ytm_items, ytdlp_items):
        if isinstance(group, list):
            for item in group:
                if item.videoId not in seen:
                    seen.add(item.videoId)
                    merged.append(item)

    return merged[:16]


async def resolve_video_metadata(video_id: str) -> Optional[SearchResultItem]:
    proc = await asyncio.create_subprocess_exec(
        "yt-dlp",
        f"https://www.youtube.com/watch?v={video_id}",
        "--dump-single-json",
        "--no-playlist",
        "--skip-download",
        "--no-warnings",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    if not stdout:
        return None
    try:
        obj = json.loads(stdout.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return None

    track = obj.get("track") or ""
    artist = obj.get("artist") or ""
    album = obj.get("album") or ""
    raw_title = obj.get("title") or ""
    channel = obj.get("channel") or obj.get("uploader") or ""

    if not track or not artist:
        c_title, c_artist = clean_track_metadata(raw_title, channel)
        track = track or c_title
        artist = artist or c_artist

    dur_sec = int(round(float(obj.get("duration") or 0)))
    return SearchResultItem(
        videoId=video_id,
        title=track or raw_title,
        artist=artist or channel,
        album=album,
        durationSec=dur_sec,
        durationText=_format_duration(dur_sec),
        thumbnailUrl=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        resultType="studio" if channel.endswith("- Topic") else "video",
    )
