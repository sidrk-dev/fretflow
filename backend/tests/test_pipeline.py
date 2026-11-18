from __future__ import annotations

import numpy as np
import pytest

from app.acr_fast import extract_beats, run_fast_chord_recognition
from app.acr_neural import _load_bundle, run_neural_chord_recognition
from app.aligner import align_lyrics_and_chords
from app.audio import BINS_PER_OCTAVE, HOP_LENGTH, N_BINS, SAMPLE_RATE, AudioFeatures
from app.guitar_theory import compute_capo_options, parse_harte_chord
from app.lyrics import (
    fetch_best_lyrics,
    parse_betterlyrics_ttml,
    parse_lrc_string,
    parse_lrclib_yaml,
)
from app.schemas import ChordEvent
from app.search import clean_track_metadata
from app.sponsorblock import fetch_sponsorblock_offsets
import librosa
from pathlib import Path


def _synth_chord_audio(freqs_per_segment: list[tuple[float, list[float]]], sr: int = SAMPLE_RATE) -> AudioFeatures:
    segments = []
    for dur_sec, freqs in freqs_per_segment:
        t = np.linspace(0, dur_sec, int(sr * dur_sec), endpoint=False, dtype=np.float32)
        sig = np.zeros_like(t)
        for f in freqs:
            # Add fundamental + 2nd/3rd harmonics like a Plucked Guitar string
            sig += 0.55 * np.sin(2 * np.pi * f * t)
            sig += 0.28 * np.sin(2 * np.pi * (2 * f) * t)
            sig += 0.14 * np.sin(2 * np.pi * (3 * f) * t)
        # Add subtle strummed envelope pulses every 0.5s (120 BPM)
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


def test_clean_track_metadata():
    title, artist = clean_track_metadata(
        "Oasis - Wonderwall (Official Video) [HD Remastered]", "OasisVEVO"
    )
    assert title == "Wonderwall"
    assert artist == "Oasis"


def test_harte_parser_and_smart_capo():
    parsed = parse_harte_chord("F#:min7")
    assert parsed is not None
    root_pc, qual, bass_pc, disp = parsed
    assert root_pc == 6
    assert qual == "min7"
    assert disp == "F#m7"

    # Wonderwall concert chords: F#m7 - A - E - B -> should strongly recommend Capo 2 (Em7 - G - D - A)
    wonderwall_events = [
        ChordEvent(harte="F#:min7", rootPc=6, quality="min7", display="F#m7", startMs=0, endMs=2000),
        ChordEvent(harte="A", rootPc=9, quality="maj", display="A", startMs=2000, endMs=4000),
        ChordEvent(harte="E", rootPc=4, quality="maj", display="E", startMs=4000, endMs=6000),
        ChordEvent(harte="B:sus4", rootPc=11, quality="sus4", display="Bsus4", startMs=6000, endMs=8000),
    ]
    options, rec_fret = compute_capo_options(wonderwall_events)
    assert rec_fret == 2
    capo2 = next(o for o in options if o.capoFret == 2)
    assert set(capo2.previewChords) == {"Em7", "G", "D", "Asus4"}

    # Already-open progression: G - D - Em - C -> should keep Capo 0
    open_events = [
        ChordEvent(harte="G", rootPc=7, quality="maj", display="G", startMs=0, endMs=2000),
        ChordEvent(harte="D", rootPc=2, quality="maj", display="D", startMs=2000, endMs=4000),
        ChordEvent(harte="E:min", rootPc=4, quality="min", display="Em", startMs=4000, endMs=6000),
        ChordEvent(harte="C", rootPc=0, quality="maj", display="C", startMs=6000, endMs=8000),
    ]
    _, open_rec = compute_capo_options(open_events)
    assert open_rec == 0


