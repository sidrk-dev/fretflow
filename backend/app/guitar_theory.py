from __future__ import annotations

import re
from collections import defaultdict
from typing import Optional

import numpy as np

from .schemas import CapoOption, ChordEvent

MAJOR_ROOT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MINOR_ROOT_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"]

NOTE_TO_PC: dict[str, int] = {
    "C": 0, "B#": 0,
    "C#": 1, "Db": 1,
    "D": 2,
    "D#": 3, "Eb": 3,
    "E": 4, "Fb": 4,
    "F": 5, "E#": 5,
    "F#": 6, "Gb": 6,
    "G": 7,
    "G#": 8, "Ab": 8,
    "A": 9,
    "A#": 10, "Bb": 10,
    "B": 11, "Cb": 11,
}

QUALITY_SUFFIX_MAP: dict[str, str] = {
    "maj": "",
    "min": "m",
    "7": "7",
    "maj7": "maj7",
    "min7": "m7",
    "sus4": "sus4",
    "sus2": "sus2",
    "dim": "dim",
    "dim7": "dim7",
    "hdim7": "m7b5",
    "aug": "aug",
    "aug7": "7#5",
    "maj6": "6",
    "6": "6",
    "min6": "m6",
    "minmaj7": "m(maj7)",
    "5": "5",
}

MINOR_LIKE_QUALITIES = {"min", "min7", "min6", "minmaj7", "hdim7", "dim", "dim7"}

OPEN_MAJOR_PCS = {0, 2, 4, 7, 9}   # C, D, E, G, A
OPEN_MINOR_PCS = {2, 4, 9}         # Dm, Em, Am

INTERVAL_SEMITONES: dict[str, int] = {
    "1": 0, "b2": 1, "2": 2, "#2": 3, "b3": 3, "3": 4,
    "4": 5, "#4": 6, "b5": 6, "5": 7, "#5": 8, "b6": 8,
    "6": 9, "bb7": 9, "b7": 10, "7": 11,
}

_MAJ_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MIN_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_MAJ_Z = (_MAJ_PROFILE - _MAJ_PROFILE.mean()) / _MAJ_PROFILE.std()
_MIN_Z = (_MIN_PROFILE - _MIN_PROFILE.mean()) / _MIN_PROFILE.std()


def format_guitar_chord(root_pc: int, quality: str, bass_pc: Optional[int] = None) -> str:
    root_pc = root_pc % 12
    q_norm = quality if quality in QUALITY_SUFFIX_MAP else "maj"
    root_names = MINOR_ROOT_NAMES if q_norm in MINOR_LIKE_QUALITIES else MAJOR_ROOT_NAMES
    root_str = root_names[root_pc]
    suffix = QUALITY_SUFFIX_MAP.get(q_norm, "")
    label = f"{root_str}{suffix}"
    if bass_pc is not None and (bass_pc % 12) != root_pc:
        bass_str = MAJOR_ROOT_NAMES[bass_pc % 12]
        label = f"{label}/{bass_str}"
    return label


def parse_harte_chord(label: str) -> Optional[tuple[int, str, Optional[int], str]]:
    """Parse Harte/MIREX chord string (e.g. 'F#:min7', 'G/3', 'Bb') -> (root_pc, quality, bass_pc, display)."""
    if not label:
        return None
    s = label.strip()
    if s in ("N", "X", "NC", "None"):
        return None

    bass_str: Optional[str] = None
    if "/" in s:
        s, bass_str = s.rsplit("/", 1)

    if ":" in s:
        root_part, qual_part = s.split(":", 1)
    else:
        m = re.match(r"^([A-Ga-g][#b]?)(.*)$", s)
        if not m:
            return None
        root_part, qual_part = m.group(1), m.group(2)

    root_part = root_part[0].upper() + root_part[1:]
    if root_part not in NOTE_TO_PC:
        return None
    root_pc = NOTE_TO_PC[root_part]

    q = qual_part.strip() or "maj"
    q_alias = {
        "m": "min",
        "min9": "min7",
        "maj9": "maj7",
        "9": "7",
        "7sus4": "sus4",
        "sus": "sus4",
        "m7b5": "hdim7",
        "min7b5": "hdim7",
        "6": "maj6",
    }
    q = q_alias.get(q, q)
    if q not in QUALITY_SUFFIX_MAP:
        q = "min" if q.startswith("m") and not q.startswith("maj") else "maj"

    bass_pc: Optional[int] = None
    if bass_str:
        b = bass_str.strip()
        if b in INTERVAL_SEMITONES:
            bass_pc = (root_pc + INTERVAL_SEMITONES[b]) % 12
        else:
            b_norm = b[0].upper() + b[1:] if b else ""
            if b_norm in NOTE_TO_PC:
                bass_pc = NOTE_TO_PC[b_norm]

    display = format_guitar_chord(root_pc, q, bass_pc)
    return root_pc, q, bass_pc, display


