from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from typing import Optional

import httpx
import syncedlyrics
import yaml

from .schemas import LyricLine, LyricsPayload, LyricWord, SongSection

USER_AGENT = "FretFlow/0.1.0 (https://github.com/fretflow/guitar-karaoke)"
LRCLIB_BASE = "https://lrclib.net/api"
BETTERLYRICS_URL = "https://lyrics-api.boidu.dev/getLyrics"

LRC_LINE_RE = re.compile(r"^\[(\d{1,3}):(\d{2}(?:\.\d{1,3})?)\](.*)$")
ELRC_WORD_RE = re.compile(r"<(\d{1,3}):(\d{2}(?:\.\d{1,3})?)>([^<]*)")

PART_RENAME = {
    "Verse": "Verse",
    "Chorus": "Chorus",
    "PreChorus": "Pre-Chorus",
    "Bridge": "Bridge",
    "Intro": "Intro",
    "Outro": "Outro",
    "Instrumental": "Instrumental",
    "Hook": "Hook",
    "Refrain": "Refrain",
}


def parse_time_to_ms(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    parts = s.split(":")
    try:
        if len(parts) == 1:
            return int(round(float(parts[0]) * 1000))
        if len(parts) == 2:
            return int(round((int(parts[0]) * 60 + float(parts[1])) * 1000))
        if len(parts) == 3:
            return int(round((int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])) * 1000))
    except ValueError:
        return None
    return None


