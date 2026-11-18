import React, { useState } from 'react';
import { ChevronLeft, ChevronRight, Grid2X2, Volume2 } from 'lucide-react';
import { getGuitarVoicings, strumGuitarVoicing } from '../lib/chordVoicings';
import type { GuitarTransformSettings } from '../lib/musicTransposer';
import { transformChord } from '../lib/musicTransposer';
import type { ChordEvent, GuitarVoicing } from '../types/music';

interface FretboardSvgProps {
  chordLabel: string;
  voicing: GuitarVoicing;
  capoFret: number;
  highlight?: boolean;
  compact?: boolean;
  onStrum?: () => void;
}

const STRING_NAMES = ['E', 'A', 'D', 'G', 'B', 'e'];

export const FretboardSvg: React.FC<FretboardSvgProps> = ({
  chordLabel,
  voicing,
  capoFret,
  highlight = false,
  compact = false,
  onStrum,
}) => {
  const numStrings = 6;
  const numFrets = 4;
  const width = compact ? 132 : 164;
  const height = compact ? 158 : 192;
  const padLeft = compact ? 24 : 28;
  const padRight = 18;
  const padTop = compact ? 34 : 40;
  const padBottom = 22;

  const gridW = width - padLeft - padRight;
  const gridH = height - padTop - padBottom;
  const stringStep = gridW / (numStrings - 1);
  const fretStep = gridH / numFrets;

  const positiveFrets = voicing.frets.filter((f) => f > 0);
  const maxFret = positiveFrets.length ? Math.max(...positiveFrets) : 1;
  const minFret = positiveFrets.length ? Math.min(...positiveFrets) : 1;
  const baseFret = maxFret <= 4 ? 1 : Math.max(1, voicing.baseFret || minFret);

  return (
    <div
      className={`fretboard-card ${highlight ? 'is-active' : ''} ${compact ? 'is-compact' : ''}`}
      onClick={onStrum}
      role={onStrum ? 'button' : undefined}
      tabIndex={onStrum ? 0 : undefined}
      onKeyDown={(e) => {
        if (onStrum && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onStrum();
        }
      }}
      title="Click to strum guitar chord preview"
    >
      <div className="fretboard-title-row">
        <span className="fretboard-chord-name">{chordLabel}</span>
        {onStrum && <Volume2 size={13} className="strum-hint-icon" />}
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        width={width}
        height={height}
        aria-label={`${chordLabel} guitar chord diagram`}
        className="fretboard-svg"
      >
        {/* Nut or Base Fret Label */}
        {baseFret === 1 ? (
          <line
            x1={padLeft - 1}
            y1={padTop}
            x2={padLeft + gridW + 1}
            y2={padTop}
            stroke="currentColor"
            strokeWidth={4.5}
            className="fret-nut"
          />
        ) : (
          <text
            x={padLeft - 8}
            y={padTop + fretStep * 0.62}
            textAnchor="end"
            className="base-fret-text"
          >
            {baseFret}fr
          </text>
        )}

        {/* Horizontal fret wires */}
        {Array.from({ length: numFrets + 1 }).map((_, fi) => (
          <line
            key={`f-${fi}`}
            x1={padLeft}
            y1={padTop + fi * fretStep}
            x2={padLeft + gridW}
            y2={padTop + fi * fretStep}
            stroke="rgba(148, 163, 184, 0.28)"
            strokeWidth={1.2}
          />
        ))}

        {/* Vertical guitar strings (thicker bass -> thinner treble) */}
        {Array.from({ length: numStrings }).map((_, si) => (
          <g key={`s-${si}`}>
            <line
              x1={padLeft + si * stringStep}
              y1={padTop}
              x2={padLeft + si * stringStep}
              y2={padTop + gridH}
              stroke="rgba(226, 232, 240, 0.52)"
              strokeWidth={2.2 - si * 0.24}
            />
            <text
              x={padLeft + si * stringStep}
              y={height - 5}
              textAnchor="middle"
              className="string-label-text"
            >
              {STRING_NAMES[si]}
            </text>
          </g>
        ))}

        {/* Barre bars */}
        {voicing.barres?.map((b, bi) => {
          const relFret = b.fret - baseFret + 1;
          if (relFret < 1 || relFret > numFrets) return null;
          const x1 = padLeft + b.fromString * stringStep;
          const x2 = padLeft + b.toString * stringStep;
          const cy = padTop + (relFret - 0.5) * fretStep;
          return (
            <line
              key={`barre-${bi}`}
              x1={x1}
              y1={cy}
              x2={x2}
              y2={cy}
              stroke={highlight ? '#f59e0b' : '#38bdf8'}
              strokeWidth={compact ? 11 : 13}
              strokeLinecap="round"
              opacity={0.9}
            />
          );
        })}

        {/* Open (O), Muted (X), and Finger Dots */}
        {voicing.frets.map((fret, si) => {
          const cx = padLeft + si * stringStep;
          if (fret < 0) {
            return (
              <text key={`m-${si}`} x={cx} y={padTop - 10} textAnchor="middle" className="mute-x">
                ×
              </text>
            );
          }
          if (fret === 0) {
            return (
              <circle
                key={`o-${si}`}
                cx={cx}
                cy={padTop - 13}
                r={4.5}
                fill="none"
                stroke="#94a3b8"
                strokeWidth={1.6}
              />
            );
          }
          const relFret = fret - baseFret + 1;
          if (relFret < 1 || relFret > numFrets) return null;
          const cy = padTop + (relFret - 0.5) * fretStep;
          const finger = voicing.fingers[si];

          return (
            <g key={`d-${si}`}>
              <circle
                cx={cx}
                cy={cy}
                r={compact ? 7.5 : 9}
                fill={highlight ? '#f59e0b' : '#38bdf8'}
              />
              {finger > 0 && (
                <text x={cx} y={cy + 3.5} textAnchor="middle" className="finger-num-text">
                  {finger}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      <div className="fretboard-sub">
        <span>{voicing.label || 'Standard'}</span>
        {capoFret > 0 && <span className="capo-mini-tag">Capo {capoFret}</span>}
      </div>
    </div>
  );
};

interface FretboardDeckProps {
  currentEvent: ChordEvent | null;
  nextEvent: ChordEvent | null;
  allEvents: ChordEvent[];
  settings: GuitarTransformSettings;
}

export const FretboardDeck: React.FC<FretboardDeckProps> = ({
  currentEvent,
  nextEvent,
  allEvents,
  settings,
}) => {
  const [voicingIdxByChord, setVoicingIdxByChord] = useState<Record<string, number>>({});

  const renderSlot = (ev: ChordEvent | null, roleLabel: string, isPrimary: boolean) => {
    if (!ev) {
      return (
        <div className="fretboard-slot empty-slot">
          <span className="slot-eyebrow">{roleLabel}</span>
          <div className="empty-fretboard-box">Waiting for chord…</div>
        </div>
      );
    }

    const tx = transformChord(ev.rootPc, ev.quality, ev.bassPc, settings);
    const voicings = getGuitarVoicings(tx.shapeRootPc, tx.shapeQuality);
    const vIdx = (voicingIdxByChord[tx.label] ?? 0) % voicings.length;
    const activeVoicing = voicings[vIdx];

    return (
      <div className="fretboard-slot">
        <div className="slot-header-row">
          <span className="slot-eyebrow">{roleLabel}</span>
          {voicings.length > 1 && (
            <div className="voicing-cycler">
              <button
                type="button"
                className="voicing-arrow-btn"
                aria-label="Previous voicing"
                onClick={() =>
                  setVoicingIdxByChord((prev) => ({
                    ...prev,
                    [tx.label]: (vIdx - 1 + voicings.length) % voicings.length,
                  }))
                }
              >
                <ChevronLeft size={13} />
              </button>
              <span className="voicing-count">
                {vIdx + 1}/{voicings.length}
              </span>
              <button
                type="button"
                className="voicing-arrow-btn"
                aria-label="Next voicing"
                onClick={() =>
                  setVoicingIdxByChord((prev) => ({
                    ...prev,
                    [tx.label]: (vIdx + 1) % voicings.length,
                  }))
                }
              >
                <ChevronRight size={13} />
              </button>
            </div>
          )}
        </div>

        <FretboardSvg
          chordLabel={tx.label}
          voicing={activeVoicing}
          capoFret={settings.capo}
          highlight={isPrimary}
          compact={!isPrimary}
          onStrum={() => strumGuitarVoicing(activeVoicing, settings.capo)}
        />
      </div>
    );
  };

  // Deduplicate unique chords in song for the native Popover dictionary
  const uniqueMap = new Map<string, { rootPc: number; quality: string; label: string }>();
  for (const ev of allEvents) {
    const tx = transformChord(ev.rootPc, ev.quality, ev.bassPc, settings);
    if (!uniqueMap.has(tx.label)) {
      uniqueMap.set(tx.label, {
        rootPc: tx.shapeRootPc,
        quality: tx.shapeQuality,
        label: tx.label,
      });
    }
  }
  const uniqueChordItems = Array.from(uniqueMap.values());

  return (
    <section className="fretboard-deck" aria-label="Live guitar chord diagrams">
      <div className="deck-top-bar">
        <span className="deck-heading">Fretboard Guide</span>
        {uniqueChordItems.length > 0 && (
          <button
            type="button"
            popoverTarget="all-song-chords-popover"
            className="all-chords-btn"
          >
            <Grid2X2 size={13} />
            <span>All {uniqueChordItems.length} Chords</span>
          </button>
        )}
      </div>

      <div className="deck-pair">
        {renderSlot(currentEvent, 'PLAYING NOW', true)}
        {renderSlot(nextEvent, 'UP NEXT', false)}
      </div>

      {/* Native HTML Top-Layer Popover for All Chords in the Song */}
      <div id="all-song-chords-popover" popover="auto" className="chords-dictionary-popover">
        <div className="popover-header">
          <div>
            <h3>Song Chord Shapes {settings.capo > 0 ? `(Capo ${settings.capo})` : ''}</h3>
            <p>Click any diagram to hear how the chord sounds on guitar.</p>
          </div>
          <button
            type="button"
            popoverTarget="all-song-chords-popover"
            popoverTargetAction="hide"
            className="popover-close-btn"
          >
            Close
          </button>
        </div>
        <div className="popover-chord-grid">
          {uniqueChordItems.map((item) => {
            const v = getGuitarVoicings(item.rootPc, item.quality)[0];
            return (
              <FretboardSvg
                key={item.label}
                chordLabel={item.label}
                voicing={v}
                capoFret={settings.capo}
                compact
                onStrum={() => strumGuitarVoicing(v, settings.capo)}
              />
            );
          })}
        </div>
      </div>
    </section>
  );
};
