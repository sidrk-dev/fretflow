from __future__ import annotations

import asyncio
import json
import re
import threading
from typing import Optional

from ytmusicapi import YTMusic

from .schemas import YOUTUBE_ID_RE, SearchResultItem

_tls = threading.local()

NOISE_BRACKET_PATTERNS = [
    r"\(\s*official\s+(?:hd\s+)?(?:remaster(?:ed)?\s+)?(?:music\s+|lyric\s+|audio\s+)?video\s*\)",
    r"\[\s*official\s+(?:hd\s+)?(?:remaster(?:ed)?\s+)?(?:music\s+|lyric\s+|audio\s+)?video\s*\]",
    r"\(\s*official\s+audio\s*\)",
    r"\[\s*official\s+audio\s*\]",
    r"\(\s*lyrics?\s*(?:video)?\s*\)",
    r"\[\s*lyrics?\s*(?:video)?\s*\]",
    r"\(\s*(?:\d{4}\s+)?(?:hd\s+)?remaster(?:ed)?(?:\s+\d{4})?\s*\)",
    r"\[\s*(?:\d{4}\s+)?(?:hd\s+)?remaster(?:ed)?(?:\s+\d{4})?\s*\]",
    r"\[\s*4k\s*[^\]]*\]",
    r"\(\s*visualizer\s*\)",
]

TRAILING_EDITION_RE = re.compile(
    r"\s+[-–—]\s*(?:\d{4}\s+)?(?:remaster(?:ed)?(?:\s+\d{4})?|radio\s+edit|single\s+edit|album\s+version|acoustic(?:\s+version)?|unplugged|instrumental|stereo|mono|live(?:\s+at\b.*|\s+in\b.*|\s+from\b.*)?|[^-–—]*\bmix\b)\s*$",
    re.IGNORECASE,
)

YOUTUBE_URL_ID_RE = re.compile(
    r"(?:[?&]v=|youtu\.be/|(?:youtube\.com|music\.youtube\.com)/(?:embed|shorts|live|v)/)([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])"
)


def _get_ytm() -> YTMusic:
    ytm = getattr(_tls, "ytm", None)
    if ytm is None:
        ytm = YTMusic()
        _tls.ytm = ytm
    return ytm


