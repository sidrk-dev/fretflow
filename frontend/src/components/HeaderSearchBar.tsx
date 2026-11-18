import React, { useEffect, useRef, useState } from 'react';
import { Disc3, Guitar, Loader2, Radio, Search, Sparkles, Tv, X } from 'lucide-react';
import type { SearchResponse, SearchResultItem, SearchResultType, SessionStage } from '../types/music';

interface HeaderSearchBarProps {
  onSelectSong: (item: SearchResultItem) => void;
  stage: SessionStage;
  activeVideoId: string | null;
}

const STAGE_BADGES: Record<SessionStage, { label: string; tone: string } | null> = {
  idle: null,
  loading_lyrics: { label: 'Syncing Lyrics…', tone: 'badge-amber' },
  lyrics_ready: { label: 'Extracting Audio & Beats…', tone: 'badge-amber' },
  chords_fast: { label: 'Fast Chords Ready • Upgrading to Neural…', tone: 'badge-cyan' },
  chords_neural: { label: 'HD Neural Chords + Synced Lyrics', tone: 'badge-emerald' },
  error: { label: 'Analysis Error', tone: 'badge-rose' },
};

export const HeaderSearchBar: React.FC<HeaderSearchBarProps> = ({
  onSelectSong,
  stage,
  activeVideoId,
}) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<'all' | SearchResultType>('all');
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  const runSearch = async (qText: string) => {
    const trimmed = qText.trim();
    if (!trimmed) return;
    setLoading(true);
    setOpen(true);
    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(trimmed)}`);
      if (res.ok) {
        const data = (await res.json()) as SearchResponse;
        setResults(data.results);
      }
    } catch {
      // ignore network hiccup
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void runSearch(query);
  };

  const filtered = results.filter((r) => (tab === 'all' ? true : r.resultType === tab));
  const badge = STAGE_BADGES[stage];

  return (
    <header className="studio-header">
      <div className="brand-lockup">
        <div className="brand-icon">
          <Guitar size={20} />
        </div>
        <span className="brand-name">
          Fret<span>Flow</span>
        </span>
      </div>

      <div className="search-shell" ref={wrapperRef}>
        <form onSubmit={handleSubmit} className="search-form">
          <Search size={16} className="search-icon" />
          <input
            type="search"
            value={query}
            onFocus={() => {
              if (results.length > 0) setOpen(true);
            }}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search any song, artist, or paste a YouTube URL…"
            aria-label="Search songs or YouTube videos"
            className="search-input"
          />
          {query && (
            <button
              type="button"
              className="icon-clear-btn"
              onClick={() => {
                setQuery('');
                setResults([]);
              }}
              aria-label="Clear search"
            >
              <X size={14} />
            </button>
          )}
          <button type="submit" className="search-submit-btn" disabled={loading}>
            {loading ? <Loader2 size={15} className="spin" /> : 'Search'}
          </button>
        </form>

        {open && (loading || results.length > 0) && (
          <div className="search-dropdown" role="listbox" aria-label="Song search results">
            <div className="search-tabs">
              {(['all', 'studio', 'video', 'live'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`search-tab ${tab === t ? 'active' : ''}`}
                  onClick={() => setTab(t)}
                >
                  {t === 'all' && 'All Results'}
                  {t === 'studio' && (
                    <>
                      <Disc3 size={13} /> Official Audio (Best Sync)
                    </>
                  )}
                  {t === 'video' && (
                    <>
                      <Tv size={13} /> Music Videos
                    </>
                  )}
                  {t === 'live' && (
                    <>
                      <Radio size={13} /> Live / Covers
                    </>
                  )}
                </button>
              ))}
            </div>

            {loading ? (
              <div className="search-loading-row">
                <Loader2 size={18} className="spin" />
                <span>Searching YouTube Music & Videos…</span>
              </div>
            ) : filtered.length === 0 ? (
              <div className="search-loading-row">No matching videos in this tab.</div>
            ) : (
              <ul className="search-result-list">
                {filtered.map((item) => {
                  const isCurrent = item.videoId === activeVideoId;
                  return (
                    <li key={item.videoId}>
                      <button
                        type="button"
                        className={`search-result-item ${isCurrent ? 'selected' : ''}`}
                        onClick={() => {
                          onSelectSong(item);
                          setOpen(false);
                        }}
                      >
                        <img
                          src={item.thumbnailUrl}
                          alt=""
                          width={56}
                          height={42}
                          loading="lazy"
                          className="result-thumb"
                        />
                        <div className="result-meta">
                          <div className="result-title-row">
                            <span className="result-title">{item.title}</span>
                            <span className={`result-type-pill type-${item.resultType}`}>
                              {item.resultType === 'studio'
                                ? 'Studio Audio'
                                : item.resultType === 'live'
                                  ? 'Live / Cover'
                                  : 'Music Video'}
                            </span>
                          </div>
                          <div className="result-sub">
                            <span>{item.artist}</span>
                            {item.album && <span>• {item.album}</span>}
                            {item.durationText && <span>• {item.durationText}</span>}
                          </div>
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </div>

      <div className="header-status">
        {badge && (
          <span className={`status-pill ${badge.tone}`}>
            {stage === 'chords_neural' ? (
              <Sparkles size={13} />
            ) : stage === 'error' ? null : (
              <Loader2 size={13} className="spin" />
            )}
            <span>{badge.label}</span>
          </span>
        )}
      </div>
    </header>
  );
};
