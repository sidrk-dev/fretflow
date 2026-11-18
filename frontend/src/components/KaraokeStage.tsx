import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDownCircle, Guitar, Music2, Play, Repeat } from 'lucide-react';
import type { LoopRange } from '../hooks/usePlaybackClock';
import { getGuitarVoicings, strumGuitarVoicing } from '../lib/chordVoicings';
import type { GuitarTransformSettings } from '../lib/musicTransposer';
import { transformChord } from '../lib/musicTransposer';
import type {
  ChordAnchor,
  LyricLine,
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

  // Locate active line or instrumental section ID
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

  // Smoothly center active lyric line unless guitarist scrolled manually
  useEffect(() => {
    if (userPausedAutoScroll || !activeTargetId || !activeElementRef.current || !scrollerRef.current) {
      return;
    }
    const container = scrollerRef.current;
    const el = activeElementRef.current;
    const targetTop = el.offsetTop - container.clientHeight * 0.34;
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
        <div className="welcome-hero">
          <div className="welcome-badge">
            <Guitar size={15} />
            <span>Ultimate Guitar × Synced YouTube Karaoke</span>
          </div>
          <h1>Strum along to any song on YouTube — perfectly in sync.</h1>
          <p>
            Search any song above or pick a guitar classic below. FretFlow pulls the YouTube video,
            auto-corrects music-video intro skits via SponsorBlock, fetches word-by-word lyrics, and
            detects beat-synced guitar chords with automatic Capo recommendations.
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

                      // Word-by-word karaoke rendering with chords anchored above specific words
                      if (line.words.length > 0) {
                        const chordsByWord = new Map<number, ChordAnchor[]>();
                        line.chords.forEach((ch) => {
                          const wi = Math.min(
                            line.words.length - 1,
                            Math.max(0, ch.wordIndex ?? 0)
                          );
                          const existing = chordsByWord.get(wi) ?? [];
                          existing.push(ch);
                          chordsByWord.set(wi, existing);
                        });

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
                              {line.words.map((w, wi) => {
                                const attachedChords = chordsByWord.get(wi) ?? [];
                                let fillPct = 0;
                                if (currentTimeMs >= w.endMs) fillPct = 100;
                                else if (currentTimeMs > w.startMs) {
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
                                  <span key={`${line.id}-w-${wi}`} className="word-chord-stack">
                                    {hasAnyChordsOnLine && (
                                      <span className="chord-above-slot">
                                        {attachedChords.map((ch, ci) => {
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
                                              key={ci}
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
                                    <span
                                      className={`karaoke-word ${
                                        fillPct > 0 && fillPct < 100 ? 'word-singing' : ''
                                      } ${fillPct >= 100 ? 'word-sung' : ''}`}
                                      style={{ '--fill-pct': `${fillPct}%` } as React.CSSProperties}
                                      onClick={() => onSeekMs(w.startMs)}
                                    >
                                      {w.text}
                                    </span>
                                  </span>
                                );
                              })}
                            </div>
                          </div>
                        );
                      }

                      // Line-synced rendering with chords anchored above character offsets
                      const segments = splitLineByChordOffsets(line);
                      const hasChords = line.chords.length > 0;
                      let linePct = 0;
                      if (hasLineSync) {
                        if (currentTimeMs >= line.endMs) linePct = 100;
                        else if (currentTimeMs > line.startMs) {
                          linePct = Math.min(
                            100,
                            Math.round(
                              ((currentTimeMs - line.startMs) /
                                Math.max(200, line.endMs - line.startMs)) *
                                100
                            )
                          );
                        }
                      }

                      return (
                        <div
                          key={line.id}
                          ref={isLineActive ? activeElementRef : undefined}
                          className={`lyric-line-row ${isLineActive ? 'is-active' : ''} ${
                            isLinePast ? 'is-past' : ''
                          }`}
                          onClick={() => hasLineSync && onSeekMs(line.startMs)}
                        >
                          <div
                            className="line-segments-wrap"
                            style={{ '--line-pct': `${linePct}%` } as React.CSSProperties}
                          >
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
                                  <span className="line-segment-text">{seg.segment}</span>
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
