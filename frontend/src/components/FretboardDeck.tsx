import React, { useState } from 'react';
import { ChevronLeft, ChevronRight, Grid2X2, Volume2 } from 'lucide-react';
import {
  getGuitarVoicings,
  playReferenceString,
  strumGuitarVoicing,
} from '../lib/chordVoicings';
import type { GuitarTransformSettings } from '../lib/musicTransposer';
import { transformChord } from '../lib/musicTransposer';
import type { ChordEvent, GuitarVoicing } from '../types/music';

interface FretboardSvgProps {
  chordLabel: string;
  voicing: GuitarVoicing;
  capoFret: number;
  leftHanded?: boolean;
  highlight?: boolean;
  compact?: boolean;
  onStrum?: () => void;
}

const STRING_NAMES = ['E', 'A', 'D', 'G', 'B', 'e'];

export const FretboardSvg: React.FC<FretboardSvgProps> = ({
  chordLabel,
  voicing,
  capoFret,
  leftHanded = false,
  highlight = false,
  compact = false,
  onStrum,
}) => {
  const numStrings = 6;
  const positiveFrets = voicing.frets.filter((f) => f > 0);
  const maxFret = positiveFrets.length ? Math.max(...positiveFrets) : 1;
  const minFret = positiveFrets.length ? Math.min(...positiveFrets) : 1;
  const hasOpen = voicing.frets.includes(0);
  const baseFret =
    hasOpen || (maxFret <= 4 && voicing.baseFret === 1) ? 1 : Math.max(1, minFret);
  const numFrets = Math.max(4, maxFret - baseFret + 1);

  const width = compact ? 124 : 156;
  const height = compact ? 148 : 182;
  const padLeft = compact ? 24 : 28;
  const padRight = 16;
  const padTop = compact ? 32 : 38;
  const padBottom = 20;

  const gridW = width - padLeft - padRight;
  const gridH = height - padTop - padBottom;
  const stringStep = gridW / (numStrings - 1);
  const fretStep = gridH / numFrets;
  const xForString = (si: number) =>
    padLeft + (leftHanded ? numStrings - 1 - si : si) * stringStep;

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
            x={padLeft - 7}
            y={padTop + fretStep * 0.62}
            textAnchor="end"
            className="base-fret-text"
          >
            {baseFret}fr
          </text>
        )}

        {Array.from({ length: numFrets + 1 }).map((_, fi) => (
          <line
            key={`f-${fi}`}
            x1={padLeft}
            y1={padTop + fi * fretStep}
            x2={padLeft + gridW}
            y2={padTop + fi * fretStep}
            stroke="var(--fret-wire)"
            strokeWidth={1}
          />
        ))}

        {Array.from({ length: numStrings }).map((_, di) => {
          const origSi = leftHanded ? numStrings - 1 - di : di;
          const cx = padLeft + di * stringStep;
          return (
            <g key={`s-${di}`}>
              <line
                x1={cx}
                y1={padTop}
                x2={cx}
                y2={padTop + gridH}
                stroke="var(--fret-string)"
                strokeWidth={1.8 - origSi * 0.18}
              />
              <text
                x={cx}
                y={height - 4}
                textAnchor="middle"
                className="string-label-text"
              >
                {STRING_NAMES[origSi]}
              </text>
            </g>
          );
        })}

        {voicing.barres?.map((b, bi) => {
          const relFret = b.fret - baseFret + 1;
          if (relFret < 1 || relFret > numFrets) return null;
          const x1 = xForString(b.fromString);
          const x2 = xForString(b.toString);
          const cy = padTop + (relFret - 0.5) * fretStep;
          return (
            <line
              key={`barre-${bi}`}
              x1={x1}
              y1={cy}
              x2={x2}
              y2={cy}
              stroke={highlight ? 'var(--fret-dot-primary)' : 'var(--fret-dot-secondary)'}
              strokeWidth={compact ? 10 : 12}
              strokeLinecap="round"
              opacity={0.94}
            />
          );
        })}

        {voicing.frets.map((fret, si) => {
          const cx = xForString(si);
          if (fret < 0) {
            return (
              <text key={`m-${si}`} x={cx} y={padTop - 9} textAnchor="middle" className="mute-x">
                ×
              </text>
            );
          }
          if (fret === 0) {
            return (
              <circle
                key={`o-${si}`}
                cx={cx}
                cy={padTop - 12}
                r={4.2}
                fill="none"
                stroke="var(--muted)"
                strokeWidth={1.5}
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
                r={compact ? 7 : 8.5}
                fill={highlight ? 'var(--fret-dot-primary)' : 'var(--fret-dot-secondary)'}
              />
              {finger > 0 && (
                <text x={cx} y={cy + 3.4} textAnchor="middle" className="finger-num-text">
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
          leftHanded={Boolean(settings.leftHanded)}
          highlight={isPrimary}
          compact={!isPrimary}
          onStrum={() => strumGuitarVoicing(activeVoicing, settings.capo)}
        />
      </div>
    );
  };

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

      <div id="all-song-chords-popover" popover="auto" className="chords-dictionary-popover">
        <div className="popover-header">
          <div>
            <h3>
              Song Chord Shapes{' '}
              {settings.capo > 0 && (
                <span style={{ whiteSpace: 'nowrap' }}>(Capo {settings.capo})</span>
              )}
            </h3>
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

        <div className="popover-tuner-bar" role="group" aria-label="Reference guitar ear tuner">
          <span className="tuner-label">
            Ear Tuner {settings.capo > 0 ? `(w/ Capo ${settings.capo})` : '(Standard)'}
          </span>
          <div className="tuner-strings">
            {STRING_NAMES.map((name, si) => (
              <button
                key={`${name}-${si}`}
                type="button"
                className="tuner-string-btn"
                title={`Pluck ${name} string reference tone`}
                onClick={() => playReferenceString(si, settings.capo)}
              >
                <Volume2 size={11} />
                <span>{name}</span>
              </button>
            ))}
          </div>
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
                leftHanded={Boolean(settings.leftHanded)}
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
