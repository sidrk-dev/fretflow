export type SearchResultType = 'studio' | 'video' | 'live';

export interface SearchResultItem {
  videoId: string;
  title: string;
  artist: string;
  album: string;
  durationSec: number;
  durationText: string;
  thumbnailUrl: string;
  resultType: SearchResultType;
  viewsText: string;
}

export interface SearchResponse {
  query: string;
  results: SearchResultItem[];
}

export interface LyricWord {
  text: string;
  startMs: number;
  endMs: number;
}

export interface ChordAnchor {
  harte: string;
  rootPc: number;
  quality: string;
  bassPc: number | null;
  display: string;
  startMs: number;
  endMs: number;
  wordIndex: number | null;
  charOffset: number | null;
  confidence: number;
}

export interface LyricLine {
  id: string;
  startMs: number;
  endMs: number;
  text: string;
  words: LyricWord[];
  chords: ChordAnchor[];
}

export interface InstrumentalBarChord {
  harte: string;
  rootPc: number;
  quality: string;
  bassPc: number | null;
  display: string;
  startMs: number;
  endMs: number;
  beats: number;
}

export interface SongSection {
  id: string;
  name: string;
  kind: 'lyrics' | 'instrumental';
  startMs: number;
  endMs: number;
  lines: LyricLine[];
  instrumentalChords: InstrumentalBarChord[];
}

export interface ChordEvent {
  harte: string;
  rootPc: number;
  quality: string;
  bassPc: number | null;
  display: string;
  startMs: number;
  endMs: number;
  confidence: number;
}

export interface CapoOption {
  capoFret: number;
  score: number;
  openChordRatio: number;
  keyLabel: string;
  previewChords: string[];
  isRecommended: boolean;
}

export interface SkipSegment {
  category: string;
  startMs: number;
  endMs: number;
}

export type LyricsSource =
  | 'betterlyrics_ttml'
  | 'lrclib_word'
  | 'lrclib_line'
  | 'syncedlyrics_word'
  | 'syncedlyrics_line'
  | 'plain'
  | 'none';

export interface LyricsPayload {
  source: LyricsSource;
  hasWordSync: boolean;
  hasLineSync: boolean;
  plainText: string;
  sections: SongSection[];
}

export interface ChordsPayload {
  engine: 'fast_cqt_hmm' | 'neural_btc_170';
  bpm: number;
  beatsMs: number[];
  detectedKey: string;
  events: ChordEvent[];
  capoOptions: CapoOption[];
  recommendedCapo: number;
  uniqueChords: string[];
}

export interface SongSession {
  videoId: string;
  title: string;
  artist: string;
  album: string;
  durationSec: number;
  thumbnailUrl: string;
  autoOffsetMs: number;
  manualOffsetMs: number;
  skipSegments: SkipSegment[];
  lyrics: LyricsPayload | null;
  chords: ChordsPayload | null;
  alignedSections: SongSection[];
  audioReady: boolean;
}

export type SessionStage = 'idle' | 'loading_lyrics' | 'lyrics_ready' | 'chords_fast' | 'chords_neural' | 'error';

export interface GuitarVoicing {
  /** 6 strings from low E (6th) to high e (1st): -1 = muted (X), 0 = open (O), >0 = fret number */
  frets: [number, number, number, number, number, number];
  /** Finger numbers 0..4 per string */
  fingers: [number, number, number, number, number, number];
  /** Starting fret shown at top of diagram (1 for open chords, >1 for movable barre shapes) */
  baseFret: number;
  /** Optional barre fret list (relative to baseFret or absolute) */
  barres?: { fret: number; fromString: number; toString: number }[];
  label?: string;
}
