from __future__ import annotations

import librosa
import numpy as np

from .audio import AudioFeatures
from .guitar_theory import (
    MAJOR_ROOT_NAMES,
    compute_capo_options,
    estimate_key_label,
    parse_harte_chord,
)
from .schemas import ChordEvent, ChordsPayload


def _build_chord_templates() -> tuple[np.ndarray, list[str]]:
    """Build 49 L2-normalized 12-D chroma templates (Maj, min, 7, min7 + No-Chord)."""
    templates: list[np.ndarray] = []
    labels: list[str] = []

    specs = [
        ("maj", [(0, 1.0), (4, 0.88), (7, 0.92)]),
        ("min", [(0, 1.0), (3, 0.90), (7, 0.92)]),
        ("7", [(0, 1.0), (4, 0.82), (7, 0.85), (10, 0.72)]),
        ("min7", [(0, 1.0), (3, 0.84), (7, 0.85), (10, 0.72)]),
    ]

    for qual, intervals in specs:
        for pc in range(12):
            vec = np.zeros(12, dtype=np.float32)
            for ivl, weight in intervals:
                vec[(pc + ivl) % 12] = weight
            vec /= np.linalg.norm(vec) + 1e-8
            templates.append(vec)
            root_name = MAJOR_ROOT_NAMES[pc]
            labels.append(root_name if qual == "maj" else f"{root_name}:{qual}")

    nc = np.ones(12, dtype=np.float32) / np.sqrt(12.0)
    templates.append(nc)
    labels.append("N")
    return np.stack(templates, axis=0), labels


_TEMPLATES, _STATE_LABELS = _build_chord_templates()


def _viterbi_decode(log_obs: np.ndarray, stay_prob: float = 0.88) -> np.ndarray:
    """Vectorized log-space Viterbi decoder over (T, K) observation scores."""
    num_frames, num_states = log_obs.shape
    if num_frames == 0:
        return np.zeros(0, dtype=np.int64)

    log_stay = float(np.log(stay_prob))
    log_switch = float(np.log((1.0 - stay_prob) / max(1, num_states - 1)))

    trans = np.full((num_states, num_states), log_switch, dtype=np.float32)
    np.fill_diagonal(trans, log_stay)

    backptr = np.zeros((num_frames, num_states), dtype=np.int16)
    dp = log_obs[0].copy()

    for t in range(1, num_frames):
        scores = dp[:, None] + trans
        best_prev = np.argmax(scores, axis=0)
        backptr[t] = best_prev
        dp = scores[best_prev, np.arange(num_states)] + log_obs[t]

    path = np.zeros(num_frames, dtype=np.int64)
    path[-1] = int(np.argmax(dp))
    for t in range(num_frames - 1, 0, -1):
        path[t - 1] = int(backptr[t, path[t]])
    return path


def frames_to_smoothed_events(
    frame_labels: list[str],
    frame_confidences: np.ndarray,
    frame_duration: float,
    beats_ms: list[int],
    min_segment_sec: float = 0.45,
) -> list[ChordEvent]:
    """Convert per-frame Harte labels into beat-snapped, Guitar-formatted ChordEvents."""
    if not frame_labels:
        return []

    raw_segs: list[list] = []
    cur_lbl = frame_labels[0]
    start_idx = 0

    for i in range(1, len(frame_labels)):
        if frame_labels[i] != cur_lbl:
            conf = float(np.mean(frame_confidences[start_idx:i])) if frame_confidences.size >= i else 0.85
            raw_segs.append([start_idx * frame_duration, i * frame_duration, cur_lbl, conf])
            cur_lbl = frame_labels[i]
            start_idx = i

    conf_last = float(np.mean(frame_confidences[start_idx:])) if frame_confidences.size > start_idx else 0.85
    raw_segs.append([start_idx * frame_duration, len(frame_labels) * frame_duration, cur_lbl, conf_last])

    merged: list[list] = []
    for seg in raw_segs:
        dur = seg[1] - seg[0]
        if merged and dur < min_segment_sec:
            merged[-1][1] = seg[1]
        elif merged and merged[-1][2] == seg[2]:
            merged[-1][1] = seg[1]
            merged[-1][3] = (merged[-1][3] + seg[3]) * 0.5
        else:
            merged.append(seg)

    beats_arr = np.asarray(beats_ms, dtype=np.int64) if beats_ms else np.zeros(0, dtype=np.int64)

    def _snap_ms(ms: int) -> int:
        if beats_arr.size == 0 or ms <= 0:
            return ms
        idx = int(np.argmin(np.abs(beats_arr - ms)))
        if abs(int(beats_arr[idx]) - ms) <= 135:
            return int(beats_arr[idx])
        return ms

    events: list[ChordEvent] = []
    prev_end_ms = 0

    for i, (s_sec, e_sec, harte, conf) in enumerate(merged):
        start_ms = prev_end_ms if i > 0 else int(round(s_sec * 1000))
        end_ms = _snap_ms(int(round(e_sec * 1000)))
        if end_ms <= start_ms + 120:
            end_ms = int(round(e_sec * 1000))
        prev_end_ms = end_ms

        parsed = parse_harte_chord(harte)
        if not parsed:
            continue
        root_pc, quality, bass_pc, display = parsed
        events.append(
            ChordEvent(
                harte=harte,
                rootPc=root_pc,
                quality=quality,
                bassPc=bass_pc,
                display=display,
                startMs=start_ms,
                endMs=end_ms,
                confidence=round(max(0.0, min(1.0, conf)), 3),
            )
        )

    coalesced: list[ChordEvent] = []
    for ev in events:
        if coalesced and coalesced[-1].display == ev.display and abs(ev.startMs - coalesced[-1].endMs) <= 80:
            coalesced[-1].endMs = ev.endMs
        else:
            coalesced.append(ev)

    return coalesced


