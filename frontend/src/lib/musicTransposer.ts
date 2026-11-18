export interface GuitarTransformSettings {
  capo: number;
  transpose: number;
  simplify: boolean;
  leftHanded?: boolean;
}

export interface TransformedChord {
  shapeRootPc: number;
  shapeQuality: string;
  shapeBassPc: number | null;
  label: string;
  concertLabel: string;
}

const MAJOR_NAMES = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B'];
const MINOR_NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'G#', 'A', 'Bb', 'B'];

const MINOR_QUALITIES = new Set([
  'min',
  'min7',
  'min6',
  'minmaj7',
  'hdim7',
  'dim',
  'dim7',
]);

const SUFFIX_MAP: Record<string, string> = {
  maj: '',
  min: 'm',
  '7': '7',
  maj7: 'maj7',
  min7: 'm7',
  sus4: 'sus4',
  sus2: 'sus2',
  dim: 'dim',
  dim7: 'dim7',
  hdim7: 'm7b5',
  aug: 'aug',
  aug7: '7#5',
  maj6: '6',
  '6': '6',
  min6: 'm6',
  minmaj7: 'm(maj7)',
  '5': '5',
};

export function simplifyQuality(quality: string): string {
  if (quality === 'min7' || quality === 'min6' || quality === 'minmaj7' || quality === 'hdim7' || quality === 'dim' || quality === 'dim7') {
    return 'min';
  }
  return 'maj';
}

export function formatChordLabel(
  rootPc: number,
  quality: string,
  bassPc: number | null = null
): string {
  const rpc = ((rootPc % 12) + 12) % 12;
  const q = quality in SUFFIX_MAP ? quality : 'maj';
  const names = MINOR_QUALITIES.has(q) ? MINOR_NAMES : MAJOR_NAMES;
  const suffix = SUFFIX_MAP[q] ?? '';
  let out = `${names[rpc]}${suffix}`;
  if (bassPc !== null && bassPc !== undefined) {
    const bpc = ((bassPc % 12) + 12) % 12;
    if (bpc !== rpc) {
      out += `/${MAJOR_NAMES[bpc]}`;
    }
  }
  return out;
}

export function transformChord(
  rootPc: number,
  quality: string,
  bassPc: number | null,
  settings: GuitarTransformSettings
): TransformedChord {
  const concertRpc = (((rootPc + settings.transpose) % 12) + 12) % 12;
  const concertBass =
    bassPc !== null && bassPc !== undefined
      ? (((bassPc + settings.transpose) % 12) + 12) % 12
      : null;

  const shapeRootPc = (((concertRpc - settings.capo) % 12) + 12) % 12;
  const shapeQuality = settings.simplify ? simplifyQuality(quality) : quality;
  const shapeBassPc =
    settings.simplify || concertBass === null
      ? null
      : (((concertBass - settings.capo) % 12) + 12) % 12;

  return {
    shapeRootPc,
    shapeQuality,
    shapeBassPc,
    label: formatChordLabel(shapeRootPc, shapeQuality, shapeBassPc),
    concertLabel: formatChordLabel(concertRpc, quality, concertBass),
  };
}
