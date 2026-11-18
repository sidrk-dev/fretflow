from __future__ import annotations

from typing import Optional

from .schemas import (
    ChordAnchor,
    ChordEvent,
    ChordsPayload,
    InstrumentalBarChord,
    LyricLine,
    LyricsPayload,
    LyricWord,
    SkipSegment,
    SongSection,
)
from .sponsorblock import merge_skip_segments

INSTRUMENTAL_GAP_THRESHOLD_MS = 4500


def map_studio_to_video_ms(
    studio_ms: int,
    auto_offset_ms: int,
    manual_offset_ms: int,
    skip_segments: Optional[list[SkipSegment]] = None,
    video_duration_ms: int = 0,
) -> int:
    """
    Map a studio-master timestamp to YouTube video timestamp:
    - Applies intro offset + mid-video non-music dialogue skits (piecewise cumulative SponsorBlock shift)
    - Excludes outro skits near the end of the video
    - Applies guitarist manual_offset_ms
    """
    if not skip_segments:
        return studio_ms + auto_offset_ms + manual_offset_ms

    merged = merge_skip_segments(skip_segments)
    pos = studio_ms
    for seg in merged:
        # Ignore trailing outro skits (starting in the final 15% of a known video duration and > 60s)
        if video_duration_ms > 60_000 and seg.startMs > video_duration_ms * 0.85 and seg.endMs >= video_duration_ms - 5000:
            continue
        if pos >= seg.startMs - 500:
            pos += seg.endMs - seg.startMs
    return pos + manual_offset_ms


def _build_instrumental_section(
    sec_id: str,
    name: str,
    start_ms: int,
    end_ms: int,
    events: list[ChordEvent],
    bpm: float,
) -> Optional[SongSection]:
    beat_dur_ms = max(250.0, 60_000.0 / max(40.0, bpm))
    bars: list[InstrumentalBarChord] = []
    for ev in events:
        if ev.endMs <= start_ms + 150 or ev.startMs >= end_ms - 150:
            continue
        s = max(start_ms, ev.startMs)
        e = min(end_ms, ev.endMs)
        if e - s < 250:
            continue
        beats = max(1, min(16, int(round((e - s) / beat_dur_ms))))
        bars.append(
            InstrumentalBarChord(
                harte=ev.harte,
                rootPc=ev.rootPc,
                quality=ev.quality,
                bassPc=ev.bassPc,
                display=ev.display,
                startMs=s,
                endMs=e,
                beats=beats,
            )
        )
    if not bars:
        return None
    return SongSection(
        id=sec_id,
        name=name,
        kind="instrumental",
        startMs=bars[0].startMs,
        endMs=bars[-1].endMs,
        instrumentalChords=bars,
    )


