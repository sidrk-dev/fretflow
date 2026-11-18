import { useCallback, useEffect, useRef, useState } from 'react';

declare global {
  interface Window {
    YT?: {
      Player: new (
        elementId: string | HTMLElement,
        options: {
          videoId?: string;
          playerVars?: Record<string, string | number>;
          events?: {
            onReady?: (e: { target: YTPlayerInstance }) => void;
            onStateChange?: (e: { data: number; target: YTPlayerInstance }) => void;
            onError?: (e: { data: number }) => void;
          };
        }
      ) => YTPlayerInstance;
    };
    onYouTubeIframeAPIReady?: () => void;
  }
}

interface YTPlayerInstance {
  loadVideoById: (videoId: string) => void;
  playVideo: () => void;
  pauseVideo: () => void;
  seekTo: (seconds: number, allowSeekAhead: boolean) => void;
  getCurrentTime: () => number;
  getDuration: () => number;
  setPlaybackRate: (rate: number) => void;
  getPlayerState: () => number;
  destroy: () => void;
}

export interface LoopRange {
  startMs: number;
  endMs: number;
  label: string;
}

interface UsePlaybackClockOptions {
  videoId: string | null;
  audioReady: boolean;
  loopRange: LoopRange | null;
}

let ytApiPromise: Promise<void> | null = null;
function ensureYouTubeApi(): Promise<void> {
  if (window.YT && window.YT.Player) return Promise.resolve();
  if (ytApiPromise) return ytApiPromise;
  ytApiPromise = new Promise((resolve) => {
    const prev = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      prev?.();
      resolve();
    };
    const script = document.createElement('script');
    script.src = 'https://www.youtube.com/iframe_api';
    script.async = true;
    document.head.appendChild(script);
  });
  return ytApiPromise;
}

