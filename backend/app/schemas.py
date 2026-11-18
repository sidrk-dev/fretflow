from __future__ import annotations

import re
from typing import Literal, Optional
from pydantic import BaseModel, Field

YOUTUBE_ID_PATTERN = r"^[A-Za-z0-9_-]{11}$"
YOUTUBE_ID_RE = re.compile(YOUTUBE_ID_PATTERN)


class SearchResultItem(BaseModel):
    videoId: str
    title: str
    artist: str
    album: str = ""
    durationSec: int = 0
    durationText: str = ""
    thumbnailUrl: str = ""
    resultType: Literal["studio", "video", "live"] = "studio"
    viewsText: str = ""


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]


class LyricWord(BaseModel):
    text: str
    startMs: int
    endMs: int


class ChordAnchor(BaseModel):
    harte: str
    rootPc: int
    quality: str
    bassPc: Optional[int] = None
    display: str
    startMs: int
    endMs: int
    wordIndex: Optional[int] = None
    charOffset: Optional[int] = None
    confidence: float = 1.0


class LyricLine(BaseModel):
    id: str
    startMs: int
    endMs: int
    text: str
    words: list[LyricWord] = Field(default_factory=list)
    chords: list[ChordAnchor] = Field(default_factory=list)


class InstrumentalBarChord(BaseModel):
    harte: str
    rootPc: int
    quality: str
    bassPc: Optional[int] = None
    display: str
    startMs: int
    endMs: int
    beats: int = 4


class SongSection(BaseModel):
    id: str
    name: str
    kind: Literal["lyrics", "instrumental"] = "lyrics"
    startMs: int
    endMs: int
    lines: list[LyricLine] = Field(default_factory=list)
    instrumentalChords: list[InstrumentalBarChord] = Field(default_factory=list)


class ChordEvent(BaseModel):
    harte: str
    rootPc: int
    quality: str
    bassPc: Optional[int] = None
    display: str
    startMs: int
    endMs: int
    confidence: float = 1.0


class CapoOption(BaseModel):
    capoFret: int
    score: float
    openChordRatio: float
    keyLabel: str
    previewChords: list[str]
    isRecommended: bool = False


class SkipSegment(BaseModel):
    category: str
    startMs: int
    endMs: int


class LyricsPayload(BaseModel):
    source: Literal[
        "betterlyrics_ttml",
        "lrclib_word",
        "lrclib_line",
        "syncedlyrics_word",
        "syncedlyrics_line",
        "plain",
        "none",
    ]
    hasWordSync: bool
    hasLineSync: bool
    plainText: str = ""
    sections: list[SongSection] = Field(default_factory=list)


class ChordsPayload(BaseModel):
    engine: Literal["fast_cqt_hmm", "neural_btc_170"]
    bpm: float
    beatsMs: list[int] = Field(default_factory=list)
    detectedKey: str = ""
    events: list[ChordEvent] = Field(default_factory=list)
    capoOptions: list[CapoOption] = Field(default_factory=list)
    recommendedCapo: int = 0
    uniqueChords: list[str] = Field(default_factory=list)


class SongSession(BaseModel):
    videoId: str
    title: str
    artist: str
    album: str = ""
    durationSec: int = 0
    thumbnailUrl: str = ""
    autoOffsetMs: int = 0
    manualOffsetMs: int = 0
    skipSegments: list[SkipSegment] = Field(default_factory=list)
    lyrics: Optional[LyricsPayload] = None
    chords: Optional[ChordsPayload] = None
    alignedSections: list[SongSection] = Field(default_factory=list)
    audioReady: bool = False


class OffsetUpdateRequest(BaseModel):
    manualOffsetMs: int = Field(..., ge=-300_000, le=300_000)
