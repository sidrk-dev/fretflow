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
    SongSection,
)

INSTRUMENTAL_GAP_THRESHOLD_MS = 4500


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
    """Attach chord events occurring just before or during a lyric line to specific words or character offsets."""
    window_start = line.startMs - 280
    window_end = line.endMs
    if next_line_start_ms is not None and (next_line_start_ms - line.endMs) < INSTRUMENTAL_GAP_THRESHOLD_MS:
        window_end = max(line.endMs, min(next_line_start_ms - 250, line.endMs + 2200))

    overlapping = [
        ev for ev in events if ev.endMs > line.startMs + 80 and ev.startMs < window_end
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
            # Find the word active at eff_start or the closest upcoming word
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
            # Avoid stacking two chords on the exact same word index if possible
            if anchors and anchors[-1].wordIndex == best_w and best_w + 1 < len(line.words):
                best_w += 1
            word_idx = best_w

        # Also compute proportional charOffset for clean chord-above-lyric spacing
        if ev.startMs <= line.startMs + 120 and idx == 0:
            char_offset = 0
        else:
            frac = min(1.0, max(0.0, (eff_start - line.startMs) / float(line_span)))
            raw_char = int(round(frac * (text_len - 1)))
            # Snap to nearest word boundary in line.text so chord sits at start of a word
            while raw_char > 0 and line.text[raw_char - 1] not in (" ", "\t", "-"):
                raw_char -= 1
            if anchors and anchors[-1].charOffset is not None and raw_char <= anchors[-1].charOffset + 3:
                raw_char = min(text_len, (anchors[-1].charOffset or 0) + 5)
            char_offset = raw_char

        # Deduplicate back-to-back identical chord displays on the same line
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
) -> list[SongSection]:
    """
    Produce a complete timeline of SongSections combining:
    - Shifted synced lyrics (`studio_ms + total_offset_ms`)
    - Chords snapped directly above lyric words/characters
    - `[Intro]`, `[Instrumental]`, and `[Outro]` chord-bar sections during non-vocal passages
    """
    events = chords.events if chords else []
    bpm = chords.bpm if chords else 120.0

    # Instrumental-only or missing lyrics: group entire song into clean 8-bar sections
    if not lyrics or not lyrics.sections or lyrics.source == "none":
        if not events:
            return []
        end_ms = max(song_duration_ms, events[-1].endMs)
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

    # Shift all lyric lines & words by total_offset_ms (only if lyrics are time-synced)
    shift = total_offset_ms if lyrics.hasLineSync else 0
    shifted_sections: list[SongSection] = []
    all_shifted_lines: list[LyricLine] = []

    for sec in lyrics.sections:
        s_lines: list[LyricLine] = []
        for ln in sec.lines:
            s_words = [
                LyricWord(
                    text=w.text,
                    startMs=max(0, w.startMs + shift),
                    endMs=max(80, w.endMs + shift),
                )
                for w in ln.words
            ]
            new_ln = LyricLine(
                id=ln.id,
                startMs=max(0, ln.startMs + shift),
                endMs=max(200, ln.endMs + shift),
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

    # Anchor chords onto every shifted lyric line
    for global_i, ln in enumerate(all_shifted_lines):
        next_start = (
            all_shifted_lines[global_i + 1].startMs
            if global_i + 1 < len(all_shifted_lines)
            else None
        )
        ln.chords = _anchor_chords_to_line(ln, events, next_start)

    # Interleave [Intro], [Instrumental], and [Outro] chord-bar sections for non-vocal gaps
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
            if sec.startMs - prev_end >= INSTRUMENTAL_GAP_THRESHOLD_MS + 1500:
                solo_count += 1
                interlude = _build_instrumental_section(
                    sec_id=f"inst-break-{solo_count}",
                    name="Instrumental / Solo" if solo_count == 1 else f"Instrumental {solo_count}",
                    start_ms=prev_end,
                    end_ms=sec.startMs,
                    events=events,
                    bpm=bpm,
                )
                if interlude:
                    output.append(interlude)
        output.append(sec)

    last_vocal_end = shifted_sections[-1].endMs
    final_ms = max(song_duration_ms, events[-1].endMs)
    if final_ms - last_vocal_end >= INSTRUMENTAL_GAP_THRESHOLD_MS + 1500:
        outro_sec = _build_instrumental_section(
            sec_id="inst-outro",
            name="Outro",
            start_ms=last_vocal_end,
            end_ms=final_ms,
            events=events,
            bpm=bpm,
        )
        if outro_sec:
            output.append(outro_sec)

    return output