export function usePlaybackClock({ videoId, audioReady, loopRange }: UsePlaybackClockOptions) {
  const ytContainerRef = useRef<HTMLDivElement | null>(null);
  const ytPlayerRef = useRef<YTPlayerInstance | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const [useAudioFallback, setUseAudioFallback] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTimeMs, setCurrentTimeMs] = useState(0);
  const [durationMs, setDurationMs] = useState(0);
  const [playbackRate, setPlaybackRateState] = useState(1.0);

  const currentTimeMsRef = useRef(0);
  const durationMsRef = useRef(0);

  const updateCurrentTime = useCallback((ms: number) => {
    if (currentTimeMsRef.current !== ms) {
      currentTimeMsRef.current = ms;
      setCurrentTimeMs(ms);
    }
  }, []);

  const updateDuration = useCallback((ms: number) => {
    if (ms > 0 && durationMsRef.current !== ms) {
      durationMsRef.current = ms;
      setDurationMs(ms);
    }
  }, []);

  const interpRef = useRef({
    lastRawMediaSec: 0,
    anchorMediaSec: 0,
    anchorPerfMs: 0,
  });
  const loopRef = useRef<LoopRange | null>(loopRange);
  loopRef.current = loopRange;
  const rateRef = useRef(playbackRate);
  rateRef.current = playbackRate;

  // Reset state cleanly when videoId changes
  useEffect(() => {
    setUseAudioFallback(false);
    setIsPlaying(false);
    currentTimeMsRef.current = 0;
    durationMsRef.current = 0;
    setCurrentTimeMs(0);
    setDurationMs(0);
    interpRef.current = {
      lastRawMediaSec: 0,
      anchorMediaSec: 0,
      anchorPerfMs: performance.now(),
    };
  }, [videoId]);

  // Mount & cleanly destroy YouTube IFrame Player whenever videoId or useAudioFallback changes
  useEffect(() => {
    if (!videoId || useAudioFallback) return;
    let cancelled = false;

    void ensureYouTubeApi().then(() => {
      if (cancelled || !ytContainerRef.current || !window.YT) return;

      const mountNode = document.createElement('div');
      ytContainerRef.current.innerHTML = '';
      ytContainerRef.current.appendChild(mountNode);

      const player = new window.YT.Player(mountNode, {
        videoId,
        playerVars: {
          autoplay: 1,
          playsinline: 1,
          rel: 0,
          modestbranding: 1,
          origin: window.location.origin,
        },
        events: {
          onReady: (e) => {
            if (cancelled) return;
            const dur = e.target.getDuration();
            if (dur > 0) updateDuration(Math.round(dur * 1000));
            e.target.setPlaybackRate(rateRef.current);
            if (currentTimeMsRef.current > 0) {
              e.target.seekTo(currentTimeMsRef.current / 1000, true);
            }
          },
          onStateChange: (e) => {
            if (cancelled) return;
            const playing = e.data === 1;
            setIsPlaying(playing);
            const rawSec = e.target.getCurrentTime() || 0;
            interpRef.current = {
              lastRawMediaSec: rawSec,
              anchorMediaSec: rawSec,
              anchorPerfMs: performance.now(),
            };
            const dur = e.target.getDuration();
            if (dur > 0) updateDuration(Math.round(dur * 1000));
          },
          onError: (e) => {
            if (cancelled) return;
            if ([2, 5, 100, 101, 150].includes(e.data)) {
              setUseAudioFallback(true);
              setIsPlaying(false);
            }
          },
        },
      });
      ytPlayerRef.current = player;
    });

    return () => {
      cancelled = true;
      if (ytPlayerRef.current) {
        try {
          ytPlayerRef.current.destroy();
        } catch {
          // ignore
        }
        ytPlayerRef.current = null;
      }
    };
  }, [videoId, useAudioFallback, updateDuration]);

  // Sync current position and auto-play HTML5 fallback audio when ready
  useEffect(() => {
    if (!useAudioFallback || !videoId || !audioReady || !audioRef.current) return;
    const el = audioRef.current;
    el.playbackRate = rateRef.current;
    el.preservesPitch = true;
    if (currentTimeMsRef.current > 0 && Math.abs(el.currentTime * 1000 - currentTimeMsRef.current) > 300) {
      el.currentTime = currentTimeMsRef.current / 1000;
    }
    void el.play().catch(() => {});
  }, [useAudioFallback, videoId, audioReady]);

  const seekToMs = useCallback(
    (ms: number) => {
      const clampedMs = Math.max(0, Math.round(ms));
      const sec = clampedMs / 1000;
      interpRef.current = {
        lastRawMediaSec: sec,
        anchorMediaSec: sec,
        anchorPerfMs: performance.now(),
      };
      updateCurrentTime(clampedMs);

      if (useAudioFallback && audioRef.current) {
        audioRef.current.currentTime = sec;
      } else if (ytPlayerRef.current) {
        try {
          ytPlayerRef.current.seekTo(sec, true);
        } catch {
          // Player still mounting; currentTimeMsRef will apply in onReady
        }
      }
    },
    [useAudioFallback, updateCurrentTime]
  );

  const togglePlay = useCallback(() => {
    if (useAudioFallback && audioRef.current) {
      if (audioRef.current.paused) {
        void audioRef.current.play().catch(() => {});
      } else {
        audioRef.current.pause();
      }
      return;
    }
    const p = ytPlayerRef.current;
    if (!p) return;
    try {
      const st = p.getPlayerState();
      if (st === 1) {
        p.pauseVideo();
      } else {
        p.playVideo();
      }
    } catch {
      // ignore if player not ready yet
    }
  }, [useAudioFallback]);

  const setPlaybackRate = useCallback(
    (rate: number) => {
      setPlaybackRateState(rate);
      rateRef.current = rate;
      if (useAudioFallback && audioRef.current) {
        audioRef.current.playbackRate = rate;
        audioRef.current.preservesPitch = true;
      } else if (ytPlayerRef.current) {
        try {
          ytPlayerRef.current.setPlaybackRate(rate);
        } catch {
          // ignore
        }
      }
    },
    [useAudioFallback]
  );

  // 60fps smooth clock + A-B loop enforcement with zero idle re-renders
  useEffect(() => {
    if (!videoId) return;
    let rafId = 0;

    const tick = () => {
      const now = performance.now();
      let computedMs = currentTimeMsRef.current;

      if (useAudioFallback && audioRef.current) {
        const el = audioRef.current;
        if (!el.paused || el.currentTime > 0) {
          computedMs = Math.round(el.currentTime * 1000);
        }
        if (el.duration && Number.isFinite(el.duration)) {
          updateDuration(Math.round(el.duration * 1000));
        }
      } else if (ytPlayerRef.current) {
        try {
          const st = ytPlayerRef.current.getPlayerState();
          const rawSec = ytPlayerRef.current.getCurrentTime() || 0;
          const playing = st === 1;

          if (Math.abs(rawSec - interpRef.current.lastRawMediaSec) > 0.001) {
            interpRef.current = {
              lastRawMediaSec: rawSec,
              anchorMediaSec: rawSec,
              anchorPerfMs: now,
            };
          }

          if (playing) {
            const elapsedSec =
              ((now - interpRef.current.anchorPerfMs) / 1000) * rateRef.current;
            computedMs = Math.round(
              (interpRef.current.anchorMediaSec + Math.min(elapsedSec, 0.35)) * 1000
            );
          } else if (rawSec > 0) {
            computedMs = Math.round(rawSec * 1000);
          }
        } catch {
          // Player still initializing
        }
      }

      const activeLoop = loopRef.current;
      if (activeLoop && computedMs >= activeLoop.endMs) {
        seekToMs(activeLoop.startMs);
      } else {
        updateCurrentTime(computedMs);
      }

      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [videoId, useAudioFallback, seekToMs, updateCurrentTime, updateDuration]);

  return {
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
  };
}
