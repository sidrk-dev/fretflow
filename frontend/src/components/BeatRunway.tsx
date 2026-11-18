import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Volume2, VolumeX } from 'lucide-react';
import { playMetronomeTick } from '../lib/chordVoicings';
import type { GuitarTransformSettings } from '../lib/musicTransposer';
import { transformChord } from '../lib/musicTransposer';
import type { ChordEvent } from '../types/music';

interface BeatRunwayProps {
  currentTimeMs: number;
  bpm: number;
  beatsMs: number[];
  events: ChordEvent[];
  settings: GuitarTransformSettings;
  isPlaying?: boolean;
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
  isPlaying = false,
  onSeekMs,
}) => {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const [trackWidthPx, setTrackWidthPx] = useState<number>(640);
  const [clickEnabled, setClickEnabled] = useState<boolean>(false);
  const lastBeatIdxRef = useRef<number | null>(null);

  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    const update = () => {
      if (el.clientWidth > 0) setTrackWidthPx(el.clientWidth);
    };
    update();
    if (typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(update);
      ro.observe(el);
      return () => ro.disconnect();
    }
  }, []);

  const { beatIdx, beatInBar } = useMemo(() => {
    if (!beatsMs.length) {
      const beatDur = 60000 / Math.max(60, bpm || 120);
      const idx = Math.floor(Math.max(0, currentTimeMs) / beatDur);
      return { beatIdx: idx, beatInBar: (idx % 4) + 1 };
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
    return { beatIdx: idx, beatInBar: (idx % 4) + 1 };
  }, [beatsMs, bpm, currentTimeMs]);

  useEffect(() => {
    if (!clickEnabled || !isPlaying) {
      lastBeatIdxRef.current = beatIdx;
      return;
    }
    if (lastBeatIdxRef.current !== null && beatIdx !== lastBeatIdxRef.current) {
      playMetronomeTick(beatInBar === 1);
    }
    lastBeatIdxRef.current = beatIdx;
  }, [beatIdx, beatInBar, clickEnabled, isPlaying]);

  const visibleEvents = useMemo(() => {
    const startWin = currentTimeMs - PAST_WINDOW_MS;
    const endWin = currentTimeMs + FUTURE_WINDOW_MS;
    return events.filter((ev) => ev.endMs > startWin && ev.startMs < endWin);
  }, [events, currentTimeMs]);

  return (
    <div className="beat-runway-bar" aria-label="Beat pulse and upcoming chord runway">
      <div className="metronome-cluster" title={`${bpm || 120} BPM`}>
        <button
          type="button"
          className={`metronome-click-btn ${clickEnabled ? 'active' : ''}`}
          aria-label="Toggle audible metronome click"
          aria-pressed={clickEnabled}
          title={clickEnabled ? 'Mute beat metronome click' : 'Enable audible beat metronome click'}
          onClick={() => setClickEnabled((prev) => !prev)}
        >
          {clickEnabled ? <Volume2 size={12} /> : <VolumeX size={12} />}
        </button>
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

      <div className="runway-track" ref={trackRef}>
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

          const playheadOffsetPct = isCurrent ? Math.max(0, PLAYHEAD_PCT - leftPct) : 0;
          const pillWidthPx = Math.max(0, (widthPct / 100) * trackWidthPx - 3);
          const playheadOffsetPx = (playheadOffsetPct / 100) * trackWidthPx;
          const availableTextPx =
            playheadOffsetPct > 0 ? pillWidthPx - playheadOffsetPx - 14 : pillWidthPx - 12;
          const minNeededPx = Math.max(12, tx.label.length * 7.8 + 4);
          const hideLabel = availableTextPx < minNeededPx;

          return (
            <button
              key={`${ev.startMs}-${i}`}
              type="button"
              className={`runway-chord-pill ${isCurrent ? 'is-now' : ''}`}
              style={{
                left: `${leftPct}%`,
                width: `calc(${widthPct}% - 3px)`,
              }}
              title={tx.label}
              onClick={() => onSeekMs(ev.startMs)}
            >
              {!hideLabel && (
                <span
                  className="runway-pill-label"
                  style={
                    playheadOffsetPct > 0
                      ? {
                          paddingLeft: `calc(${(playheadOffsetPct / widthPct) * 100}% + 8px)`,
                        }
                      : undefined
                  }
                >
                  {tx.label}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};
