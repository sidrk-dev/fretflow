import type { GuitarVoicing } from '../types/music';

/**
 * Curated open-position guitar voicings keyed by `${rootPc}:${quality}`
 * Strings ordered from 6th (Low E) to 1st (High e).
 */
const OPEN_VOICINGS: Record<string, GuitarVoicing[]> = {
  // C family (pc = 0)
  '0:maj': [
    { frets: [-1, 3, 2, 0, 1, 0], fingers: [0, 3, 2, 0, 1, 0], baseFret: 1, label: 'Open C' },
  ],
  '0:maj7': [
    { frets: [-1, 3, 2, 0, 0, 0], fingers: [0, 3, 2, 0, 0, 0], baseFret: 1, label: 'Open Cmaj7' },
  ],
  '0:7': [
    { frets: [-1, 3, 2, 3, 1, 0], fingers: [0, 3, 2, 4, 1, 0], baseFret: 1, label: 'Open C7' },
  ],
  // D family (pc = 2)
  '2:maj': [
    { frets: [-1, -1, 0, 2, 3, 2], fingers: [0, 0, 0, 1, 3, 2], baseFret: 1, label: 'Open D' },
  ],
  '2:min': [
    { frets: [-1, -1, 0, 2, 3, 1], fingers: [0, 0, 0, 2, 3, 1], baseFret: 1, label: 'Open Dm' },
  ],
  '2:7': [
    { frets: [-1, -1, 0, 2, 1, 2], fingers: [0, 0, 0, 2, 1, 3], baseFret: 1, label: 'Open D7' },
  ],
  '2:maj7': [
    {
      frets: [-1, -1, 0, 2, 2, 2],
      fingers: [0, 0, 0, 1, 1, 1],
      baseFret: 1,
      barres: [{ fret: 2, fromString: 3, toString: 5 }],
      label: 'Open Dmaj7',
    },
  ],
  '2:min7': [
    {
      frets: [-1, -1, 0, 2, 1, 1],
      fingers: [0, 0, 0, 2, 1, 1],
      baseFret: 1,
      barres: [{ fret: 1, fromString: 4, toString: 5 }],
      label: 'Open Dm7',
    },
  ],
  '2:sus4': [
    { frets: [-1, -1, 0, 2, 3, 3], fingers: [0, 0, 0, 1, 2, 3], baseFret: 1, label: 'Open Dsus4' },
  ],
  '2:sus2': [
    { frets: [-1, -1, 0, 2, 3, 0], fingers: [0, 0, 0, 1, 3, 0], baseFret: 1, label: 'Open Dsus2' },
  ],
  // E family (pc = 4)
  '4:maj': [
    { frets: [0, 2, 2, 1, 0, 0], fingers: [0, 2, 3, 1, 0, 0], baseFret: 1, label: 'Open E' },
  ],
  '4:min': [
    { frets: [0, 2, 2, 0, 0, 0], fingers: [0, 2, 3, 0, 0, 0], baseFret: 1, label: 'Open Em' },
  ],
  '4:7': [
    { frets: [0, 2, 0, 1, 0, 0], fingers: [0, 2, 0, 1, 0, 0], baseFret: 1, label: 'Open E7' },
  ],
  '4:maj7': [
    { frets: [0, 2, 1, 1, 0, 0], fingers: [0, 3, 1, 2, 0, 0], baseFret: 1, label: 'Open Emaj7' },
  ],
  '4:min7': [
    { frets: [0, 2, 2, 0, 3, 0], fingers: [0, 1, 2, 0, 3, 0], baseFret: 1, label: 'Oasis Em7' },
    { frets: [0, 2, 0, 0, 0, 0], fingers: [0, 2, 0, 0, 0, 0], baseFret: 1, label: 'Easy Em7' },
  ],
  '4:sus4': [
    { frets: [0, 2, 2, 2, 0, 0], fingers: [0, 2, 3, 4, 0, 0], baseFret: 1, label: 'Open Esus4' },
  ],
  // F family (pc = 5)
  '5:maj7': [
    { frets: [-1, -1, 3, 2, 1, 0], fingers: [0, 0, 3, 2, 1, 0], baseFret: 1, label: 'Open Fmaj7' },
  ],
  '5:maj': [
    {
      frets: [1, 3, 3, 2, 1, 1],
      fingers: [1, 3, 4, 2, 1, 1],
      baseFret: 1,
      barres: [{ fret: 1, fromString: 0, toString: 5 }],
      label: 'F Barre',
    },
    {
      frets: [-1, -1, 3, 2, 1, 1],
      fingers: [0, 0, 3, 2, 1, 1],
      baseFret: 1,
      barres: [{ fret: 1, fromString: 4, toString: 5 }],
      label: 'Mini F (Easy)',
    },
  ],
  // G family (pc = 7)
  '7:maj': [
    { frets: [3, 2, 0, 0, 0, 3], fingers: [2, 1, 0, 0, 0, 3], baseFret: 1, label: 'Open G' },
    { frets: [3, 2, 0, 0, 3, 3], fingers: [2, 1, 0, 0, 3, 4], baseFret: 1, label: 'Rock G (4-finger)' },
  ],
  '7:7': [
    { frets: [3, 2, 0, 0, 0, 1], fingers: [3, 2, 0, 0, 0, 1], baseFret: 1, label: 'Open G7' },
  ],
  '7:maj7': [
    { frets: [3, 2, 0, 0, 0, 2], fingers: [3, 2, 0, 0, 0, 1], baseFret: 1, label: 'Open Gmaj7' },
  ],
  '7:sus4': [
    { frets: [3, 3, 0, 0, 1, 3], fingers: [2, 3, 0, 0, 1, 4], baseFret: 1, label: 'Open Gsus4' },
  ],
  // A family (pc = 9)
  '9:maj': [
    { frets: [-1, 0, 2, 2, 2, 0], fingers: [0, 0, 1, 2, 3, 0], baseFret: 1, label: 'Open A' },
  ],
  '9:min': [
    { frets: [-1, 0, 2, 2, 1, 0], fingers: [0, 0, 2, 3, 1, 0], baseFret: 1, label: 'Open Am' },
  ],
  '9:7': [
    { frets: [-1, 0, 2, 0, 2, 0], fingers: [0, 0, 2, 0, 3, 0], baseFret: 1, label: 'Open A7' },
  ],
  '9:maj7': [
    { frets: [-1, 0, 2, 1, 2, 0], fingers: [0, 0, 2, 1, 3, 0], baseFret: 1, label: 'Open Amaj7' },
  ],
  '9:min7': [
    { frets: [-1, 0, 2, 0, 1, 0], fingers: [0, 0, 2, 0, 1, 0], baseFret: 1, label: 'Open Am7' },
  ],
  '9:sus4': [
    { frets: [-1, 0, 2, 2, 3, 0], fingers: [0, 0, 1, 2, 3, 0], baseFret: 1, label: 'Open Asus4' },
  ],
  '9:sus2': [
    { frets: [-1, 0, 2, 2, 0, 0], fingers: [0, 0, 1, 2, 0, 0], baseFret: 1, label: 'Open Asus2' },
  ],
  // B family (pc = 11)
  '11:7': [
    { frets: [-1, 2, 1, 2, 0, 2], fingers: [0, 2, 1, 3, 0, 4], baseFret: 1, label: 'Open B7' },
  ],
  '11:min7': [
    { frets: [-1, 2, 0, 2, 0, 2], fingers: [0, 1, 0, 2, 0, 3], baseFret: 1, label: 'Open Bm7' },
  ],
};