def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def clean_track_metadata(
    raw_title: str, raw_artist: str = "", trusted_artist: bool = False
) -> tuple[str, str]:
    """Clean YouTube video title/channel into clean (title, artist) without swapping edition tags."""
    title = raw_title.strip()
    artist = raw_artist.strip()

    if re.search(r"\s*-\s*Topic$", artist, re.IGNORECASE):
        trusted_artist = True
    artist = re.sub(r"\s*-\s*Topic$", "", artist, flags=re.IGNORECASE)
    artist = re.sub(r"VEVO$", "", artist, flags=re.IGNORECASE).strip()

    for pat in NOISE_BRACKET_PATTERNS:
        title = re.sub(pat, "", title, flags=re.IGNORECASE).strip()

    # Strip unparenthesized trailing "Official (Music|Lyric) Video/Audio"
    title = re.sub(
        r"\s+\b(?:official\s+(?:music\s+|lyric\s+)?(?:video|audio))\b\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()

    # Strip bracketed or trailing feat./ft./featuring credits
    title = re.sub(
        r"\s*[\(\[]\s*(?:feat(?:uring)?\.?|ft\.?)\s+[^\)\]]+[\)\]]",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()
    title = re.sub(
        r"\s+\b(?:feat(?:uring)?\.?|ft\.?)\s+.+$",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()

    # Strip trailing hyphenated edition suffixes BEFORE attempting Artist - Title split
    title = TRAILING_EDITION_RE.sub("", title).strip()

    # Split "Artist - Track" or "Track - Artist" across ASCII hyphen, en-dash, or em-dash
    dash_parts = re.split(r"\s+[-–—]\s+", title, maxsplit=1)
    if len(dash_parts) == 2:
        left, right = dash_parts[0].strip(), dash_parts[1].strip()
        left_norm, right_norm, artist_norm = _alnum(left), _alnum(right), _alnum(artist)

        if artist_norm and left_norm and (left_norm in artist_norm or artist_norm in left_norm):
            # "Guns N' Roses - Knockin' On Heaven's Door" with channel "GunsNRoses"
            if len(left) >= len(artist):
                artist = left
            title = right
        elif artist_norm and right_norm and (right_norm in artist_norm or artist_norm in right_norm):
            # Reversed upload: "Knockin' On Heaven's Door - Guns N' Roses"
            if len(right) >= len(artist):
                artist = right
            title = left
        elif not trusted_artist and not artist_norm and len(left) < 42:
            artist = left
            title = right
        elif (
            not trusted_artist
            and artist_norm
            and len(left) < 40
            and not re.search(
                r"\b(remaster|live|version|edit|acoustic|unplugged|instrumental|mix|part|pt|ost|soundtrack|overture|intro)\b",
                right,
                re.I,
            )
            and ":" not in left
        ):
            # Generic lyric channel like "7clouds" uploading "Artist - Song" (Wait: check if right isn't a known band suffix)
            artist = left
            title = right

    # Strip wrapping quotes & collapse repeated whitespace
    title = title.strip(" -–—|'\"“”‘’")
    title = re.sub(r"\s{2,}", " ", title).strip()
    artist = re.sub(r"\s{2,}", " ", artist).strip()
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
            if not vid or not YOUTUBE_ID_RE.fullmatch(vid) or vid in seen_ids:
                continue
            seen_ids.add(vid)

            title = entry.get("title") or ""
            artists = entry.get("artists") or []
            artist_name = (
                artists[0].get("name", "")
                if artists and artists[0].get("name")
                else ""
            )
            album_obj = entry.get("album")
            album_name = album_obj.get("name", "") if isinstance(album_obj, dict) else ""

            dur_sec = int(entry.get("duration_seconds") or 0)
            dur_txt = entry.get("duration") or _format_duration(dur_sec)
            if not dur_sec and dur_txt:
                dur_sec = _parse_duration_str(dur_txt)

            thumbs = entry.get("thumbnails") or []
            thumb_url = (
                thumbs[-1].get("url", "")
                if thumbs
                else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
            )

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
        "--flat-playlist",
        "--dump-json",
        "--no-warnings",
        "--",
        f"ytsearch{limit}:{query}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15.0)
    except BaseException:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        return []

    results: list[SearchResultItem] = []
    for line in stdout.decode("utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        vid = obj.get("id")
        if not isinstance(vid, str) or not YOUTUBE_ID_RE.fullmatch(vid):
            continue
        raw_title = obj.get("title") or ""
        channel = obj.get("channel") or obj.get("uploader") or ""
        clean_t, clean_a = clean_track_metadata(raw_title, channel)
        dur_sec = int(round(float(obj.get("duration") or 0)))
        rtype = (
            "live"
            if re.search(r"\b(live|acoustic|cover|unplugged)\b", raw_title, re.I)
            else "video"
        )
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

    # 1. Explicit YouTube URL (watch?v=, youtu.be/, /shorts/, /live/, /embed/)
    yt_match = YOUTUBE_URL_ID_RE.search(q)
    if yt_match:
        meta = await resolve_video_metadata(yt_match.group(1))
        return [meta] if meta else []

    # 2. Bare 11-char ID candidate (skip purely alphabetic words like "Soundgarden"!)
    if YOUTUBE_ID_RE.fullmatch(q) and not q.isalpha():
        meta = await resolve_video_metadata(q)
        if meta:
            return [meta]

    ytm_task = asyncio.to_thread(_search_ytmusic_sync, q, 8)
    ytdlp_task = _search_ytdlp_videos(q, 6)
    ytm_items, ytdlp_items = await asyncio.gather(
        ytm_task, ytdlp_task, return_exceptions=True
    )

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
    if not YOUTUBE_ID_RE.fullmatch(video_id):
        return None

    proc = await asyncio.create_subprocess_exec(
        "yt-dlp",
        "--dump-single-json",
        "--no-playlist",
        "--skip-download",
        "--no-warnings",
        "--",
        f"https://www.youtube.com/watch?v={video_id}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15.0)
    except BaseException:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        return None

    if proc.returncode != 0 or not stdout:
        return None
    try:
        obj = json.loads(stdout.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None

    track = str(obj.get("track") or "").strip()
    artist = str(obj.get("artist") or "").strip()
    album = str(obj.get("album") or "").strip()
    raw_title = str(obj.get("title") or "").strip()
    channel = str(obj.get("channel") or obj.get("uploader") or "").strip()

    if track and artist:
        c_title, c_artist = clean_track_metadata(track, artist, trusted_artist=True)
    else:
        c_title, c_artist = clean_track_metadata(raw_title, artist or channel)

    dur_sec = int(round(float(obj.get("duration") or 0)))
    return SearchResultItem(
        videoId=video_id,
        title=c_title or track or raw_title,
        artist=c_artist or artist or channel,
        album=album,
        durationSec=min(dur_sec, 3600),
        durationText=_format_duration(dur_sec),
        thumbnailUrl=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        resultType="studio" if channel.endswith("- Topic") else "video",
    )
