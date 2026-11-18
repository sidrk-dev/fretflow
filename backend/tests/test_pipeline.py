from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.acr_fast import extract_beats, run_fast_chord_recognition
from app.acr_neural import _load_bundle, run_neural_chord_recognition
from app.aligner import align_lyrics_and_chords, map_studio_to_video_ms
from app.audio import (
    BINS_PER_OCTAVE,
    HOP_LENGTH,
    N_BINS,
    SAMPLE_RATE,
    AudioFeatures,
    get_cached_audio_path,
)
from app.guitar_theory import compute_capo_options, estimate_key_label, parse_harte_chord
from app.lyrics import (
    _normalize_primary_artist,
    fetch_best_lyrics,
    parse_betterlyrics_ttml,
    parse_lrc_string,
    parse_lrclib_yaml,
)
from app.main import app
from app.schemas import ChordEvent, ChordsPayload, SkipSegment
from app.search import YOUTUBE_URL_ID_RE, clean_track_metadata, search_songs_and_videos
from app.sponsorblock import fetch_sponsorblock_offsets, merge_skip_segments


def _synth_chord_audio(
    freqs_per_segment: list[tuple[float, list[float]]], sr: int = SAMPLE_RATE
) -> AudioFeatures:
    segments = []
    for dur_sec, freqs in freqs_per_segment:
        t = np.linspace(0, dur_sec, int(sr * dur_sec), endpoint=False, dtype=np.float32)
        sig = np.zeros_like(t)
        for f in freqs:
            sig += 0.55 * np.sin(2 * np.pi * f * t)
            sig += 0.28 * np.sin(2 * np.pi * (2 * f) * t)
            sig += 0.14 * np.sin(2 * np.pi * (3 * f) * t)
        beat_env = 0.75 + 0.25 * np.abs(np.cos(np.pi * 2.0 * t))
        segments.append(sig * beat_env)

    y = np.concatenate(segments).astype(np.float32)
    y /= np.max(np.abs(y)) + 1e-6

    cqt = librosa.cqt(
        y,
        sr=sr,
        n_bins=N_BINS,
        bins_per_octave=BINS_PER_OCTAVE,
        hop_length=HOP_LENGTH,
        fmin=float(librosa.note_to_hz("C1")),
    )
    cqt_mag = np.abs(cqt).astype(np.float32)
    log_cqt = np.log(cqt_mag + 1e-6).T.astype(np.float32)
    return AudioFeatures(
        audio_path=Path("/tmp/synth.mp3"),
        samples=y,
        sr=sr,
        cqt_mag=cqt_mag,
        log_cqt_frames=log_cqt,
        frame_duration=float(HOP_LENGTH) / float(sr),
    )


def test_clean_track_metadata_regressions():
    # Standard VEVO upload
    assert clean_track_metadata(
        "Oasis - Wonderwall (Official Video) [HD Remastered]", "OasisVEVO"
    ) == ("Wonderwall", "Oasis")

    # Edition suffixes must NOT overwrite trusted studio artist
    assert clean_track_metadata("Get Lucky - Radio Edit", "Daft Punk", trusted_artist=True) == (
        "Get Lucky",
        "Daft Punk",
    )
    assert clean_track_metadata("Layla - Acoustic", "Eric Clapton", trusted_artist=True) == (
        "Layla",
        "Eric Clapton",
    )
    assert clean_track_metadata("Cliffs Of Dover - Instrumental", "Eric Johnson - Topic") == (
        "Cliffs Of Dover",
        "Eric Johnson",
    )

    # Reversed "Title - Artist" upload
    assert clean_track_metadata(
        "Knockin' On Heaven's Door - Guns N' Roses", "Guns N' Roses"
    ) == ("Knockin' On Heaven's Door", "Guns N' Roses")

    # Alphanumeric normalized VEVO match ("GunsNRoses" vs "Guns N' Roses")
    assert clean_track_metadata(
        "Guns N' Roses - Knockin' On Heaven's Door", "GunsNRosesVEVO"
    ) == ("Knockin' On Heaven's Door", "Guns N' Roses")

    # Comma-containing band names preserved
    assert _normalize_primary_artist("Earth, Wind & Fire") == "Earth, Wind & Fire"
    assert _normalize_primary_artist("Tyler, The Creator") == "Tyler, The Creator"

    # Shorts & Live URL regex
    m = YOUTUBE_URL_ID_RE.search("https://www.youtube.com/shorts/dQw4w9WgXcQ?feature=share")
    assert m and m.group(1) == "dQw4w9WgXcQ"