def _chord_ergonomic_weight(shape_pc: int, quality: str) -> tuple[float, bool]:
    is_minor = quality in MINOR_LIKE_QUALITIES
    if not is_minor and shape_pc in OPEN_MAJOR_PCS:
        if quality in ("dim", "dim7", "aug", "aug7"):
            return 0.45, False
        return 1.0, True
    if is_minor and shape_pc in OPEN_MINOR_PCS:
        if quality in ("dim", "dim7", "hdim7"):
            return 0.50, False
        return 1.0, True

    if shape_pc == 5 and quality == "maj7":
        return 0.82, True
    if shape_pc == 11 and quality == "7":
        return 0.78, True
    if shape_pc == 11 and quality in ("min", "min7"):
        return 0.58, False
    if shape_pc == 5 and not is_minor:
        return 0.52, False
    if shape_pc in (6, 1) and is_minor:
        return 0.35, False

    return 0.12, False


def estimate_key_label(events: list[ChordEvent], transpose_semitones: int = 0) -> str:
    """Z-scored Pearson Krumhansl-Schmuckler key estimation with exact triad/sus/dim/aug intervals."""
    if not events:
        return "C Major"

    chroma = np.zeros(12, dtype=np.float64)
    for ev in events:
        dur = max(0.05, (ev.endMs - ev.startMs) / 1000.0)
        rpc = (ev.rootPc + transpose_semitones) % 12
        chroma[rpc] += dur * 1.5
        q = ev.quality
        if q == "sus2":
            chroma[(rpc + 2) % 12] += dur * 0.8
            chroma[(rpc + 7) % 12] += dur * 0.8
        elif q == "sus4":
            chroma[(rpc + 5) % 12] += dur * 0.8
            chroma[(rpc + 7) % 12] += dur * 0.8
        elif q == "5":
            chroma[(rpc + 7) % 12] += dur * 0.9
        elif q in ("dim", "dim7", "hdim7"):
            chroma[(rpc + 3) % 12] += dur * 1.0
            chroma[(rpc + 6) % 12] += dur * 0.8
        elif q in ("aug", "aug7"):
            chroma[(rpc + 4) % 12] += dur * 1.0
            chroma[(rpc + 8) % 12] += dur * 0.8
        else:
            third = 3 if q in MINOR_LIKE_QUALITIES else 4
            chroma[(rpc + third) % 12] += dur * 1.0
            chroma[(rpc + 7) % 12] += dur * 0.8

    c_std = float(chroma.std())
    if c_std < 1e-8:
        return "C Major"
    c_norm = (chroma - chroma.mean()) / c_std

    best_score = -1e9
    best_label = "C Major"
    for pc in range(12):
        rot = np.roll(c_norm, -pc)
        maj_s = float(np.dot(rot, _MAJ_Z))
        if maj_s > best_score:
            best_score = maj_s
            best_label = f"{MAJOR_ROOT_NAMES[pc]} Major"
        min_s = float(np.dot(rot, _MIN_Z))
        if min_s > best_score:
            best_score = min_s
            best_label = f"{MINOR_ROOT_NAMES[pc]} Minor"
    return best_label


def compute_capo_options(
    events: list[ChordEvent], max_fret: int = 7
) -> tuple[list[CapoOption], int]:
    if not events:
        default_opt = CapoOption(
            capoFret=0,
            score=100.0,
            openChordRatio=1.0,
            keyLabel="C Major",
            previewChords=[],
            isRecommended=True,
        )
        return [default_opt], 0

    total_dur = sum(max(50, ev.endMs - ev.startMs) for ev in events)
    options: list[CapoOption] = []

    for fret in range(0, max_fret + 1):
        weighted_sum = 0.0
        open_dur = 0.0
        chord_durations: dict[str, int] = defaultdict(int)

        for ev in events:
            dur = max(50, ev.endMs - ev.startMs)
            shape_pc = (ev.rootPc - fret) % 12
            shape_bass = ((ev.bassPc - fret) % 12) if ev.bassPc is not None else None
            w, is_open = _chord_ergonomic_weight(shape_pc, ev.quality)
            weighted_sum += w * dur
            if is_open:
                open_dur += dur
            disp = format_guitar_chord(shape_pc, ev.quality, shape_bass)
            chord_durations[disp] += dur

        raw_ratio = weighted_sum / max(1.0, float(total_dur))
        open_ratio = open_dur / max(1.0, float(total_dur))
        fret_penalty = (0.03 if fret > 0 else 0.0) + (0.012 * fret)
        final_score = round(max(0.0, min(100.0, (raw_ratio - fret_penalty) * 100.0)), 1)

        top_chords = [
            ch for ch, _ in sorted(chord_durations.items(), key=lambda kv: kv[1], reverse=True)[:5]
        ]
        key_lbl = estimate_key_label(events, transpose_semitones=-fret)

        options.append(
            CapoOption(
                capoFret=fret,
                score=final_score,
                openChordRatio=round(open_ratio, 3),
                keyLabel=key_lbl,
                previewChords=top_chords,
                isRecommended=False,
            )
        )

    best = max(options, key=lambda o: o.score)
    capo0 = options[0]
    recommended_fret = best.capoFret if (best.score - capo0.score >= 10.0) else 0
    for opt in options:
        opt.isRecommended = opt.capoFret == recommended_fret

    return options, recommended_fret
