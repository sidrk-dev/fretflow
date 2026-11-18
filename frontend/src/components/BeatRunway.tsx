import React, { useMemo } from 'react';
import type { GuitarTransformSettings } from '../lib/musicTransposer';
import { transformChord } from '../lib/musicTransposer';
import type { ChordEvent } from '../types/music';

interface BeatRunwayProps {
  currentTimeMs: number;
  bpm: number;
  beatsMs: number[];
  events: ChordEvent[];
  settings: GuitarTransformSettings;
  onSeekMs: (ms: number) => void;
}

const PAST_WINDOW_MS = 1200;
const FUTURE_WINDOW_MS = 8000;
const TOTAL_SPAN_MS = PAST_WINDOW_MS + FUTURE_WINDOW_MS;
const PLAYHEAD_PCT = (PAST_WINDOW_MS / TOTAL_SPAN_MS) * 100;

export const BeatRunway: React.FC<BeatRunwayProps> = ({
  currentTimeMs,
  bpm,
  beatsMs,
  events,
  settings,
  onSeekMs,
}) => {
  const beatInBar = useMemo(() => {
    if (!beatsMs.length) {
      const beatDur = 60000 / Math.max(60, bpm || 120);
      return (Math.floor(currentTimeMs / beatDur) % 4) + 1;
    }
    let lo = 0;
    let hi = beatsMs.length - 1;
    let idx = 0;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (beatsMs[mid] <= currentTimeMs) {
        idx = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    return (idx % 4) + 1;
  }, [beatsMs, bpm, currentTimeMs]);

  const visibleEvents = useMemo(() => {
    const startWin = currentTimeMs - PAST_WINDOW_MS;
    const endWin = currentTimeMs + FUTURE_WINDOW_MS;
    return events.filter((ev) => ev.endMs > startWin && ev.startMs < endWin);
  }, [events, currentTimeMs]);

  return (
    <div className="beat-runway-bar" aria-label="Beat pulse and upcoming chord runway">
      <div className="metronome-cluster" title={`${bpm || 120} BPM`}>
        <span className="bpm-readout">{Math.round(bpm || 120)} BPM</span>
        <div className="beat-dots">
          {[1, 2, 3, 4].map((b) => (
            <span
              key={b}
              className={`beat-dot ${beatInBar === b ? (b === 1 ? 'downbeat' : 'active') : ''}`}
            >
              {b}
            </span>
          ))}
        </div>
      </div>

      <div className="runway-track">
        <div
          className="runway-playhead"
          style={{ left: `${PLAYHEAD_PCT}%` }}
          title="Now Playing"
        />
        {visibleEvents.map((ev, i) => {
          const tx = transformChord(ev.rootPc, ev.quality, ev.bassPc, settings);
          const winOrigin = currentTimeMs - PAST_WINDOW_MS;
          const nextEv = visibleEvents[i + 1];
          const cappedEndMs = nextEv ? Math.min(ev.endMs, nextEv.startMs) : ev.endMs;

          const leftPct = ((ev.startMs - winOrigin) / TOTAL_SPAN_MS) * 100;
          const widthPct = Math.max(0.8, ((cappedEndMs - ev.startMs) / TOTAL_SPAN_MS) * 100);
          const isCurrent = currentTimeMs >= ev.startMs && currentTimeMs < cappedEndMs;

          // Keep the chord label pinned just to the right of the playhead while active so the line never cuts through text
          const playheadOffsetPct = isCurrent
            ? Math.max(0, PLAYHEAD_PCT - leftPct)
            : 0;

          return (
            <button
              key={`${ev.startMs}-${i}`}
              type="button"
              className={`runway-chord-pill ${isCurrent ? 'is-now' : ''}`}
              style={{
                left: `${leftPct}%`,
                width: `calc(${widthPct}% - 3px)`,
              }}
              onClick={() => onSeekMs(ev.startMs)}
            >
              <span
                className="runway-pill-label"
                style={
                  playheadOffsetPct > 0
                    ? { paddingLeft: `calc(${(playheadOffsetPct / widthPct) * 100}% + 6px)` }
                    : undefined
                }
              >
                {tx.label}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