def _local_tag(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _get_attr_suffix(elem: ET.Element, suffix: str) -> Optional[str]:
    for k, v in elem.attrib.items():
        if k == suffix or k.endswith(f"}}{suffix}") or k.endswith(f":{suffix}"):
            return v
    return None


def parse_betterlyrics_ttml(ttml_xml: str) -> Optional[LyricsPayload]:
    """Parse Apple-Music-style TTML XML into structured SongSections with word timings."""
    try:
        root = ET.fromstring(ttml_xml)
    except ET.ParseError:
        return None

    body = None
    for child in root.iter():
        if _local_tag(child.tag) == "body":
            body = child
            break
    if body is None:
        return None

    sections: list[SongSection] = []
    part_counts: dict[str, int] = {}
    has_any_words = False
    line_counter = 0
    plain_lines: list[str] = []

    divs = [c for c in body if _local_tag(c.tag) == "div"]
    if not divs:
        divs = [body]

    for sec_idx, div in enumerate(divs):
        raw_part = _get_attr_suffix(div, "songPart") or "Verse"
        base_name = PART_RENAME.get(raw_part, raw_part)
        part_counts[base_name] = part_counts.get(base_name, 0) + 1
        sec_name = (
            f"{base_name} {part_counts[base_name]}"
            if base_name in ("Verse",)
            else (base_name if part_counts[base_name] == 1 else f"{base_name} {part_counts[base_name]}")
        )

        sec_lines: list[LyricLine] = []
        for p in div:
            if _local_tag(p.tag) != "p":
                continue
            p_start = parse_time_to_ms(p.attrib.get("begin"))
            p_end = parse_time_to_ms(p.attrib.get("end"))

            words: list[LyricWord] = []
            spans = [sp for sp in p if _local_tag(sp.tag) == "span"]

            for sp in spans:
                # Skip background translation/romanization metadata spans if marked
                role = _get_attr_suffix(sp, "role") or ""
                if role in ("x-translation", "x-roman"):
                    continue
                w_start = parse_time_to_ms(sp.attrib.get("begin"))
                w_end = parse_time_to_ms(sp.attrib.get("end"))
                txt = (sp.text or "") + (sp.tail or "")
                # Handle nested spans (e.g., background vocals wrapper <span ttm:role="x-bg">)
                if not sp.text and len(sp) > 0:
                    for sub in sp:
                        if _local_tag(sub.tag) == "span":
                            sw_s = parse_time_to_ms(sub.attrib.get("begin"))
                            sw_e = parse_time_to_ms(sub.attrib.get("end"))
                            stxt = (sub.text or "") + (sub.tail or "")
                            if stxt.strip() and sw_s is not None:
                                words.append(
                                    LyricWord(
                                        text=stxt,
                                        startMs=sw_s,
                                        endMs=sw_e if sw_e is not None else sw_s + 300,
                                    )
                                )
                    if sp.tail and words:
                        words[-1].text += sp.tail
                    continue

                if txt and w_start is not None:
                    words.append(
                        LyricWord(
                            text=txt,
                            startMs=w_start,
                            endMs=w_end if w_end is not None else w_start + 300,
                        )
                    )

            if words:
                has_any_words = True
                line_text = "".join(w.text for w in words).strip()
                l_start = p_start if p_start is not None else words[0].startMs
                l_end = p_end if p_end is not None else words[-1].endMs
            else:
                line_text = "".join(p.itertext()).strip()
                if not line_text or p_start is None:
                    continue
                l_start = p_start
                l_end = p_end if p_end is not None else l_start + 3500

            if not line_text:
                continue

            line_counter += 1
            plain_lines.append(line_text)
            sec_lines.append(
                LyricLine(
                    id=f"line-{line_counter}",
                    startMs=l_start,
                    endMs=max(l_start + 200, l_end),
                    text=line_text,
                    words=words,
                )
            )

        if sec_lines:
            sections.append(
                SongSection(
                    id=f"sec-{sec_idx + 1}",
                    name=sec_name,
                    kind="lyrics",
                    startMs=sec_lines[0].startMs,
                    endMs=sec_lines[-1].endMs,
                    lines=sec_lines,
                )
            )

    if not sections:
        return None

    return LyricsPayload(
        source="betterlyrics_ttml",
        hasWordSync=has_any_words,
        hasLineSync=True,
        plainText="\n".join(plain_lines),
        sections=sections,
    )


def parse_lrclib_yaml(yaml_text: str) -> Optional[LyricsPayload]:
    """Parse LRCLIB v1.0 `lyricsfile` YAML containing millisecond line & word timings."""
    try:
        doc = yaml.safe_load(yaml_text)
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    raw_lines = doc.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        return None

    parsed_lines: list[LyricLine] = []
    has_words = False
    plain_lines: list[str] = []

    for idx, item in enumerate(raw_lines):
        if not isinstance(item, dict):
            continue
        txt = str(item.get("text") or "").strip()
        if not txt:
            continue
        start_ms = item.get("start_ms")
        if start_ms is None:
            continue
        start_ms = int(start_ms)
        end_ms = int(item.get("end_ms") or (start_ms + 3500))

        words: list[LyricWord] = []
        raw_words = item.get("words")
        if isinstance(raw_words, list) and raw_words:
            for w_idx, w in enumerate(raw_words):
                if not isinstance(w, dict):
                    continue
                w_txt = str(w.get("text") or "")
                w_start = w.get("start_ms")
                if not w_txt or w_start is None:
                    continue
                w_start = int(w_start)
                if w.get("end_ms") is not None:
                    w_end = int(w["end_ms"])
                elif w_idx + 1 < len(raw_words) and raw_words[w_idx + 1].get("start_ms") is not None:
                    w_end = int(raw_words[w_idx + 1]["start_ms"])
                else:
                    w_end = max(w_start + 250, end_ms)
                words.append(LyricWord(text=w_txt, startMs=w_start, endMs=max(w_start + 80, w_end)))
            if words:
                has_words = True

        plain_lines.append(txt)
        parsed_lines.append(
            LyricLine(
                id=f"line-{idx + 1}",
                startMs=start_ms,
                endMs=max(start_ms + 250, end_ms),
                text=txt,
                words=words,
            )
        )

    if not parsed_lines:
        return None

    # Fill endMs tightly from next line startMs when missing/overlapping
    for i in range(len(parsed_lines) - 1):
        if parsed_lines[i].endMs > parsed_lines[i + 1].startMs:
            parsed_lines[i].endMs = parsed_lines[i + 1].startMs

    sections = _group_lines_into_sections(parsed_lines)
    return LyricsPayload(
        source="lrclib_word" if has_words else "lrclib_line",
        hasWordSync=has_words,
        hasLineSync=True,
        plainText="\n".join(plain_lines),
        sections=sections,
    )


def parse_lrc_string(
    lrc_text: str, source_prefix: str = "lrclib"
) -> Optional[LyricsPayload]:
    """Parse standard `[mm:ss.xx]` or Enhanced `<mm:ss.xx>` LRC text into SongSections."""
    if not lrc_text or not lrc_text.strip():
        return None

    raw_entries: list[tuple[int, str, bool]] = []
    pending_blank = False

    for raw_line in lrc_text.splitlines():
        s = raw_line.strip()
        if not s:
            pending_blank = True
            continue
        m = LRC_LINE_RE.match(s)
        if not m:
            continue
        mins, secs, content = int(m.group(1)), float(m.group(2)), m.group(3).strip()
        start_ms = int(round((mins * 60 + secs) * 1000))
        if not content:
            pending_blank = True
            continue
        raw_entries.append((start_ms, content, pending_blank))
        pending_blank = False

    if not raw_entries:
        return None

    raw_entries.sort(key=lambda x: x[0])
    lines_with_breaks: list[tuple[LyricLine, bool]] = []
    has_word_sync = False
    plain_lines: list[str] = []

    for i, (start_ms, content, had_break) in enumerate(raw_entries):
        next_ms = raw_entries[i + 1][0] if i + 1 < len(raw_entries) else start_ms + 4500
        end_ms = max(start_ms + 300, min(next_ms, start_ms + 8000))

        words: list[LyricWord] = []
        word_matches = list(ELRC_WORD_RE.finditer(content))
        if word_matches:
            for wm_idx, wm in enumerate(word_matches):
                w_ms = int(round((int(wm.group(1)) * 60 + float(wm.group(2))) * 1000))
                w_txt = wm.group(3)
                if not w_txt:
                    continue
                if wm_idx + 1 < len(word_matches):
                    nw = word_matches[wm_idx + 1]
                    w_end = int(round((int(nw.group(1)) * 60 + float(nw.group(2))) * 1000))
                else:
                    w_end = end_ms
                words.append(LyricWord(text=w_txt, startMs=w_ms, endMs=max(w_ms + 80, w_end)))
            clean_text = ELRC_WORD_RE.sub(r"\3", content).strip()
            if words:
                has_word_sync = True
        else:
            clean_text = re.sub(r"<\d{1,3}:\d{2}(?:\.\d{1,3})?>", "", content).strip()

        if not clean_text:
            continue
        plain_lines.append(clean_text)
        lines_with_breaks.append(
            (
                LyricLine(
                    id=f"line-{i + 1}",
                    startMs=start_ms,
                    endMs=end_ms,
                    text=clean_text,
                    words=words,
                ),
                had_break,
            )
        )

    if not lines_with_breaks:
        return None

    sections: list[SongSection] = []
    cur_lines: list[LyricLine] = []
    sec_num = 1

    for idx, (ln, had_break) in enumerate(lines_with_breaks):
        prev_end = cur_lines[-1].endMs if cur_lines else ln.startMs
        big_gap = (ln.startMs - prev_end) >= 5500
        if cur_lines and (had_break or big_gap or len(cur_lines) >= 8):
            sections.append(
                SongSection(
                    id=f"sec-{sec_num}",
                    name=f"Section {sec_num}",
                    kind="lyrics",
                    startMs=cur_lines[0].startMs,
                    endMs=cur_lines[-1].endMs,
                    lines=cur_lines,
                )
            )
            sec_num += 1
            cur_lines = []
        cur_lines.append(ln)

    if cur_lines:
        sections.append(
            SongSection(
                id=f"sec-{sec_num}",
                name=f"Section {sec_num}",
                kind="lyrics",
                startMs=cur_lines[0].startMs,
                endMs=cur_lines[-1].endMs,
                lines=cur_lines,
            )
        )

    src_name = f"{source_prefix}_{'word' if has_word_sync else 'line'}"
    return LyricsPayload(
        source=src_name,  # type: ignore[arg-type]
        hasWordSync=has_word_sync,
        hasLineSync=True,
        plainText="\n".join(plain_lines),
        sections=sections,
    )


def _group_lines_into_sections(lines: list[LyricLine]) -> list[SongSection]:
    sections: list[SongSection] = []
    cur: list[LyricLine] = []
    sec_num = 1
    for ln in lines:
        if cur and ((ln.startMs - cur[-1].endMs) >= 5000 or len(cur) >= 6):
            sections.append(
                SongSection(
                    id=f"sec-{sec_num}",
                    name=f"Verse / Part {sec_num}",
                    kind="lyrics",
                    startMs=cur[0].startMs,
                    endMs=cur[-1].endMs,
                    lines=cur,
                )
            )
            sec_num += 1
            cur = []
        cur.append(ln)
    if cur:
        sections.append(
            SongSection(
                id=f"sec-{sec_num}",
                name=f"Verse / Part {sec_num}",
                kind="lyrics",
                startMs=cur[0].startMs,
                endMs=cur[-1].endMs,
                lines=cur,
            )
        )
    return sections


async def _fetch_betterlyrics(
    client: httpx.AsyncClient, title: str, artist: str, album: str = "", duration_sec: int = 0
) -> Optional[LyricsPayload]:
    params: dict[str, str | int] = {"s": title, "a": artist}
    if album:
        params["al"] = album
    if duration_sec > 0:
        params["d"] = duration_sec
    try:
        resp = await client.get(BETTERLYRICS_URL, params=params, timeout=5.5)
        if resp.status_code != 200:
            return None
        data = resp.json()
        ttml = data.get("ttml")
        if isinstance(ttml, str) and "<tt" in ttml:
            return parse_betterlyrics_ttml(ttml)
    except Exception:
        return None
    return None


async def _fetch_lrclib(
    client: httpx.AsyncClient, title: str, artist: str, album: str = "", duration_sec: int = 0
) -> Optional[LyricsPayload]:
    headers = {"User-Agent": USER_AGENT}
    candidates: list[dict] = []

    if title and artist:
        get_params: dict[str, str | int] = {"track_name": title, "artist_name": artist}
        if album:
            get_params["album_name"] = album
        if 1 <= duration_sec <= 3600:
            get_params["duration"] = duration_sec
        try:
            r = await client.get(f"{LRCLIB_BASE}/get", params=get_params, headers=headers, timeout=5.0)
            if r.status_code == 200:
                candidates.append(r.json())
        except Exception:
            pass

    if not candidates:
        search_params = {"track_name": title, "artist_name": artist} if artist else {"q": title}
        try:
            r = await client.get(f"{LRCLIB_BASE}/search", params=search_params, headers=headers, timeout=5.5)
            if r.status_code == 200 and isinstance(r.json(), list):
                candidates.extend(r.json())
        except Exception:
            pass

        if not candidates and title:
            try:
                r = await client.get(
                    f"{LRCLIB_BASE}/search",
                    params={"q": f"{artist} {title}".strip()},
                    headers=headers,
                    timeout=5.5,
                )
                if r.status_code == 200 and isinstance(r.json(), list):
                    candidates.extend(r.json())
            except Exception:
                pass

    if not candidates:
        return None

    def _score_record(rec: dict) -> tuple[int, int, float]:
        has_word = 1 if rec.get("hasWordSync") else 0
        has_sync = 1 if rec.get("syncedLyrics") else 0
        rec_dur = float(rec.get("duration") or 0)
        dur_diff = abs(rec_dur - duration_sec) if (duration_sec > 0 and rec_dur > 0) else 30.0
        # Penalize large duration mismatches (>12s) unless it's the only synced record
        dur_bonus = -dur_diff if dur_diff <= 15 else -100.0 - dur_diff
        return (has_word, has_sync, dur_bonus)

    candidates.sort(key=_score_record, reverse=True)

    for rec in candidates:
        if rec.get("hasWordSync") and rec.get("lyricsfile"):
            parsed = parse_lrclib_yaml(str(rec["lyricsfile"]))
            if parsed:
                return parsed
        if rec.get("syncedLyrics"):
            parsed = parse_lrc_string(str(rec["syncedLyrics"]), source_prefix="lrclib")
            if parsed:
                return parsed

    # Plain lyrics fallback from LRCLIB
    for rec in candidates:
        plain = str(rec.get("plainLyrics") or "").strip()
        if plain:
            return _build_plain_payload(plain)

    return None


def _build_plain_payload(plain_text: str) -> LyricsPayload:
    lines: list[LyricLine] = []
    for idx, raw in enumerate(plain_text.splitlines()):
        txt = raw.strip()
        if not txt:
            continue
        lines.append(
            LyricLine(
                id=f"line-{idx + 1}",
                startMs=idx * 4000,
                endMs=(idx + 1) * 4000,
                text=txt,
            )
        )
    return LyricsPayload(
        source="plain",
        hasWordSync=False,
        hasLineSync=False,
        plainText=plain_text,
        sections=[
            SongSection(
                id="sec-1",
                name="Lyrics (Unsynced)",
                kind="lyrics",
                startMs=0,
                endMs=max(4000, len(lines) * 4000),
                lines=lines,
            )
        ]
        if lines
        else [],
    )


def _fetch_syncedlyrics_sync(query: str) -> Optional[LyricsPayload]:
    for enhanced in (True, False):
        try:
            lrc = syncedlyrics.search(
                query,
                enhanced=enhanced,
                synced_only=True,
                providers=["NetEase", "Musixmatch", "Megalobiz"],
            )
            if lrc:
                parsed = parse_lrc_string(lrc, source_prefix="syncedlyrics")
                if parsed:
                    return parsed
        except Exception:
            continue
    return None


async def fetch_best_lyrics(
    title: str, artist: str, album: str = "", effective_duration_sec: int = 0
) -> LyricsPayload:
    """
    Execute the multi-source synced lyrics waterfall:
    1. Parallel BetterLyrics (TTML word + Verse/Chorus sections) & LRCLIB (word YAML + LRC)
    2. Fallback to `syncedlyrics` (NetEase / Musixmatch / Megalobiz)
    """
    clean_title = title.strip()
    clean_artist = artist.split(",")[0].strip() if artist else ""

    async with httpx.AsyncClient(follow_redirects=True) as client:
        bl_task = _fetch_betterlyrics(client, clean_title, clean_artist, album, effective_duration_sec)
        lrc_task = _fetch_lrclib(client, clean_title, clean_artist, album, effective_duration_sec)
        bl_res, lrc_res = await asyncio.gather(bl_task, lrc_task, return_exceptions=True)

    bl_payload = bl_res if isinstance(bl_res, LyricsPayload) else None
    lrc_payload = lrc_res if isinstance(lrc_res, LyricsPayload) else None

    # Prefer BetterLyrics TTML when it has word sync (includes Verse/Chorus headers!)
    if bl_payload and bl_payload.hasWordSync:
        return bl_payload
    if lrc_payload and lrc_payload.hasWordSync:
        return lrc_payload
    if bl_payload and bl_payload.hasLineSync:
        return bl_payload
    if lrc_payload and lrc_payload.hasLineSync:
        return lrc_payload

    # Secondary multi-provider fallback via syncedlyrics
    query_str = f"{clean_artist} {clean_title}".strip()
    if query_str:
        sl_payload = await asyncio.to_thread(_fetch_syncedlyrics_sync, query_str)
        if sl_payload:
            return sl_payload

    if lrc_payload:
        return lrc_payload

    return LyricsPayload(source="none", hasWordSync=False, hasLineSync=False)