def test_harte_parser_key_estimator_and_smart_capo():
    bundle = _load_bundle()
    assert bundle.model.n_classes == 170
    # Verify all 170 model classes parse cleanly without raising
    parsed_non_null = 0
    for _, lbl in bundle.idx_to_chord.items():
        res = parse_harte_chord(lbl)
        if lbl not in ("N", "X"):
            assert res is not None, f"Failed to parse model chord {lbl}"
            parsed_non_null += 1
    assert parsed_non_null >= 168

    wonderwall_events = [
        ChordEvent(harte="F#:min7", rootPc=6, quality="min7", display="F#m7", startMs=0, endMs=2000),
        ChordEvent(harte="A", rootPc=9, quality="maj", display="A", startMs=2000, endMs=4000),
        ChordEvent(harte="E:sus4", rootPc=4, quality="sus4", display="Esus4", startMs=4000, endMs=6000),
        ChordEvent(harte="B:sus4", rootPc=11, quality="sus4", display="Bsus4", startMs=6000, endMs=8000),
    ]
    options, rec_fret = compute_capo_options(wonderwall_events)
    assert rec_fret == 2
    capo2 = next(o for o in options if o.capoFret == 2)
    assert set(capo2.previewChords) == {"Em7", "G", "Dsus4", "Asus4"}

    c_major_events = [
        ChordEvent(harte="C", rootPc=0, quality="maj", display="C", startMs=0, endMs=2000),
        ChordEvent(harte="G", rootPc=7, quality="maj", display="G", startMs=2000, endMs=4000),
        ChordEvent(harte="A:min", rootPc=9, quality="min", display="Am", startMs=4000, endMs=6000),
        ChordEvent(harte="F", rootPc=5, quality="maj", display="F", startMs=6000, endMs=8000),
    ]
    assert estimate_key_label(c_major_events) == "C Major"


def test_ttml_yaml_and_lrc_edge_cases():
    # Nested x-bg TTML with leading '(' and unit suffixes ('s' / 'ms')
    sample_ttml = """<tt xmlns="http://www.w3.org/ns/ttml" xmlns:itunes="http://music.apple.com/lyric-ttml-internal" xmlns:ttm="http://www.w3.org/ns/ttml#metadata">
      <body>
        <div begin="22s" end="33s" itunes:songPart="Verse">
          <p begin="22.175s" end="28.5s">
            <span begin="22175ms" end="23223ms">Today </span>
            <span ttm:role="x-bg">(<span begin="24.0s" end="25.5s">oh yeah</span>)</span>
          </p>
        </div>
      </body>
    </tt>"""
    ttml_res = parse_betterlyrics_ttml(sample_ttml)
    assert ttml_res is not None and ttml_res.hasWordSync is True
    assert "(oh yeah)" in ttml_res.sections[0].lines[0].text

    # Pre-trimmed YAML word spacing recovery
    sample_yaml = """
version: '1.0'
lines:
- text: Today is gonna be
  start_ms: 1000
  end_ms: 4000
  words:
  - text: Today
    start_ms: 1000
  - text: is
    start_ms: 1800
  - text: gonna
    start_ms: 2400
  - text: be
    start_ms: 3200
"""
    yaml_res = parse_lrclib_yaml(sample_yaml)
    assert yaml_res is not None
    joined = "".join(w.text for w in yaml_res.sections[0].lines[0].words)
    assert joined == "Today is gonna be"

    # Multi-timestamp LRC + [offset:] + NetEase credit stripping + Megalobiz colon centiseconds
    sample_lrc = "\n".join(
        [
            "[offset:+500]",
            "[00:00.00]作词 : Noel Gallagher",
            "[00:01.00]作曲 : Noel Gallagher",
            "[00:10.00]First verse line",
            "[00:15.00][00:45.00]Repeated chorus hook",
            "[00:20.00][00:50.00]",
            "[00:25:50]Megalobiz colon timestamp",
        ]
    )
    lrc_res = parse_lrc_string(sample_lrc)
    assert lrc_res is not None
    all_lines = [ln for s in lrc_res.sections for ln in s.lines]
    texts = [ln.text for ln in all_lines]
    assert not any("作词" in t or "[00:" in t for t in texts)
    assert texts.count("Repeated chorus hook") == 2
    assert all_lines[0].startMs == 9500  # 10000 - 500ms [offset:+500]


