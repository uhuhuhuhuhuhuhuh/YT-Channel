"""Group timed words into short, punchy caption chunks (and export SRT)."""

from __future__ import annotations

from dataclasses import dataclass

from .tts import Word


@dataclass
class Chunk:
    words: list[Word]
    start: float
    end: float          # when the chunk leaves the screen

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def chunk_words(words: list[Word], max_words: int = 3, max_chars: int = 16,
                linger: float = 0.35) -> list[Chunk]:
    chunks: list[Chunk] = []
    cur: list[Word] = []
    for w in words:
        trial = " ".join(x.text for x in cur + [w])
        if cur and (len(cur) >= max_words or len(trial) > max_chars):
            chunks.append(Chunk(cur, cur[0].start, cur[-1].end))
            cur = []
        cur.append(w)
        if w.text[-1:] in ".!?,;:…":
            chunks.append(Chunk(cur, cur[0].start, cur[-1].end))
            cur = []
    if cur:
        chunks.append(Chunk(cur, cur[0].start, cur[-1].end))
    # hold each chunk until the next one starts (bridging short gaps only)
    for a, b in zip(chunks, chunks[1:]):
        a.end = min(b.start, a.end + linger) if b.start - a.end > linger else b.start
    if chunks:
        chunks[-1].end += linger
    return chunks


def _ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(words: list[Word], max_words: int = 7, max_chars: int = 42) -> str:
    """Closed-caption file for YouTube (longer lines than the burned-in ones)."""
    out = []
    for i, c in enumerate(chunk_words(words, max_words, max_chars, linger=0.6), 1):
        out.append(f"{i}\n{_ts(c.start)} --> {_ts(c.end)}\n{c.text}\n")
    return "\n".join(out)