interface BarreShapeSpec {
  rel: [number | null, number | null, number | null, number | null, number | null, number | null];
  fingers: [number, number, number, number, number, number];
  barre?: [number, number, number]; // [fromString, toString, relFretOffset]
}

const E_BARRE_SHAPES: Record<string, BarreShapeSpec> = {
  maj:     { rel: [0, 2, 2, 1, 0, 0],          fingers: [1, 3, 4, 2, 1, 1], barre: [0, 5, 0] },
  min:     { rel: [0, 2, 2, 0, 0, 0],          fingers: [1, 3, 4, 1, 1, 1], barre: [0, 5, 0] },
  '7':     { rel: [0, 2, 0, 1, 0, 0],          fingers: [1, 3, 1, 2, 1, 1], barre: [0, 5, 0] },
  min7:    { rel: [0, 2, 0, 0, 0, 0],          fingers: [1, 3, 1, 1, 1, 1], barre: [0, 5, 0] },
  maj7:    { rel: [0, null, 1, 1, 0, null],    fingers: [1, 0, 3, 4, 2, 0] },
  minmaj7: { rel: [0, 2, 1, 0, 0, 0],          fingers: [1, 3, 2, 1, 1, 1], barre: [0, 5, 0] },
  sus4:    { rel: [0, 2, 2, 2, 0, 0],          fingers: [1, 2, 3, 4, 1, 1], barre: [0, 5, 0] },
  sus2:    { rel: [0, 2, 2, -1, null, null],   fingers: [2, 3, 4, 1, 0, 0] },
  maj6:    { rel: [0, null, 2, 1, 2, null],    fingers: [1, 0, 3, 2, 4, 0] },
  '6':     { rel: [0, null, 2, 1, 2, null],    fingers: [1, 0, 3, 2, 4, 0] },
  min6:    { rel: [0, null, 2, 0, 2, null],    fingers: [1, 0, 3, 1, 4, 0] },
  dim:     { rel: [0, 1, 2, 0, null, null],    fingers: [1, 2, 3, 1, 0, 0] },
  dim7:    { rel: [0, null, -1, 0, -1, null],  fingers: [3, 0, 1, 4, 2, 0] },
  hdim7:   { rel: [0, null, 0, 0, -1, null],   fingers: [2, 0, 3, 4, 1, 0] },
  aug:     { rel: [0, null, 2, 1, 1, null],    fingers: [1, 0, 4, 2, 3, 0] },
  aug7:    { rel: [0, null, 0, 1, 1, null],    fingers: [1, 0, 2, 3, 4, 0] },
  '5':     { rel: [0, 2, 2, null, null, null], fingers: [1, 3, 4, 0, 0, 0] },
};