def test_piecewise_sponsorblock_and_negative_offset_alignment():
    segs = merge_skip_segments(
        [
            SkipSegment(category="music_offtopic", startMs=0, endMs=5000),
            SkipSegment(category="music_offtopic", startMs=5200, endMs=15000),
            SkipSegment(category="music_offtopic", startMs=100_000, endMs=150_000),
            SkipSegment(category="music_offtopic", startMs=270_000, endMs=278_000),
        ]
    )
    assert len(segs) == 3
    assert segs[0].startMs == 0 and segs[0].endMs == 15000

    # Studio 10s -> shifted by 15s intro -> 25s
    assert map_studio_to_video_ms(10_000, 15_000, 0, segs, video_duration_ms=278_000) == 25_000
    # Studio 90s -> +15s intro = 105s (>= 100s mid-video skit!) -> +50s skit = 155s
    assert map_studio_to_video_ms(90_000, 15_000, 0, segs, video_duration_ms=278_000) == 155_000


def test_dual_mode_acr_and_whole_word_syllable_anchoring():
    feats = _synth_chord_audio(
        [
            (3.0, [130.81, 164.81, 196.00, 261.63]),
            (3.0, [98.00, 123.47, 146.83, 196.00]),
            (3.0, [110.00, 130.81, 164.81, 220.00]),
            (3.0, [87.31, 110.00, 130.81, 174.61]),
        ]
    )
    bpm, beats_ms = extract_beats(feats)
    fast_payload = run_fast_chord_recognition(feats, bpm, beats_ms)
    neural_payload = run_neural_chord_recognition(feats, bpm, beats_ms)
    assert len({ev.rootPc for ev in fast_payload.events} & {0, 7, 9, 5}) >= 3
    assert len({ev.rootPc for ev in neural_payload.events} & {0, 7, 9, 5}) >= 3

    # Ensure chord occurring mid-word on syllable 2 ("wall") snaps to syllable 1 ("wonder")
    syllabic_ttml = """<tt xmlns="http://www.w3.org/ns/ttml" xmlns:itunes="http://music.apple.com/lyric-ttml-internal"><body>
      <div itunes:songPart="Outro">
        <p begin="5.0" end="9.0">
          <span begin="5.0" end="6.0">You're my </span>
          <span begin="6.0" end="6.4">wonder</span><span begin="6.4" end="8.5">wall</span>
        </p>
      </div>
    </body></tt>"""
    lyr = parse_betterlyrics_ttml(syllabic_ttml)
    aligned = align_lyrics_and_chords(lyr, neural_payload, total_offset_ms=0, song_duration_ms=22_000)
    lyric_sec = next(s for s in aligned if s.kind == "lyrics")
    for ch in lyric_sec.lines[0].chords:
        # Word index 2 is "wall" (preceded by "wonder" without trailing space) -> must snap to 1 ("wonder") or 0!
        assert ch.wordIndex != 2

    # Trailing instrumental section after an "Outro" vocal section must be named "Instrumental Outro" (never duplicate "Outro")
    section_names = [s.name for s in aligned]
    assert section_names.count("Outro") <= 1

    # Rapid 3-chord change over a single sustained word ("Feels ") must produce strictly monotonic wordIndex order
    rapid_ttml = """<tt xmlns="http://www.w3.org/ns/ttml"><body><div>
      <p begin="52.88" end="55.00">
        <span begin="52.88" end="53.70">Feels </span>
        <span begin="53.70" end="54.10">the </span>
        <span begin="54.10" end="55.00">way</span>
      </p>
    </div></body></tt>"""
    rapid_chords = ChordsPayload(
        engine="neural_btc_170",
        bpm=118.0,
        detectedKey="F# Minor",
        recommendedCapo=2,
        events=[
            ChordEvent(startMs=51_450, endMs=53_030, harte="E:maj", display="E", rootPc=4, quality="maj", confidence=0.9),
            ChordEvent(startMs=53_030, endMs=53_660, harte="A:maj", display="A", rootPc=9, quality="maj", confidence=0.9),
            ChordEvent(startMs=53_660, endMs=55_200, harte="F#:min7", display="F#m7", rootPc=6, quality="min7", confidence=0.9),
        ],
    )
    rapid_aligned = align_lyrics_and_chords(parse_betterlyrics_ttml(rapid_ttml), rapid_chords, total_offset_ms=0, song_duration_ms=60_000)
    rapid_lyric_sec = next(s for s in rapid_aligned if s.kind == "lyrics")
    rapid_anchors = rapid_lyric_sec.lines[0].chords
    word_indices = [a.wordIndex for a in rapid_anchors if a.wordIndex is not None]
    assert word_indices == sorted(word_indices)
    assert [a.display for a in rapid_anchors] == ["E", "A", "F#m7"]


