import React, { useState } from 'react';
import {
  FastForward,
  Pause,
  Play,
  Repeat,
  Rewind,
  SkipForward,
  TimerReset,
  X,
} from 'lucide-react';
import type { LoopRange } from '../hooks/usePlaybackClock';
import type { SkipSegment } from '../types/music';

interface PracticeBarProps {
  isPlaying: boolean;
  currentTimeMs: number;
  durationMs: number;
  playbackRate: number;
  loopRange: LoopRange | null;
  autoOffsetMs: number;
  manualOffsetMs: number;
  skipSegments: SkipSegment[];
  firstVocalStudioMs: number | null;
  onTogglePlay: () => void;
  onSeekMs: (ms: number) => void;
  onChangeRate: (rate: number) => void;
  onSetLoopRange: (range: LoopRange | null) => void;
  onUpdateManualOffset: (nextManualMs: number) => void;
}

const SPEEDS = [0.5, 0.75, 0.9, 1.0, 1.25];

function formatClock(ms: number): string {
  const totalSec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export const PracticeBar: React.FC<PracticeBarProps> = ({
  isPlaying,
  currentTimeMs,
  durationMs,
  playbackRate,
  loopRange,
  autoOffsetMs,
  manualOffsetMs,
  skipSegments,
  firstVocalStudioMs,
  onTogglePlay,
  onSeekMs,
  onChangeRate,
  onSetLoopRange,
  onUpdateManualOffset,
}) => {
  const [pointAMs, setPointAMs] = useState<number | null>(null);

  // Check if playback is currently inside a SponsorBlock non-music skit segment
  const activeSkipSeg = skipSegments.find(
    (seg) => currentTimeMs >= seg.startMs && currentTimeMs < seg.endMs - 400
  );

  const handleABClick = () => {
    if (loopRange) {
      onSetLoopRange(null);
      setPointAMs(null);
      return;
    }
    if (pointAMs === null) {
      setPointAMs(currentTimeMs);
    } else {
      const start = Math.min(pointAMs, currentTimeMs);
      const end = Math.max(pointAMs + 1500, currentTimeMs);
      onSetLoopRange({ startMs: start, endMs: end, label: 'Custom A–B' });
      setPointAMs(null);
    }
  };

  const handleTapFirstLyric = () => {
    if (firstVocalStudioMs === null) return;
    // We want: firstVocalStudioMs + autoOffsetMs + newManualOffsetMs === currentTimeMs
    const desiredManual = currentTimeMs - firstVocalStudioMs - autoOffsetMs;
    onUpdateManualOffset(Math.round(desiredManual));
  };

  const totalOffsetSec = ((autoOffsetMs + manualOffsetMs) / 1000).toFixed(1);

  return (
    <footer className="practice-bar" aria-label="Playback and practice controls">
      {/* Timeline Scrubber */}
      <div className="scrubber-row">
        <span className="time-label">{formatClock(currentTimeMs)}</span>
        <div className="scrubber-track-wrap">
          <input
            type="range"
            min={0}
            max={Math.max(1000, durationMs)}
            value={Math.min(durationMs || 1000, currentTimeMs)}
            onChange={(e) => onSeekMs(Number(e.target.value))}
            aria-label="Song timeline"
            className="timeline-slider"
          />
          {loopRange && durationMs > 0 && (
            <div
              className="scrubber-loop-highlight"
              style={{
                left: `${(loopRange.startMs / durationMs) * 100}%`,
                width: `${Math.max(1, ((loopRange.endMs - loopRange.startMs) / durationMs) * 100)}%`,
              }}
            />
          )}
        </div>
        <span className="time-label">{formatClock(durationMs)}</span>
      </div>

      {/* Main Controls Row */}
      <div className="transport-controls-row">
        {/* Left: Transport + Skip Intro */}
        <div className="transport-cluster">
          <button
            type="button"
            className="transport-icon-btn"
            onClick={() => onSeekMs(Math.max(0, currentTimeMs - 5000))}
            title="Rewind 5 seconds"
            aria-label="Rewind 5 seconds"
          >
            <Rewind size={16} />
          </button>

          <button
            type="button"
            className="play-main-btn"
            onClick={onTogglePlay}
            aria-label={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? <Pause size={18} fill="currentColor" /> : <Play size={18} fill="currentColor" />}
          </button>

          <button
            type="button"
            className="transport-icon-btn"
            onClick={() => onSeekMs(Math.min(durationMs, currentTimeMs + 5000))}
            title="Forward 5 seconds"
            aria-label="Forward 5 seconds"
          >
            <FastForward size={16} />
          </button>

          {activeSkipSeg && (
            <button
              type="button"
              className="skip-skit-btn"
              onClick={() => onSeekMs(activeSkipSeg.endMs)}
            >
              <SkipForward size={14} />
              <span>Skip Intro Skit ({Math.round(activeSkipSeg.endMs / 1000)}s)</span>
            </button>
          )}
        </div>

        {/* Center: A-B Loop + Speed Trainer */}
        <div className="practice-cluster">
          <button
            type="button"
            className={`loop-ab-btn ${loopRange ? 'active' : pointAMs !== null ? 'armed' : ''}`}
            onClick={handleABClick}
          >
            <Repeat size={14} />
            <span>
              {loopRange
                ? `Loop: ${loopRange.label}`
                : pointAMs !== null
                  ? `Set B (A=${formatClock(pointAMs)})`
                  : 'A–B Loop'}
            </span>
            {loopRange && <X size={13} />}
          </button>

          <div className="speed-pills" role="group" aria-label="Playback speed">
            {SPEEDS.map((spd) => (
              <button
                key={spd}
                type="button"
                className={`speed-pill ${playbackRate === spd ? 'active' : ''}`}
                onClick={() => onChangeRate(spd)}
              >
                {spd}x
              </button>
            ))}
          </div>
        </div>

        {/* Right: Lyric Sync Nudge + Tap Sync */}
        <div className="sync-cluster" aria-label="Lyric timing offset adjustment">
          <span className="sync-title" title={autoOffsetMs > 0 ? `Includes +${(autoOffsetMs / 1000).toFixed(1)}s SponsorBlock intro offset` : 'Adjust lyric sync timing'}>
            Sync {Number(totalOffsetSec) >= 0 ? `+${totalOffsetSec}s` : `${totalOffsetSec}s`}
          </span>
          <button
            type="button"
            className="nudge-btn"
            onClick={() => onUpdateManualOffset(manualOffsetMs - 250)}
            title="Show lyrics 250ms earlier ([ key)"
          >
            −0.25s
          </button>
          <button
            type="button"
            className="nudge-btn"
            onClick={() => onUpdateManualOffset(manualOffsetMs + 250)}
            title="Delay lyrics 250ms later (] key)"
          >
            +0.25s
          </button>
          {firstVocalStudioMs !== null && (
            <button
              type="button"
              className="tap-sync-btn"
              onClick={handleTapFirstLyric}
              title="Click right when the singer sings the very first word of the song"
            >
              <TimerReset size={13} />
              <span>Tap 1st Word</span>
            </button>
          )}
          {manualOffsetMs !== 0 && (
            <button
              type="button"
              className="nudge-reset-btn"
              onClick={() => onUpdateManualOffset(0)}
              title="Reset manual sync offset"
            >
              Reset
            </button>
          )}
        </div>
      </div>
    </footer>
  );
};