const A_BARRE_SHAPES: Record<string, BarreShapeSpec> = {
  maj:     { rel: [null, 0, 2, 2, 2, 0],       fingers: [0, 1, 2, 3, 4, 1], barre: [1, 5, 0] },
  min:     { rel: [null, 0, 2, 2, 1, 0],       fingers: [0, 1, 3, 4, 2, 1], barre: [1, 5, 0] },
  '7':     { rel: [null, 0, 2, 0, 2, 0],       fingers: [0, 1, 3, 1, 4, 1], barre: [1, 5, 0] },
  min7:    { rel: [null, 0, 2, 0, 1, 0],       fingers: [0, 1, 3, 1, 2, 1], barre: [1, 5, 0] },
  maj7:    { rel: [null, 0, 2, 1, 2, 0],       fingers: [0, 1, 3, 2, 4, 1], barre: [1, 5, 0] },
  minmaj7: { rel: [null, 0, 2, 1, 1, 0],       fingers: [0, 1, 4, 2, 3, 1], barre: [1, 5, 0] },
  sus4:    { rel: [null, 0, 2, 2, 3, 0],       fingers: [0, 1, 2, 3, 4, 1], barre: [1, 5, 0] },
  sus2:    { rel: [null, 0, 2, 2, 0, 0],       fingers: [0, 1, 3, 4, 1, 1], barre: [1, 5, 0] },
  maj6:    { rel: [null, 0, 2, 2, 2, 2],       fingers: [0, 1, 3, 3, 3, 3], barre: [2, 5, 2] },
  '6':     { rel: [null, 0, 2, 2, 2, 2],       fingers: [0, 1, 3, 3, 3, 3], barre: [2, 5, 2] },
  min6:    { rel: [null, 0, 2, -1, 1, null],   fingers: [0, 2, 4, 1, 3, 0] },
  hdim7:   { rel: [null, 0, 1, 0, 1, null],    fingers: [0, 1, 3, 2, 4, 0] },
  dim7:    { rel: [null, 0, 1, -1, 1, null],   fingers: [0, 2, 3, 1, 4, 0] },
  dim:     { rel: [null, 0, 1, 2, 1, null],    fingers: [0, 1, 2, 4, 3, 0] },
  aug:     { rel: [null, 0, 3, 2, 2, null],    fingers: [0, 1, 4, 2, 3, 0] },
  aug7:    { rel: [null, 0, 3, 0, 2, null],    fingers: [0, 1, 4, 1, 3, 0] },
  '5':     { rel: [null, 0, 2, 2, null, null], fingers: [0, 1, 3, 4, 0, 0] },
};