def test_ttml_yaml_and_lrc_parsers():
    sample_ttml = """<tt xmlns="http://www.w3.org/ns/ttml" xmlns:itunes="http://music.apple.com/lyric-ttml-internal">
      <body>
        <div begin="22.0" end="33.0" itunes:songPart="Verse">
          <p begin="22.175" end="27.781">
            <span begin="22.175" end="23.223">Today</span> <span begin="23.223" end="23.717">is</span> <span begin="23.717" end="26.031">gonna be the day</span>
          </p>
        </div>
        <div begin="45.0" end="60.0" itunes:songPart="Chorus">
          <p begin="45.5" end="50.0">
            <span begin="45.5" end="47.0">And</span> <span begin="47.0" end="50.0">maybe</span>
          </p>
        </div>
      </body>
    </tt>"""
    ttml_res = parse_betterlyrics_ttml(sample_ttml)
    assert ttml_res is not None
    assert ttml_res.hasWordSync is True
    assert ttml_res.sections[0].name == "Verse 1"
    assert ttml_res.sections[1].name == "Chorus"
    assert ttml_res.sections[0].lines[0].text == "Today is gonna be the day"
    assert len(ttml_res.sections[0].lines[0].words) == 3

    sample_yaml = """
version: '1.0'
lines:
- text: Today is gonna be the day
  start_ms: 22175
  end_ms: 27781
  words:
  - text: 'Today '
    start_ms: 22175
  - text: 'is '
    start_ms: 23223
  - text: 'gonna be the day'
    start_ms: 23717
"""
    yaml_res = parse_lrclib_yaml(sample_yaml)
    assert yaml_res is not None
    assert yaml_res.hasWordSync is True
    assert yaml_res.sections[0].lines[0].words[0].endMs == 23223

    sample_elrc = "[00:12.00]<00:12.00>Hello <00:12.80>world\n[00:15.50]<00:15.50>Guitar <00:16.20>karaoke"
    elrc_res = parse_lrc_string(sample_elrc)
    assert elrc_res is not None
    assert elrc_res.hasWordSync is True
    assert elrc_res.sections[0].lines[0].text == "Hello world"


def test_dual_mode_acr_and_alignment():
    # Load BTC checkpoint strictly
    bundle = _load_bundle()
    assert bundle.model.n_classes == 170

    # Synthesize C major (C3-E3-G3-C4) -> G major (G2-B2-D3-G3) -> A minor (A2-C3-E3-A3) -> F major (F2-A2-C3-F3)
    feats = _synth_chord_audio(
        [
            (3.0, [130.81, 164.81, 196.00, 261.63]),  # C
            (3.0, [98.00, 123.47, 146.83, 196.00]),   # G
            (3.0, [110.00, 130.81, 164.81, 220.00]),  # Am
            (3.0, [87.31, 110.00, 130.81, 174.61]),   # F
        ]
    )
    bpm, beats_ms = extract_beats(feats)
    assert 65.0 <= bpm <= 180.0

    fast_payload = run_fast_chord_recognition(feats, bpm, beats_ms)
    neural_payload = run_neural_chord_recognition(feats, bpm, beats_ms)

    assert len(fast_payload.events) >= 2
    assert len(neural_payload.events) >= 2
    fast_roots = {ev.rootPc for ev in fast_payload.events}
    neural_roots = {ev.rootPc for ev in neural_payload.events}
    # Expect core progression roots (C=0, G=7, A=9, F=5) detected
    assert len(fast_roots & {0, 7, 9, 5}) >= 3
    assert len(neural_roots & {0, 7, 9, 5}) >= 3

    # Test alignment with intro chord bars + lyric word snapping
    lyr = parse_lrc_string("[00:05.50]<00:05.50>Singing <00:07.00>over <00:09.20>chords")
    aligned = align_lyrics_and_chords(lyr, neural_payload, total_offset_ms=500, song_duration_ms=12_000)
    assert aligned[0].kind == "instrumental"
    assert aligned[0].name == "Intro"
    lyric_sec = next(s for s in aligned if s.kind == "lyrics")
    assert lyric_sec.lines[0].startMs == 6000
    assert len(lyric_sec.lines[0].chords) >= 1


@pytest.mark.asyncio
async def test_live_sponsorblock_and_lyrics():
    offset_ms, eff_dur, segs = await fetch_sponsorblock_offsets("bx1Bh8ZvH84", 278)
    assert offset_ms > 10_000
    assert 245 <= eff_dur <= 268
    assert len(segs) >= 1

    lyr = await fetch_best_lyrics("Wonderwall", "Oasis", effective_duration_sec=eff_dur)
    assert lyr.hasLineSync is True
    assert len(lyr.sections) >= 2