def extract_beats(features: AudioFeatures) -> tuple[float, list[int]]:
    onset_env = librosa.onset.onset_strength(
        y=features.samples, sr=features.sr, hop_length=512
    )
    tempo, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset_env, sr=features.sr, hop_length=512
    )
    bpm_val = float(np.atleast_1d(tempo)[0]) if tempo is not None else 120.0
    if bpm_val <= 0:
        bpm_val = 120.0
    while bpm_val < 68.0:
        bpm_val *= 2.0
    while bpm_val > 176.0:
        bpm_val *= 0.5

    beat_times_sec = librosa.frames_to_time(beat_frames, sr=features.sr, hop_length=512)
    beats_ms = [int(round(float(t) * 1000)) for t in beat_times_sec]
    return round(bpm_val, 1), beats_ms


def run_fast_chord_recognition(
    features: AudioFeatures, bpm: float, beats_ms: list[int]
) -> ChordsPayload:
    """Fast (~0.4s) tuning-compensated, broadband-floor-cleaned CQT Chroma + Viterbi HMM recognizer."""
    cqt_mag = features.cqt_mag  # (144, T), 24 bins/octave starting at C1
    num_frames = cqt_mag.shape[1]
    if num_frames == 0:
        capo_opts, rec_capo = compute_capo_options([])
        return ChordsPayload(
            engine="fast_cqt_hmm",
            bpm=bpm,
            beatsMs=beats_ms,
            detectedKey="C Major",
            events=[],
            capoOptions=capo_opts,
            recommendedCapo=rec_capo,
            uniqueChords=[],
        )

    try:
        tuning = float(librosa.estimate_tuning(y=features.samples, sr=features.sr, bins_per_octave=12))
    except Exception:
        tuning = 0.0
    bin_shift = int(round(tuning * 2.0))
    shifted = np.roll(cqt_mag, -bin_shift, axis=0)

    # Symmetric semitone-centered folding around exact 2*p bins
    center = shifted[0::2]
    left = np.roll(shifted, 1, axis=0)[0::2]
    right = shifted[1::2]
    semitone_energy = 0.60 * center + 0.20 * left + 0.20 * right  # (72, T)

    oct_weights = np.array([0.65, 1.15, 1.25, 1.15, 0.90, 0.55], dtype=np.float32)[:, None, None]
    folded = (semitone_energy.reshape(6, 12, num_frames) * oct_weights).mean(axis=0)  # (12, T)

    # Subtract broadband percussive/drum floor so active frames don't collapse to uniform 'N'
    frame_energy = np.linalg.norm(folded, axis=0)
    energy_thresh = float(np.percentile(frame_energy, 8)) * 0.55
    floor = np.percentile(folded, 35, axis=0, keepdims=True)
    cleaned = np.maximum(0.0, folded - floor)
    chroma_norm = (cleaned / (np.linalg.norm(cleaned, axis=0, keepdims=True) + 1e-8)).T  # (T, 12)

    sim = chroma_norm @ _TEMPLATES.T  # (T, 49)
    sim[:, 24:48] -= 0.038
    silent_mask = frame_energy < energy_thresh
    sim[~silent_mask, 48] -= 0.15
    sim[silent_mask, 48] += 0.65

    log_obs = sim * 18.0
    state_seq = _viterbi_decode(log_obs, stay_prob=0.88)

    probs = np.exp(log_obs - np.max(log_obs, axis=1, keepdims=True))
    probs /= np.sum(probs, axis=1, keepdims=True) + 1e-8
    confs = probs[np.arange(num_frames), state_seq]
    frame_labels = [_STATE_LABELS[int(s)] for s in state_seq]

    events = frames_to_smoothed_events(
        frame_labels=frame_labels,
        frame_confidences=confs,
        frame_duration=features.frame_duration,
        beats_ms=beats_ms,
        min_segment_sec=0.45,
    )
    capo_options, recommended_capo = compute_capo_options(events)
    detected_key = estimate_key_label(events)
    unique_chords = list(dict.fromkeys(ev.display for ev in events))

    return ChordsPayload(
        engine="fast_cqt_hmm",
        bpm=bpm,
        beatsMs=beats_ms,
        detectedKey=detected_key,
        events=events,
        capoOptions=capo_options,
        recommendedCapo=recommended_capo,
        uniqueChords=unique_chords,
    )