function buildEShapeBarre(rootPc: number, quality: string): GuitarVoicing {
  let fret = (rootPc - 4 + 12) % 12;
  if (fret === 0) fret = 12;

  const spec = E_BARRE_SHAPES[quality] ?? E_BARRE_SHAPES.maj;
  const frets = spec.rel.map((r) => (r === null ? -1 : fret + r)) as [
    number,
    number,
    number,
    number,
    number,
    number,
  ];
  const fingers = frets.map((f, i) => (f <= 0 ? 0 : spec.fingers[i])) as [
    number,
    number,
    number,
    number,
    number,
    number,
  ];
  const pos = frets.filter((f) => f > 0);
  const minF = pos.length ? Math.min(...pos) : 1;

  return {
    frets,
    fingers,
    baseFret: minF,
    barres:
      spec.barre && fret + spec.barre[2] > 0
        ? [{ fret: fret + spec.barre[2], fromString: spec.barre[0], toString: spec.barre[1] }]
        : undefined,
    label: `E-Shape (Fret ${fret})`,
  };
}

function buildAShapeBarre(rootPc: number, quality: string): GuitarVoicing {
  let fret = (rootPc - 9 + 12) % 12;
  if (fret === 0) fret = 12;

  const spec = A_BARRE_SHAPES[quality] ?? A_BARRE_SHAPES.maj;
  const frets = spec.rel.map((r) => (r === null ? -1 : fret + r)) as [
    number,
    number,
    number,
    number,
    number,
    number,
  ];
  const fingers = frets.map((f, i) => (f <= 0 ? 0 : spec.fingers[i])) as [
    number,
    number,
    number,
    number,
    number,
    number,
  ];
  const pos = frets.filter((f) => f > 0);
  const minF = pos.length ? Math.min(...pos) : 1;

  return {
    frets,
    fingers,
    baseFret: minF,
    barres:
      spec.barre && fret + spec.barre[2] > 0
        ? [{ fret: fret + spec.barre[2], fromString: spec.barre[0], toString: spec.barre[1] }]
        : undefined,
    label: `A-Shape (Fret ${fret})`,
  };
}

export function getGuitarVoicings(rootPc: number, quality: string): GuitarVoicing[] {
  const rpc = ((rootPc % 12) + 12) % 12;
  const key = `${rpc}:${quality}`;
  const openList = OPEN_VOICINGS[key] ?? [];

  const eBarre = buildEShapeBarre(rpc, quality);
  const aBarre = buildAShapeBarre(rpc, quality);

  const barres = eBarre.baseFret <= aBarre.baseFret ? [eBarre, aBarre] : [aBarre, eBarre];
  return [...openList, ...barres];
}

let sharedAudioCtx: AudioContext | null = null;
export const OPEN_STRING_MIDI = [40, 45, 50, 55, 59, 64];

