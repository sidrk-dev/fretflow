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
  const { session, stage, error, loadSong, resetSession, updateManualOffset } = useSongSession();
  const [loopRange, setLoopRange] = useState<LoopRange | null>(null);
  const [settings, setSettings] = useState<GuitarTransformSettings>({
    capo: 0,
    transpose: 0,
    simplify: false,
  });

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

  const handleGoHome = () => {
    setLoopRange(null);
    appliedCapoVideoRef.current = null;
    resetSession();
  };

  const hasLineSync = session?.lyrics?.hasLineSync ?? false;

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (e.code === 'Space' && session) {
        e.preventDefault();
        togglePlay();
      } else if (e.key === '[' && session && hasLineSync) {
        void updateManualOffset(session.manualOffsetMs - 250);
      } else if (e.key === ']' && session && hasLineSync) {
        void updateManualOffset(session.manualOffsetMs + 250);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [togglePlay, session, hasLineSync, updateManualOffset]);

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
    if (!hasLineSync) return null;
    const rawSections = session?.lyrics?.sections ?? [];
    for (const s of rawSections) {
      if (s.lines.length > 0) return s.lines[0].startMs;
    }
    return null;
  }, [session?.lyrics?.sections, hasLineSync]);

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
        onGoHome={handleGoHome}
        stage={stage}
        activeVideoId={session?.videoId ?? null}
      />

      <main className="studio-workspace-container">
        <div className={`studio-grid ${!session ? 'is-welcome' : ''}`}>
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
                  uniqueChordCount={session.chords?.uniqueChords.length ?? 0}
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

            {error && <div className="error-banner">{error}</div>}

            <KaraokeStage
              sections={session?.alignedSections ?? []}
              currentTimeMs={currentTimeMs}
              settings={settings}
              hasWordSync={session?.lyrics?.hasWordSync ?? false}
              hasLineSync={hasLineSync}
              stage={stage}
              loopRange={loopRange}
              onToggleSectionLoop={handleToggleSectionLoop}
              onSeekMs={seekToMs}
              onQuickPickSong={handleSelectSong}
            />
          </div>

          {session && (
            <aside className="right-rail-column">
              <div className="rail-media-block">
                <div className="video-frame-card">
                  {useAudioFallback ? (
                    <div key="audio-fallback" className="audio-fallback-card">
                      <div className="audio-fallback-top">
                        <img
                          src={session.thumbnailUrl}
                          alt=""
                          className="audio-fallback-thumb"
                        />
                        <div className="audio-fallback-meta">
                          <span className="audio-fallback-badge">Local HD Audio Stream</span>
                          <strong className="audio-fallback-title">{session.title}</strong>
                          <span className="audio-fallback-artist">{session.artist}</span>
                        </div>
                      </div>
                      <audio
                        ref={audioRef}
                        src={session.audioReady ? `/api/audio/${session.videoId}` : undefined}
                        onPlay={() => setIsPlaying(true)}
                        onPause={() => setIsPlaying(false)}
                        controls
                        className="fallback-audio-el"
                      />
                    </div>
                  ) : (
                    <div
                      key={`yt-${session.videoId}`}
                      ref={ytContainerRef}
                      className="yt-mount-box"
                    />
                  )}
                </div>

                <div className="mode-switch-row">
                  <span className="now-playing-truncate">
                    {session.artist} — <strong>{session.title}</strong>
                  </span>
                  <button
                    type="button"
                    className="link-btn"
                    onClick={() => setUseAudioFallback(!useAudioFallback)}
                  >
                    {useAudioFallback ? 'Try Video' : 'Audio Only'}
                  </button>
                </div>
              </div>

              <FretboardDeck
                currentEvent={currentEvent}
                nextEvent={nextEvent}
                allEvents={session.chords?.events ?? []}
                settings={settings}
              />
            </aside>
          )}
        </div>
      </main>

      {session && (
        <PracticeBar
          isPlaying={isPlaying}
          currentTimeMs={currentTimeMs}
          durationMs={effectiveDurationMs}
          playbackRate={playbackRate}
          loopRange={loopRange}
          hasLineSync={hasLineSync}
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
