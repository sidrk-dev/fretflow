import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDownCircle, Guitar, Music2, Play, Repeat } from 'lucide-react';
import type { LoopRange } from '../hooks/usePlaybackClock';
import { getGuitarVoicings, strumGuitarVoicing } from '../lib/chordVoicings';
import type { GuitarTransformSettings } from '../lib/musicTransposer';
import { transformChord } from '../lib/musicTransposer';
import type {
  ChordAnchor,
  LyricLine,
  LyricWord,
  SearchResultItem,
  SessionStage,
  SongSection,
} from '../types/music';

interface KaraokeStageProps {
  sections: SongSection[];
  currentTimeMs: number;
  settings: GuitarTransformSettings;
  hasWordSync: boolean;
  hasLineSync: boolean;
  stage: SessionStage;
  loopRange: LoopRange | null;
  onToggleSectionLoop: (sec: SongSection) => void;
  onSeekMs: (ms: number) => void;
  onQuickPickSong: (item: SearchResultItem) => void;
}

const STARTER_SONGS: SearchResultItem[] = [
  {
    videoId: 'bx1Bh8ZvH84',
    title: 'Wonderwall',
    artist: 'Oasis',
    album: "(What's The Story) Morning Glory?",
    durationSec: 278,
    durationText: '4:38',
    thumbnailUrl: 'https://i.ytimg.com/vi/bx1Bh8ZvH84/hqdefault.jpg',
    resultType: 'video',
    viewsText: 'Classic Capo 2 Test (MV w/ 15s Intro)',
  },
  {
    videoId: 'XFkzRNyygfk',
    title: 'Creep',
    artist: 'Radiohead',
    album: 'Pablo Honey',
    durationSec: 239,
    durationText: '3:59',
    thumbnailUrl: 'https://i.ytimg.com/vi/XFkzRNyygfk/hqdefault.jpg',
    resultType: 'video',
    viewsText: 'G • B • C • Cm',
  },
  {
    videoId: 'uJ_1HMAGb4k',
    title: 'Riptide',
    artist: 'Vance Joy',
    album: 'Dream Your Life Away',
    durationSec: 204,
    durationText: '3:24',
    thumbnailUrl: 'https://i.ytimg.com/vi/uJ_1HMAGb4k/hqdefault.jpg',
    resultType: 'video',
    viewsText: 'Capo 1 Campfire Classic',
  },
  {
    videoId: 'xwtdhWltSIg',
    title: 'Losing My Religion',
    artist: 'R.E.M.',
    album: 'Out of Time',
    durationSec: 294,
    durationText: '4:54',
    thumbnailUrl: 'https://i.ytimg.com/vi/xwtdhWltSIg/hqdefault.jpg',
    resultType: 'video',
    viewsText: 'Am • Em • Dm • G',
  },
  {
    videoId: '8AHCfZTRGiI',
    title: 'Hurt',
    artist: 'Johnny Cash',
    album: 'American IV: The Man Comes Around',
    durationSec: 217,
    durationText: '3:37',
    thumbnailUrl: 'https://i.ytimg.com/vi/8AHCfZTRGiI/hqdefault.jpg',
    resultType: 'video',
    viewsText: 'Am • C • D • G',
  },
  {
    videoId: '2Vv-BfVoq4g',
    title: 'Perfect',
    artist: 'Ed Sheeran',
    album: '÷ (Divide)',
    durationSec: 280,
    durationText: '4:40',
    thumbnailUrl: 'https://i.ytimg.com/vi/2Vv-BfVoq4g/hqdefault.jpg',
    resultType: 'video',
    viewsText: 'Capo 1 (G • Em • C • D)',
  },
];

interface WordPhraseChunk {
  chords: ChordAnchor[];
  words: LyricWord[];
}

/**
 * Group lyric words into chord-phrase spans (`[Em7] -> ["I ", "don't ", "believe "]`)
 * so chord badges NEVER inject unnatural mid-word or mid-sentence horizontal gaps!
 */
