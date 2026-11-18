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

const RUNWAY_WINDOW_MS = 8000;

export const BeatRunway: React.FC<BeatRunwayProps> = ({
  currentTimeMs,
  bpm,
  beatsMs,
  events,
  settings,
  onSeekMs,
}) => {
  // Determine active beat index (1..4)
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
    const startWin = currentTimeMs - 1200;
    const endWin = currentTimeMs + RUNWAY_WINDOW_MS;
    return events.filter((ev) => ev.endMs >= startWin && ev.startMs <= endWin);
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
        <div className="runway-playhead" title="Now Playing" />
        {visibleEvents.map((ev, i) => {
          const tx = transformChord(ev.rootPc, ev.quality, ev.bassPc, settings);
          const relStart = ev.startMs - (currentTimeMs - 1200);
          const relEnd = ev.endMs - (currentTimeMs - 1200);
          const totalSpan = RUNWAY_WINDOW_MS + 1200;
          const leftPct = Math.max(0, (relStart / totalSpan) * 100);
          const widthPct = Math.max(4, (Math.min(totalSpan, relEnd) - Math.max(0, relStart)) / totalSpan * 100);
          const isCurrent = currentTimeMs >= ev.startMs && currentTimeMs < ev.endMs;

          return (
            <button
              key={`${ev.startMs}-${i}`}
              type="button"
              className={`runway-chord-pill ${isCurrent ? 'is-now' : ''}`}
              style={{ left: `${leftPct}%`, width: `calc(${widthPct}% - 4px)` }}
              onClick={() => onSeekMs(ev.startMs)}
            >
              {tx.label}
            </button>
          );
        })}
      </div>
    </div>
  );
};
