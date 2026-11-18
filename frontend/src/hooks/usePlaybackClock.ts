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
      PlayerState?: {
        PLAYING: number;
        PAUSED: number;
        ENDED: number;
        BUFFERING: number;
      };
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

  // High-resolution rAF interpolation state for sub-16ms karaoke smoothness
  const interpRef = useRef({
    lastRawMediaSec: 0,
    anchorMediaSec: 0,
    anchorPerfMs: 0,
  });
  const loopRef = useRef<LoopRange | null>(loopRange);
  loopRef.current = loopRange;
  const rateRef = useRef(playbackRate);
  rateRef.current = playbackRate;

  // Reset state when videoId changes
  useEffect(() => {
    setUseAudioFallback(false);
    setIsPlaying(false);
    setCurrentTimeMs(0);
    interpRef.current = { lastRawMediaSec: 0, anchorMediaSec: 0, anchorPerfMs: performance.now() };
  }, [videoId]);

  // Mount/update YouTube IFrame Player
  useEffect(() => {
    if (!videoId || useAudioFallback) return;
    let cancelled = false;

    void ensureYouTubeApi().then(() => {
      if (cancelled || !ytContainerRef.current || !window.YT) return;

      if (ytPlayerRef.current) {
        try {
          ytPlayerRef.current.loadVideoById(videoId);
          ytPlayerRef.current.setPlaybackRate(rateRef.current);
          return;
        } catch {
          ytPlayerRef.current.destroy();
          ytPlayerRef.current = null;
        }
      }

      const mountNode = document.createElement('div');
      ytContainerRef.current.innerHTML = '';
      ytContainerRef.current.appendChild(mountNode);

      ytPlayerRef.current = new window.YT.Player(mountNode, {
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
            if (dur > 0) setDurationMs(Math.round(dur * 1000));
            e.target.setPlaybackRate(rateRef.current);
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
            if (dur > 0) setDurationMs(Math.round(dur * 1000));
          },
          onError: (e) => {
            // Codes 101 / 150 = VEVO / owner blocked embedded playback -> switch to local audio stream!
            if ([2, 5, 100, 101, 150].includes(e.data)) {
              setUseAudioFallback(true);
              setIsPlaying(false);
            }
          },
        },
      });
    });

    return () => {
      cancelled = true;
    };
  }, [videoId, useAudioFallback]);

  // Cleanup YT player on unmount
  useEffect(() => {
    return () => {
      if (ytPlayerRef.current) {
        try {
          ytPlayerRef.current.destroy();
        } catch {
          // ignore
        }
        ytPlayerRef.current = null;
      }
    };
  }, []);

  // Auto-play HTML5 fallback audio once backend finishes extracting MP3
  useEffect(() => {
    if (!useAudioFallback || !videoId || !audioReady || !audioRef.current) return;
    const el = audioRef.current;
    el.playbackRate = rateRef.current;
    el.preservesPitch = true;
    void el.play().catch(() => {});
  }, [useAudioFallback, videoId, audioReady]);

  const seekToMs = useCallback(
    (ms: number) => {
      const clampedMs = Math.max(0, ms);
      const sec = clampedMs / 1000;
      interpRef.current = {
        lastRawMediaSec: sec,
        anchorMediaSec: sec,
        anchorPerfMs: performance.now(),
      };
      setCurrentTimeMs(clampedMs);

      if (useAudioFallback && audioRef.current) {
        audioRef.current.currentTime = sec;
      } else if (ytPlayerRef.current) {
        ytPlayerRef.current.seekTo(sec, true);
      }
    },
    [useAudioFallback]
  );

  const togglePlay = useCallback(() => {
    if (useAudioFallback && audioRef.current) {
      if (audioRef.current.paused) {
        void audioRef.current.play();
      } else {
        audioRef.current.pause();
      }
      return;
    }
    const p = ytPlayerRef.current;
    if (!p) return;
    const st = p.getPlayerState();
    if (st === 1) {
      p.pauseVideo();
    } else {
      p.playVideo();
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
        ytPlayerRef.current.setPlaybackRate(rate);
      }
    },
    [useAudioFallback]
  );

  // 60fps smooth clock + A-B loop enforcement
  useEffect(() => {
    let rafId = 0;

    const tick = () => {
      const now = performance.now();
      let computedMs = currentTimeMs;

      if (useAudioFallback && audioRef.current) {
        const el = audioRef.current;
        computedMs = Math.round(el.currentTime * 1000);
        if (el.duration && Number.isFinite(el.duration)) {
          setDurationMs(Math.round(el.duration * 1000));
        }
      } else if (ytPlayerRef.current) {
        try {
          const rawSec = ytPlayerRef.current.getCurrentTime() || 0;
          const st = ytPlayerRef.current.getPlayerState();
          const playing = st === 1;

          if (Math.abs(rawSec - interpRef.current.lastRawMediaSec) > 0.001) {
            interpRef.current = {
              lastRawMediaSec: rawSec,
              anchorMediaSec: rawSec,
              anchorPerfMs: now,
            };
          }

          if (playing) {
            const elapsedSec = ((now - interpRef.current.anchorPerfMs) / 1000) * rateRef.current;
            computedMs = Math.round((interpRef.current.anchorMediaSec + Math.min(elapsedSec, 0.35)) * 1000);
          } else {
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
        setCurrentTimeMs(computedMs);
      }

      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [useAudioFallback, seekToMs]);

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
