import { useCallback, useEffect, useRef, useState } from 'react';
import type { SearchResultItem, SessionStage, SongSession } from '../types/music';

interface UseSongSessionResult {
  session: SongSession | null;
  stage: SessionStage;
  error: string | null;
  loadSong: (item: SearchResultItem) => void;
  resetSession: () => void;
  updateManualOffset: (newManualOffsetMs: number) => Promise<void>;
}

export function useSongSession(): UseSongSessionResult {
  const [session, setSession] = useState<SongSession | null>(null);
  const [stage, setStage] = useState<SessionStage>('idle');
  const [error, setError] = useState<string | null>(null);

  const esRef = useRef<EventSource | null>(null);
  const sessionRef = useRef<SongSession | null>(null);
  sessionRef.current = session;
  const patchSeqRef = useRef(0);

  const closeStream = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  }, []);

  useEffect(() => closeStream, [closeStream]);

  const resetSession = useCallback(() => {
    closeStream();
    patchSeqRef.current += 1;
    setError(null);
    setStage('idle');
    setSession(null);
  }, [closeStream]);

  const loadSong = useCallback(
    (item: SearchResultItem) => {
      closeStream();
      patchSeqRef.current += 1;
      setError(null);
      setStage('loading_lyrics');
      const initial: SongSession = {
        videoId: item.videoId,
        title: item.title,
        artist: item.artist,
        album: item.album,
        durationSec: item.durationSec,
        thumbnailUrl: item.thumbnailUrl,
        autoOffsetMs: 0,
        manualOffsetMs: 0,
        skipSegments: [],
        lyrics: null,
        chords: null,
        alignedSections: [],
        audioReady: false,
      };
      sessionRef.current = initial;
      setSession(initial);

      const params = new URLSearchParams({
        title: item.title,
        artist: item.artist,
        album: item.album || '',
        duration_sec: String(item.durationSec || 0),
        thumbnail_url: item.thumbnailUrl || '',
      });

      const es = new EventSource(
        `/api/session/${encodeURIComponent(item.videoId)}/stream?${params.toString()}`
      );
      esRef.current = es;

      es.addEventListener('lyrics_ready', (ev) => {
        const data = JSON.parse((ev as MessageEvent).data) as SongSession;
        setSession(data);
        setStage('lyrics_ready');
      });

      es.addEventListener('chords_fast', (ev) => {
        const data = JSON.parse((ev as MessageEvent).data) as SongSession;
        setSession(data);
        setStage('chords_fast');
      });

      es.addEventListener('chords_neural', (ev) => {
        const data = JSON.parse((ev as MessageEvent).data) as SongSession;
        setSession(data);
        setStage('chords_neural');
      });

      es.addEventListener('done', () => {
        closeStream();
      });

      es.addEventListener('error', (ev) => {
        const msgEvent = ev as MessageEvent;
        if (msgEvent.data) {
          try {
            const parsed = JSON.parse(msgEvent.data) as { message?: string };
            setError(parsed.message || 'Failed to analyze song');
          } catch {
            setError('Connection interrupted while analyzing song');
          }
          setStage('error');
        }
        closeStream();
      });
    },
    [closeStream]
  );

  const updateManualOffset = useCallback(async (newManualOffsetMs: number) => {
    const clamped = Math.max(-300_000, Math.min(300_000, Math.round(newManualOffsetMs)));
    const cur = sessionRef.current;
    if (!cur) return;

    const targetVideoId = cur.videoId;
    const seq = ++patchSeqRef.current;
    setSession((prev) => (prev ? { ...prev, manualOffsetMs: clamped } : null));

    try {
      const res = await fetch(`/api/session/${encodeURIComponent(targetVideoId)}/offset`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ manualOffsetMs: clamped }),
      });
      if (!res.ok || seq !== patchSeqRef.current) return;
      const updated = (await res.json()) as SongSession;
      if (seq === patchSeqRef.current) {
        setSession((latest) =>
          latest && latest.videoId === updated.videoId ? updated : latest
        );
      }
    } catch {
      // Ignore transient network errors; optimistic manualOffsetMs remains set
    }
  }, []);

  return { session, stage, error, loadSong, resetSession, updateManualOffset };
}
