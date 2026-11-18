import React, { useEffect, useMemo, useRef, useState } from 'react';
import { BeatRunway } from './components/BeatRunway';
import { FretboardDeck } from './components/FretboardDeck';
import { GuitarToolbar } from './components/GuitarToolbar';
import { HeaderSearchBar } from './components/HeaderSearchBar';
import { KaraokeStage } from './components/KaraokeStage';
import { PracticeBar } from './components/PracticeBar';
import { type LoopRange, usePlaybackClock } from './hooks/usePlaybackClock';
import { useSongSession } from './hooks/useSongSession';
import type { GuitarTransformSettings } from './lib/musicTransposer';
import type { SearchResultItem, SongSection } from './types/music';

export const App: React.FC = () => {
  const { session, stage, error, loadSong, updateManualOffset } = useSongSession();
  const [loopRange, setLoopRange] = useState<LoopRange | null>(null);
  const [settings, setSettings] = useState<GuitarTransformSettings>({
    capo: 0,
    transpose: 0,
    simplify: false,
  });

  // Auto-apply recommended capo once per newly loaded videoId
  const appliedCapoVideoRef = useRef<string | null>(null);
  useEffect(() => {
    if (!session?.chords) return;
    if (appliedCapoVideoRef.current !== session.videoId) {
      appliedCapoVideoRef.current = session.videoId;
      setSettings((prev) => ({
        ...prev,
        capo: session.chords?.recommendedCapo ?? 0,
        transpose: 0,
      }));
    }
  }, [session?.videoId, session?.chords]);

  const {
    ytContainerRef,
    audioRef,
    useAudioFallback,
    setUseAudioFallback,
    isPlaying,
    setIsPlaying,
    currentTimeMs,
    durationMs,
    playbackRate,
    setPlaybackRate,
    togglePlay,
    seekToMs,
  } = usePlaybackClock({
    videoId: session?.videoId ?? null,
    audioReady: session?.audioReady ?? false,
    loopRange,
  });

  const handleSelectSong = (item: SearchResultItem) => {
    setLoopRange(null);
    appliedCapoVideoRef.current = null;
    loadSong(item);
  };

  // Keyboard shortcuts: Space = Play/Pause, [ / ] = ±250ms lyric sync nudge
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (e.code === 'Space') {
        e.preventDefault();
        togglePlay();
      } else if (e.key === '[' && session) {
        void updateManualOffset(session.manualOffsetMs - 250);
      } else if (e.key === ']' && session) {
        void updateManualOffset(session.manualOffsetMs + 250);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [togglePlay, session, updateManualOffset]);

  // Determine current and next chord events for FretboardDeck
  const { currentEvent, nextEvent } = useMemo(() => {
    const evs = session?.chords?.events ?? [];
    if (!evs.length) return { currentEvent: null, nextEvent: null };
    let curIdx = -1;
    for (let i = 0; i < evs.length; i++) {
      if (currentTimeMs >= evs[i].startMs && currentTimeMs < evs[i].endMs) {
        curIdx = i;
        break;
      }
      if (evs[i].startMs > currentTimeMs) {
        return { currentEvent: null, nextEvent: evs[i] };
      }
    }
    if (curIdx === -1) {
      return { currentEvent: evs[evs.length - 1], nextEvent: null };
    }
    let nxt = null;
    for (let j = curIdx + 1; j < evs.length; j++) {
      if (evs[j].display !== evs[curIdx].display) {
        nxt = evs[j];
        break;
      }
    }
    return { currentEvent: evs[curIdx], nextEvent: nxt };
  }, [session?.chords?.events, currentTimeMs]);

  const firstVocalStudioMs = useMemo(() => {
    const rawSections = session?.lyrics?.sections ?? [];
    for (const s of rawSections) {
      if (s.lines.length > 0) return s.lines[0].startMs;
    }
    return null;
  }, [session?.lyrics?.sections]);

  const handleToggleSectionLoop = (sec: SongSection) => {
    if (
      loopRange &&
      Math.abs(loopRange.startMs - sec.startMs) < 150 &&
      Math.abs(loopRange.endMs - sec.endMs) < 150
    ) {
      setLoopRange(null);
    } else {
      setLoopRange({ startMs: sec.startMs, endMs: sec.endMs, label: sec.name });
      seekToMs(sec.startMs);
    }
  };

  const effectiveDurationMs = durationMs || (session?.durationSec ?? 0) * 1000;

  return (
    <div className="app-shell">
      <HeaderSearchBar
        onSelectSong={handleSelectSong}
        stage={stage}
        activeVideoId={session?.videoId ?? null}
      />

      <main className="studio-workspace-container">
        <div className="studio-grid">
          {/* Left Column: Guitar Toolbar + Beat Runway + Karaoke Chord-Lyric Stage */}
          <div className="left-stage-column">
            {session && (
              <>
                <GuitarToolbar
                  settings={settings}
                  onChangeSettings={setSettings}
                  capoOptions={session.chords?.capoOptions ?? []}
                  recommendedCapo={session.chords?.recommendedCapo ?? 0}
                  detectedKey={session.chords?.detectedKey ?? ''}
                  lyricsSource={session.lyrics?.source ?? null}
                />
                <BeatRunway
                  currentTimeMs={currentTimeMs}
                  bpm={session.chords?.bpm ?? 120}
                  beatsMs={session.chords?.beatsMs ?? []}
                  events={session.chords?.events ?? []}
                  settings={settings}
                  onSeekMs={seekToMs}
                />
              </>
            )}

            {error && (
              <div style={{ padding: '0.75rem 1.25rem', background: 'rgba(251,113,133,0.15)', color: '#fb7185', fontSize: '0.85rem' }}>
                {error}
              </div>
            )}

            <KaraokeStage
              sections={session?.alignedSections ?? []}
              currentTimeMs={currentTimeMs}
              settings={settings}
              hasWordSync={session?.lyrics?.hasWordSync ?? false}
              hasLineSync={session?.lyrics?.hasLineSync ?? false}
              stage={stage}
              loopRange={loopRange}
              onToggleSectionLoop={handleToggleSectionLoop}
              onSeekMs={seekToMs}
              onQuickPickSong={handleSelectSong}
            />
          </div>

          {/* Right Rail: YouTube Video / Fallback Audio + Dual SVG Guitar Fretboard Deck */}
          <aside className="right-rail-column">
            <div className="video-frame-card">
              {!session ? (
                <div className="audio-fallback-card">
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.84rem' }}>
                    YouTube Video Player will appear here
                  </span>
                </div>
              ) : useAudioFallback ? (
                <div className="audio-fallback-card">
                  <img
                    src={session.thumbnailUrl}
                    alt=""
                    className="audio-fallback-thumb"
                  />
                  <span className="audio-fallback-badge">
                    Local HD Audio Stream (Embed Restricted on YouTube)
                  </span>
                  <strong style={{ fontSize: '0.9rem' }}>
                    {session.title} — {session.artist}
                  </strong>
                  <audio
                    ref={audioRef}
                    src={session.audioReady ? `/api/audio/${session.videoId}` : undefined}
                    onPlay={() => setIsPlaying(true)}
                    onPause={() => setIsPlaying(false)}
                    controls
                    style={{ width: '92%', height: 32 }}
                  />
                </div>
              ) : (
                <div ref={ytContainerRef} className="yt-mount-box" />
              )}
            </div>

            {session && (
              <div className="mode-switch-row">
                <span>
                  {session.artist} — <strong>{session.title}</strong>
                </span>
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => setUseAudioFallback(!useAudioFallback)}
                >
                  {useAudioFallback ? 'Try YouTube Video' : 'Switch to Audio Stream'}
                </button>
              </div>
            )}

            <FretboardDeck
              currentEvent={currentEvent}
              nextEvent={nextEvent}
              allEvents={session?.chords?.events ?? []}
              settings={settings}
            />
          </aside>
        </div>
      </main>

      {session && (
        <PracticeBar
          isPlaying={isPlaying}
          currentTimeMs={currentTimeMs}
          durationMs={effectiveDurationMs}
          playbackRate={playbackRate}
          loopRange={loopRange}
          autoOffsetMs={session.autoOffsetMs}
          manualOffsetMs={session.manualOffsetMs}
          skipSegments={session.skipSegments}
          firstVocalStudioMs={firstVocalStudioMs}
          onTogglePlay={togglePlay}
          onSeekMs={seekToMs}
          onChangeRate={setPlaybackRate}
          onSetLoopRange={setLoopRange}
          onUpdateManualOffset={updateManualOffset}
        />
      )}
    </div>
  );
};
export default App;