def _anchor_chords_to_line(
    line: LyricLine, events: list[ChordEvent], next_line_start_ms: Optional[int]
) -> list[ChordAnchor]:
    """Attach chord events occurring just before (pickup) or during a lyric line to words/characters."""
    pickup_start = max(0, line.startMs - 240)
    window_end = line.endMs
    if (
        next_line_start_ms is not None
        and (next_line_start_ms - line.endMs) < INSTRUMENTAL_GAP_THRESHOLD_MS
    ):
        window_end = max(line.endMs, min(next_line_start_ms - 240, line.endMs + 3200))

    overlapping = [
        ev
        for ev in events
        if ev.endMs > line.startMs + 80 and ev.startMs < window_end and ev.endMs > pickup_start
    ]
    if not overlapping:
        return []

    anchors: list[ChordAnchor] = []
    text_len = max(1, len(line.text))
    line_span = max(300, line.endMs - line.startMs)

    for idx, ev in enumerate(overlapping):
        eff_start = max(line.startMs, ev.startMs)
        word_idx: Optional[int] = None
        char_offset: Optional[int] = None

        if line.words:
            best_w = 0
            best_dist = 10**9
            for wi, w in enumerate(line.words):
                if w.startMs <= eff_start <= w.endMs:
                    best_w = wi
                    best_dist = 0
                    break
                dist = abs(w.startMs - eff_start)
                if dist < best_dist:
                    best_dist = dist
                    best_w = wi
            # Snap to the start of a visual word (don't attach mid-word on syllable #2 if syllable #1 didn't end with space)
            while best_w > 0 and not line.words[best_w - 1].text.endswith((" ", "\t", "-")):
                best_w -= 1
            if anchors and anchors[-1].wordIndex is not None:
                prev_w = anchors[-1].wordIndex
                if best_w < prev_w:
                    best_w = prev_w
                if best_w == prev_w and best_w + 1 < len(line.words):
                    # Advance to next whole-word boundary if available so rapid chords stay ordered left-to-right
                    cand = best_w + 1
                    while cand < len(line.words) and not line.words[cand - 1].text.endswith((" ", "\t", "-")):
                        cand += 1
                    if cand < len(line.words):
                        best_w = cand
            word_idx = best_w

        if ev.startMs <= line.startMs + 120 and idx == 0:
            char_offset = 0
        else:
            frac = min(1.0, max(0.0, (eff_start - line.startMs) / float(line_span)))
            raw_char = int(round(frac * (text_len - 1)))
            while raw_char > 0 and line.text[raw_char - 1] not in (" ", "\t", "-"):
                raw_char -= 1
            if anchors and anchors[-1].charOffset is not None and raw_char <= anchors[-1].charOffset + 3:
                raw_char = min(text_len, (anchors[-1].charOffset or 0) + 5)
            char_offset = raw_char

        if anchors and anchors[-1].display == ev.display:
            anchors[-1].endMs = ev.endMs
            continue

        anchors.append(
            ChordAnchor(
                harte=ev.harte,
                rootPc=ev.rootPc,
                quality=ev.quality,
                bassPc=ev.bassPc,
                display=ev.display,
                startMs=ev.startMs,
                endMs=ev.endMs,
                wordIndex=word_idx,
                charOffset=char_offset,
                confidence=ev.confidence,
            )
        )
    return anchors