function ensureAudioContext(): AudioContext | null {
  try {
    if (!sharedAudioCtx) {
      sharedAudioCtx = new AudioContext();
    }
    if (sharedAudioCtx.state === 'suspended') {
      void sharedAudioCtx.resume();
    }
    return sharedAudioCtx;
  } catch {
    return null;
  }
}

export function strumGuitarVoicing(voicing: GuitarVoicing, capoFret = 0): void {
  try {
    const ctx = ensureAudioContext();
    if (!ctx) return;
    const now = ctx.currentTime;

    let strumIdx = 0;
    voicing.frets.forEach((fret, stringIndex) => {
      if (fret < 0) return;
      const midi = OPEN_STRING_MIDI[stringIndex] + fret + capoFret;
      const freq = 440 * Math.pow(2, (midi - 69) / 12);
      const t0 = now + strumIdx * 0.028;
      strumIdx += 1;

      const osc1 = ctx.createOscillator();
      const osc2 = ctx.createOscillator();
      const filter = ctx.createBiquadFilter();
      const gain = ctx.createGain();

      osc1.type = 'triangle';
      osc1.frequency.setValueAtTime(freq, t0);
      osc2.type = 'sawtooth';
      osc2.frequency.setValueAtTime(freq, t0);

      filter.type = 'lowpass';
      filter.frequency.setValueAtTime(freq * 4.5, t0);
      filter.frequency.exponentialRampToValueAtTime(freq * 1.4, t0 + 1.4);

      gain.gain.setValueAtTime(0.0001, t0);
      gain.gain.linearRampToValueAtTime(0.14, t0 + 0.012);
      gain.gain.exponentialRampToValueAtTime(0.0008, t0 + 1.85);

      osc1.connect(filter);
      osc2.connect(filter);
      filter.connect(gain);
      gain.connect(ctx.destination);

      osc1.start(t0);
      osc2.start(t0);
      osc1.stop(t0 + 1.9);
      osc2.stop(t0 + 1.9);
    });
  } catch {
    // Ignore WebAudio autoplay restrictions if triggered without gesture
  }
}

export function playReferenceString(stringIndex: number, capoFret = 0): void {
  try {
    const ctx = ensureAudioContext();
    if (!ctx || stringIndex < 0 || stringIndex >= OPEN_STRING_MIDI.length) return;
    const now = ctx.currentTime;
    const midi = OPEN_STRING_MIDI[stringIndex] + capoFret;
    const freq = 440 * Math.pow(2, (midi - 69) / 12);

    const osc1 = ctx.createOscillator();
    const osc2 = ctx.createOscillator();
    const filter = ctx.createBiquadFilter();
    const gain = ctx.createGain();

    osc1.type = 'triangle';
    osc1.frequency.setValueAtTime(freq, now);
    osc2.type = 'sawtooth';
    osc2.frequency.setValueAtTime(freq, now);

    filter.type = 'lowpass';
    filter.frequency.setValueAtTime(freq * 4.0, now);
    filter.frequency.exponentialRampToValueAtTime(freq * 1.25, now + 2.4);

    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.linearRampToValueAtTime(0.18, now + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0008, now + 2.75);

    osc1.connect(filter);
    osc2.connect(filter);
    filter.connect(gain);
    gain.connect(ctx.destination);

    osc1.start(now);
    osc2.start(now);
    osc1.stop(now + 2.8);
    osc2.stop(now + 2.8);
  } catch {
    // Ignore WebAudio restrictions
  }
}

export function playMetronomeTick(isDownbeat: boolean): void {
  try {
    const ctx = ensureAudioContext();
    if (!ctx) return;
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = 'triangle';
    osc.frequency.setValueAtTime(isDownbeat ? 1120 : 780, now);
    osc.frequency.exponentialRampToValueAtTime(isDownbeat ? 680 : 480, now + 0.032);

    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.linearRampToValueAtTime(isDownbeat ? 0.095 : 0.055, now + 0.003);
    gain.gain.exponentialRampToValueAtTime(0.0005, now + 0.038);

    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 0.042);
  } catch {
    // Ignore WebAudio restrictions
  }
}
