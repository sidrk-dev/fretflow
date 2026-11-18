import React from 'react';
import { Sparkles, Wand2 } from 'lucide-react';
import type { GuitarTransformSettings } from '../lib/musicTransposer';
import type { CapoOption, LyricsSource } from '../types/music';

interface GuitarToolbarProps {
  settings: GuitarTransformSettings;
  onChangeSettings: (next: GuitarTransformSettings) => void;
  capoOptions: CapoOption[];
  recommendedCapo: number;
  detectedKey: string;
  lyricsSource: LyricsSource | null;
}

const SOURCE_LABELS: Record<LyricsSource, string> = {
  betterlyrics_ttml: 'Word Sync + Sections (TTML)',
  lrclib_word: 'LRCLIB Word Sync',
  lrclib_line: 'LRCLIB Line Sync',
  syncedlyrics_word: 'Enhanced Word LRC',
  syncedlyrics_line: 'Synced LRC',
  plain: 'Unsynced Plain Lyrics',
  none: 'Instrumental / Chords Only',
};

export const GuitarToolbar: React.FC<GuitarToolbarProps> = ({
  settings,
  onChangeSettings,
  capoOptions,
  recommendedCapo,
  detectedKey,
  lyricsSource,
}) => {
  const recOption = capoOptions.find((o) => o.capoFret === recommendedCapo);
  const showCapoBanner = recommendedCapo > 0 && recOption;

  return (
    <div className="guitar-toolbar">
      <div className="toolbar-left">
        {showCapoBanner && (
          <button
            type="button"
            className={`smart-capo-pill ${settings.capo === recommendedCapo ? 'applied' : ''}`}
            onClick={() =>
              onChangeSettings({
                ...settings,
                capo: settings.capo === recommendedCapo ? 0 : recommendedCapo,
              })
            }
            title="Smart Capo Optimizer scored frets 0–7 for open campfire guitar shapes"
          >
            <Wand2 size={14} />
            <span>
              {settings.capo === recommendedCapo
                ? `Capo ${recommendedCapo} Active (${recOption.previewChords.slice(0, 4).join(' • ')})`
                : `Recommended: Capo ${recommendedCapo} → ${recOption.previewChords.slice(0, 4).join(' • ')}`}
            </span>
          </button>
        )}

        {detectedKey && <span className="key-chip">Concert Key: {detectedKey}</span>}
        {lyricsSource && <span className="source-chip">{SOURCE_LABELS[lyricsSource]}</span>}
      </div>

      <div className="toolbar-controls">
        <div className="stepper-group" aria-label="Capo fret selector">
          <span className="stepper-label">Capo</span>
          <button
            type="button"
            className="stepper-btn"
            onClick={() => onChangeSettings({ ...settings, capo: Math.max(0, settings.capo - 1) })}
            disabled={settings.capo <= 0}
          >
            −
          </button>
          <span className="stepper-value">{settings.capo === 0 ? 'Off' : `Fret ${settings.capo}`}</span>
          <button
            type="button"
            className="stepper-btn"
            onClick={() => onChangeSettings({ ...settings, capo: Math.min(11, settings.capo + 1) })}
            disabled={settings.capo >= 11}
          >
            +
          </button>
        </div>

        <div className="stepper-group" aria-label="Transpose semitones">
          <span className="stepper-label">Transpose</span>
          <button
            type="button"
            className="stepper-btn"
            onClick={() =>
              onChangeSettings({ ...settings, transpose: Math.max(-6, settings.transpose - 1) })
            }
          >
            −
          </button>
          <span className="stepper-value">
            {settings.transpose > 0 ? `+${settings.transpose}` : settings.transpose} st
          </span>
          <button
            type="button"
            className="stepper-btn"
            onClick={() =>
              onChangeSettings({ ...settings, transpose: Math.min(6, settings.transpose + 1) })
            }
          >
            +
          </button>
        </div>

        <button
          type="button"
          className={`simplify-toggle-btn ${settings.simplify ? 'active' : ''}`}
          onClick={() => onChangeSettings({ ...settings, simplify: !settings.simplify })}
          title="Convert extended 7th/sus/slash chords into beginner-friendly Major & Minor triads"
        >
          <Sparkles size={13} />
          <span>Simplify</span>
        </button>
      </div>
    </div>
  );
};