def test_api_security_and_http_range_compliance():
    with pytest.raises(ValueError):
        get_cached_audio_path("../../etc/passwd")

    with TestClient(app) as client:
        # Invalid video_id length/chars rejected with 422
        assert client.get("/api/audio/not_valid!!").status_code == 422
        assert client.get("/api/session/" + ("a" * 80) + "/stream").status_code == 422

        # Non-existent session PATCH returns clean 404 without creating ghost row
        assert (
            client.patch("/api/session/ZzZzZzZzZ99/offset", json={"manualOffsetMs": 250}).status_code
            == 404
        )

        # Out-of-bounds offset rejected with 422
        assert (
            client.patch("/api/session/bx1Bh8ZvH84/offset", json={"manualOffsetMs": 9_999_999}).status_code
            == 422
        )

        # Test RFC 9110 Range handling if bx1Bh8ZvH84.mp3 is cached
        mp3_path = get_cached_audio_path("bx1Bh8ZvH84")
        if mp3_path.is_file():
            size = mp3_path.stat().st_size
            # Suffix range bytes=-500 must return the LAST 500 bytes
            r_suf = client.get("/api/audio/bx1Bh8ZvH84", headers={"Range": "bytes=-500"})
            assert r_suf.status_code == 206
            assert len(r_suf.content) == 500
            assert r_suf.headers["content-range"] == f"bytes {size - 500}-{size - 1}/{size}"

            # Out-of-bounds range returns 416 with Content-Range: bytes */size
            r_416 = client.get("/api/audio/bx1Bh8ZvH84", headers={"Range": f"bytes={size + 100}-{size + 500}"})
            assert r_416.status_code == 416
            assert r_416.headers.get("content-range") == f"bytes */{size}"

            # HEAD supported
            assert client.head("/api/audio/bx1Bh8ZvH84").status_code == 200


@pytest.mark.asyncio
async def test_live_search_11char_and_sponsorblock():
    # 11-char band name ("Soundgarden") must NOT crash or get mistaken for a videoId
    sg_results = await search_songs_and_videos("Soundgarden")
    assert len(sg_results) >= 3

    # General song query ("Creep Radiohead") must populate both Official Audio ("studio") and Music Videos ("video")
    creep_results = await search_songs_and_videos("Creep Radiohead")
    creep_types = {r.resultType for r in creep_results}
    assert "studio" in creep_types
    assert "video" in creep_types

    # Deleted/nonexistent YouTube URL must return [] cleanly instead of HTTP 500
    dead_results = await search_songs_and_videos("https://www.youtube.com/watch?v=00000000000")
    assert dead_results == []

    offset_ms, eff_dur, segs = await fetch_sponsorblock_offsets("bx1Bh8ZvH84", 278)
    assert offset_ms > 10_000
    lyr = await fetch_best_lyrics("Wonderwall", "Oasis", effective_duration_sec=eff_dur)
    assert lyr.hasWordSync is True