function groupWordsIntoChordPhrases(line: LyricLine): WordPhraseChunk[] {
  const words = line.words;
  if (!words.length) return [];
  if (!line.chords.length) {
    return [{ chords: [], words }];
  }

  const chordsByWord = new Map<number, ChordAnchor[]>();
  for (const ch of line.chords) {
    const wi = Math.min(words.length - 1, Math.max(0, ch.wordIndex ?? 0));
    const list = chordsByWord.get(wi) ?? [];
    list.push(ch);
    chordsByWord.set(wi, list);
  }

  const splitIndices = Array.from(chordsByWord.keys()).sort((a, b) => a - b);
  const chunks: WordPhraseChunk[] = [];

  if (splitIndices[0] > 0) {
    chunks.push({ chords: [], words: words.slice(0, splitIndices[0]) });
  }

  for (let i = 0; i < splitIndices.length; i++) {
    const startWi = splitIndices[i];
    const endWi = i + 1 < splitIndices.length ? splitIndices[i + 1] : words.length;
    chunks.push({
      chords: chordsByWord.get(startWi) ?? [],
      words: words.slice(startWi, endWi),
    });
  }

  return chunks;
}

function splitLineByChordOffsets(
  line: LyricLine
): { anchor: ChordAnchor | null; segment: string }[] {
  const text = line.text;
  if (!line.chords.length) {
    return [{ anchor: null, segment: text }];
  }

  const sorted = [...line.chords].sort(
    (a, b) => (a.charOffset ?? 0) - (b.charOffset ?? 0)
  );
  const chunks: { anchor: ChordAnchor | null; segment: string }[] = [];
  let cursor = 0;

  sorted.forEach((ch, idx) => {
    const pos = Math.min(text.length, Math.max(cursor, ch.charOffset ?? 0));
    if (idx === 0 && pos > 0) {
      chunks.push({ anchor: null, segment: text.slice(0, pos) });
      cursor = pos;
    }
    const nextPos =
      idx + 1 < sorted.length
        ? Math.min(text.length, Math.max(pos + 1, sorted[idx + 1].charOffset ?? text.length))
        : text.length;
    chunks.push({ anchor: ch, segment: text.slice(cursor, nextPos) || '\u00A0\u00A0' });
    cursor = nextPos;
  });

  return chunks;
}