def align_lyrics_and_chords(
    lyrics: Optional[LyricsPayload],
    chords: Optional[ChordsPayload],
    total_offset_ms: int = 0,
    song_duration_ms: int = 0,
    skip_segments: Optional[list[SkipSegment]] = None,
    auto_offset_ms: Optional[int] = None,
    manual_offset_ms: Optional[int] = None,
) -> list[SongSection]:
    """
    Produce a complete timeline of SongSections combining:
    - Piecewise SponsorBlock + manual offset shifted lyrics
    - Chords snapped onto whole-word boundaries (never splitting syllabic TTML words)
    - `[Intro]`, `[Instrumental / Solo]`, and `[Outro]` chord bars
    """
    bounded_dur_ms = max(0, min(int(song_duration_ms), 3_600_000))
    events = chords.events if chords else []
    bpm = chords.bpm if chords else 120.0

    if not lyrics or not lyrics.sections or lyrics.source == "none":
        if not events:
            return []
        end_ms = min(3_600_000, max(bounded_dur_ms, events[-1].endMs))
        chunk_ms = 24_000
        inst_sections: list[SongSection] = []
        idx = 1
        for s in range(0, end_ms, chunk_ms):
            sec = _build_instrumental_section(
                sec_id=f"inst-{idx}",
                name="Intro" if idx == 1 else f"Part {idx}",
                start_ms=s,
                end_ms=min(end_ms, s + chunk_ms),
                events=events,
                bpm=bpm,
            )
            if sec:
                inst_sections.append(sec)
                idx += 1
        return inst_sections

    eff_auto = auto_offset_ms if auto_offset_ms is not None else total_offset_ms
    eff_manual = manual_offset_ms if manual_offset_ms is not None else 0

    def _shift_ts(ms: int) -> int:
        if not lyrics.hasLineSync:
            return ms
        if skip_segments:
            return map_studio_to_video_ms(ms, eff_auto, eff_manual, skip_segments, bounded_dur_ms)
        return ms + total_offset_ms

    shifted_sections: list[SongSection] = []
    all_shifted_lines: list[LyricLine] = []

    for sec in lyrics.sections:
        s_lines: list[LyricLine] = []
        for ln in sec.lines:
            raw_l_start = _shift_ts(ln.startMs)
            raw_l_end = _shift_ts(ln.endMs)
            # If negative manual offset pushed the entire line before 0:00, skip piling onto 0ms
            if lyrics.hasLineSync and raw_l_end <= 0:
                continue

            l_start = max(0, raw_l_start)
            l_end = max(l_start + 180, raw_l_end)

            s_words: list[LyricWord] = []
            for w in ln.words:
                rw_s = _shift_ts(w.startMs)
                rw_e = _shift_ts(w.endMs)
                if rw_e <= 0:
                    s_words.append(LyricWord(text=w.text, startMs=0, endMs=0))
                else:
                    ws = max(0, rw_s)
                    s_words.append(LyricWord(text=w.text, startMs=ws, endMs=max(ws + 60, rw_e)))

            new_ln = LyricLine(
                id=ln.id,
                startMs=l_start,
                endMs=l_end,
                text=ln.text,
                words=s_words,
                chords=[],
            )
            s_lines.append(new_ln)
            all_shifted_lines.append(new_ln)

        if s_lines:
            shifted_sections.append(
                SongSection(
                    id=sec.id,
                    name=sec.name,
                    kind="lyrics",
                    startMs=s_lines[0].startMs,
                    endMs=s_lines[-1].endMs,
                    lines=s_lines,
                )
            )

    if not shifted_sections:
        return []

    if not events or not lyrics.hasLineSync:
        return shifted_sections

    for global_i, ln in enumerate(all_shifted_lines):
        next_start = (
            all_shifted_lines[global_i + 1].startMs
            if global_i + 1 < len(all_shifted_lines)
            else None
        )
        ln.chords = _anchor_chords_to_line(ln, events, next_start)

    output: list[SongSection] = []
    first_vocal_ms = shifted_sections[0].startMs
    if first_vocal_ms >= INSTRUMENTAL_GAP_THRESHOLD_MS:
        intro_sec = _build_instrumental_section(
            sec_id="inst-intro",
            name="Intro",
            start_ms=0,
            end_ms=first_vocal_ms,
            events=events,
            bpm=bpm,
        )
        if intro_sec:
            output.append(intro_sec)

    solo_count = 0
    for idx, sec in enumerate(shifted_sections):
        if idx > 0:
            prev_end = shifted_sections[idx - 1].endMs
            if sec.startMs - prev_end >= INSTRUMENTAL_GAP_THRESHOLD_MS + 1000:
                solo_count += 1
                interlude = _build_instrumental_section(
                    sec_id=f"inst-break-{solo_count}",
                    name="Instrumental / Solo"
                    if solo_count == 1
                    else f"Instrumental {solo_count}",
                    start_ms=prev_end,
                    end_ms=sec.startMs,
                    events=events,
                    bpm=bpm,
                )
                if interlude:
                    output.append(interlude)
        output.append(sec)

    last_vocal_end = shifted_sections[-1].endMs
    final_ms = min(3_600_000, max(bounded_dur_ms, events[-1].endMs))
    if final_ms - last_vocal_end >= INSTRUMENTAL_GAP_THRESHOLD_MS + 1500:
        outro_title = (
            "Instrumental Outro"
            if shifted_sections[-1].name.strip().lower().startswith("outro")
            else "Outro"
        )
        outro_sec = _build_instrumental_section(
            sec_id="inst-outro",
            name=outro_title,
            start_ms=last_vocal_end,
            end_ms=final_ms,
            events=events,
            bpm=bpm,
        )
        if outro_sec:
            output.append(outro_sec)

    return output