export const KaraokeStage: React.FC<KaraokeStageProps> = ({
  sections,
  currentTimeMs,
  settings,
  hasLineSync,
  stage,
  loopRange,
  onToggleSectionLoop,
  onSeekMs,
  onQuickPickSong,
}) => {
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const activeElementRef = useRef<HTMLDivElement | null>(null);
  const [userPausedAutoScroll, setUserPausedAutoScroll] = useState(false);
  const pauseTimerRef = useRef<number | null>(null);

  const handleUserScroll = () => {
    setUserPausedAutoScroll(true);
    if (pauseTimerRef.current) window.clearTimeout(pauseTimerRef.current);
    pauseTimerRef.current = window.setTimeout(() => {
      setUserPausedAutoScroll(false);
    }, 6000);
  };

  useEffect(() => {
    return () => {
      if (pauseTimerRef.current) window.clearTimeout(pauseTimerRef.current);
    };
  }, []);

  const activeTargetId = useMemo(() => {
    if (!hasLineSync && sections.every((s) => s.kind === 'lyrics')) return null;
    for (const sec of sections) {
      if (sec.kind === 'instrumental') {
        if (currentTimeMs >= sec.startMs && currentTimeMs <= sec.endMs) {
          return sec.id;
        }
      } else {
        for (const ln of sec.lines) {
          if (currentTimeMs >= ln.startMs - 250 && currentTimeMs <= ln.endMs + 350) {
            return ln.id;
          }
        }
      }
    }
    return null;
  }, [sections, currentTimeMs, hasLineSync]);

  useEffect(() => {
    if (
      userPausedAutoScroll ||
      !activeTargetId ||
      !activeElementRef.current ||
      !scrollerRef.current
    ) {
      return;
    }
    const container = scrollerRef.current;
    const el = activeElementRef.current;
    const targetTop = el.offsetTop - container.clientHeight * 0.32;
    container.scrollTo({ top: Math.max(0, targetTop), behavior: 'smooth' });
  }, [activeTargetId, userPausedAutoScroll]);

  const strumAnchor = (anchor: ChordAnchor) => {
    const tx = transformChord(anchor.rootPc, anchor.quality, anchor.bassPc, settings);
    const v = getGuitarVoicings(tx.shapeRootPc, tx.shapeQuality)[0];
    strumGuitarVoicing(v, settings.capo);
  };

  if (stage === 'idle') {
    return (
      <div className="karaoke-stage welcome-stage">
        <div className="welcome-inner">
          <div className="welcome-hero">
            <div className="welcome-badge">
              <Guitar size={15} />
              <span>Ultimate Guitar × Synced YouTube Karaoke</span>
            </div>
            <h1>Strum along to any song on YouTube — perfectly in sync.</h1>
            <p>
              Search any song above or pick a guitar classic below. FretFlow pulls the YouTube
              video, auto-corrects music-video intro skits via SponsorBlock, fetches word-by-word
              lyrics, and detects beat-synced guitar chords with automatic Capo recommendations.
            </p>
          </div>

          <div className="starter-grid">
            {STARTER_SONGS.map((song) => (
              <button
                key={song.videoId}
                type="button"
                className="starter-card"
                onClick={() => onQuickPickSong(song)}
              >
                <img
                  src={song.thumbnailUrl}
                  alt=""
                  width={96}
                  height={72}
                  className="starter-thumb"
                />
                <div className="starter-info">
                  <span className="starter-title">{song.title}</span>
                  <span className="starter-artist">{song.artist}</span>
                  <span className="starter-hint">{song.viewsText}</span>
                </div>
                <span className="starter-play-circle">
                  <Play size={15} fill="currentColor" />
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="karaoke-stage"
      ref={scrollerRef}
      onWheel={handleUserScroll}
      onTouchMove={handleUserScroll}
    >
      {userPausedAutoScroll && (
        <button
          type="button"
          className="resume-scroll-pill"
          onClick={() => setUserPausedAutoScroll(false)}
        >
          <ArrowDownCircle size={14} />
          <span>Resume Auto-Scroll</span>
        </button>
      )}

      {sections.length === 0 ? (
        <div className="empty-sheet-state">
          <Music2 size={28} />
          <p>Loading synchronized lyrics & neural guitar chords…</p>
        </div>
      ) : (
        <div className="sheet-content">
          {sections.map((sec) => {
            const isLoopingThis =
              loopRange !== null &&
              Math.abs(loopRange.startMs - sec.startMs) < 150 &&
              Math.abs(loopRange.endMs - sec.endMs) < 150;
            const isInstActive = activeTargetId === sec.id;

            return (
              <section key={sec.id} className="song-section-block">
                <div className="section-header-row">
                  <button
                    type="button"
                    className="section-jump-label"
                    onClick={() => onSeekMs(sec.startMs)}
                    title="Jump to start of section"
                  >
                    [{sec.name}]
                  </button>
                  <button
                    type="button"
                    className={`section-loop-btn ${isLoopingThis ? 'active' : ''}`}
                    onClick={() => onToggleSectionLoop(sec)}
                  >
                    <Repeat size={12} />
                    <span>{isLoopingThis ? 'Looping Section' : 'Loop Section'}</span>
                  </button>
                </div>

                {sec.kind === 'instrumental' ? (
                  <div
                    ref={isInstActive ? activeElementRef : undefined}
                    className={`instrumental-bar-grid ${isInstActive ? 'is-section-active' : ''}`}
                  >
                    {sec.instrumentalChords.map((bar, bi) => {
                      const tx = transformChord(bar.rootPc, bar.quality, bar.bassPc, settings);
                      const barActive =
                        currentTimeMs >= bar.startMs && currentTimeMs < bar.endMs;
                      return (
                        <button
                          key={`${bar.startMs}-${bi}`}
                          type="button"
                          className={`inst-measure-cell ${barActive ? 'active' : ''}`}
                          onClick={() => onSeekMs(bar.startMs)}
                        >
                          <span className="inst-chord-name">{tx.label}</span>
                          <span className="inst-beat-slashes">
                            {'/ '.repeat(Math.min(8, Math.max(1, bar.beats))).trim()}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="section-lines">
                    {sec.lines.map((line) => {
                      const isLineActive = activeTargetId === line.id;
                      const isLinePast = hasLineSync && currentTimeMs > line.endMs;

                      if (line.words.length > 0) {
                        const phraseChunks = groupWordsIntoChordPhrases(line);
                        const hasAnyChordsOnLine = line.chords.length > 0;

                        return (
                          <div
                            key={line.id}
                            ref={isLineActive ? activeElementRef : undefined}
                            className={`lyric-line-row ${isLineActive ? 'is-active' : ''} ${
                              isLinePast ? 'is-past' : ''
                            }`}
                          >
                            <div className="word-tokens-wrap">
                              {phraseChunks.map((chunk, ci) => (
                                <span key={`${line.id}-p-${ci}`} className="word-chord-stack">
                                  {hasAnyChordsOnLine && (
                                    <span className="chord-above-slot">
                                      {chunk.chords.map((ch, chi) => {
                                        const tx = transformChord(
                                          ch.rootPc,
                                          ch.quality,
                                          ch.bassPc,
                                          settings
                                        );
                                        const chActive =
                                          currentTimeMs >= ch.startMs - 80 &&
                                          currentTimeMs < ch.endMs;
                                        return (
                                          <button
                                            key={chi}
                                            type="button"
                                            className={`inline-chord-badge ${
                                              chActive ? 'chord-now' : ''
                                            }`}
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              strumAnchor(ch);
                                            }}
                                            title="Click to hear chord voicing"
                                          >
                                            {tx.label}
                                          </button>
                                        );
                                      })}
                                    </span>
                                  )}
                                  <span className="phrase-words-row">
                                    {chunk.words.map((w, wi) => {
                                      let fillPct = 0;
                                      if (w.endMs === 0 || currentTimeMs >= w.endMs) {
                                        fillPct = 100;
                                      } else if (currentTimeMs > w.startMs) {
                                        fillPct = Math.min(
                                          100,
                                          Math.round(
                                            ((currentTimeMs - w.startMs) /
                                              Math.max(60, w.endMs - w.startMs)) *
                                              100
                                          )
                                        );
                                      }

                                      return (
                                        <span
                                          key={wi}
                                          className={`karaoke-word ${
                                            fillPct <= 0
                                              ? 'word-upcoming'
                                              : fillPct < 100
                                                ? 'word-singing'
                                                : 'word-sung'
                                          }`}
                                          style={
                                            { '--fill-pct': `${fillPct}%` } as React.CSSProperties
                                          }
                                          onClick={() => onSeekMs(w.startMs)}
                                        >
                                          {w.text}
                                        </span>
                                      );
                                    })}
                                  </span>
                                </span>
                              ))}
                            </div>
                          </div>
                        );
                      }

                      // Line-synced rendering with smooth line progress sweep
                      const segments = splitLineByChordOffsets(line);
                      const hasChords = line.chords.length > 0;
                      const isLineSung = hasLineSync && currentTimeMs >= line.endMs;

                      return (
                        <div
                          key={line.id}
                          ref={isLineActive ? activeElementRef : undefined}
                          className={`lyric-line-row ${isLineActive ? 'is-active' : ''} ${
                            isLinePast ? 'is-past' : ''
                          }`}
                          onClick={() => hasLineSync && onSeekMs(line.startMs)}
                        >
                          <div className="line-segments-wrap">
                            {segments.map((seg, si) => {
                              const ch = seg.anchor;
                              const tx = ch
                                ? transformChord(ch.rootPc, ch.quality, ch.bassPc, settings)
                                : null;
                              const chActive =
                                ch !== null &&
                                currentTimeMs >= ch.startMs - 80 &&
                                currentTimeMs < ch.endMs;

                              return (
                                <span key={si} className="word-chord-stack">
                                  {hasChords && (
                                    <span className="chord-above-slot">
                                      {ch && tx && (
                                        <button
                                          type="button"
                                          className={`inline-chord-badge ${
                                            chActive ? 'chord-now' : ''
                                          }`}
                                          onClick={(e) => {
                                            e.stopPropagation();
                                            strumAnchor(ch);
                                          }}
                                        >
                                          {tx.label}
                                        </button>
                                      )}
                                    </span>
                                  )}
                                  <span
                                    className={`line-segment-text ${
                                      isLineActive ? 'line-active-highlight' : ''
                                    } ${isLineSung ? 'line-sung' : ''}`}
                                  >
                                    {seg.segment}
                                  </span>
                                </span>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
};
