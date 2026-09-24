"""Text-to-speech with per-word timings for captions.

Each sentence is synthesised separately and cached on disk, so we know exactly
when every sentence starts. Word timings inside a sentence are estimated from
word length, which is accurate enough for 1–3 word caption chunks.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import audio
from .config import BUILD, ROOT, VOICES, load_config

PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US"


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Speech:
    audio: np.ndarray            # mono float32 @ audio.SR
    words: list[Word]            # timings relative to the start of `audio`

    @property
    def duration(self) -> float:
        return len(self.audio) / audio.SR


_SENTENCE = re.compile(r"(?<=[.!?…])[\"')\]]*\s+")


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE.split(text.strip())]
    return [p for p in parts if p]


def word_weights(words: list[str]) -> np.ndarray:
    """Relative spoken length of each word (letters + a little per word)."""
    w = []
    for word in words:
        letters = len(re.sub(r"[^\w]", "", word))
        digits = len(re.sub(r"\D", "", word))
        w.append(letters + 2 + digits * 3 + (2 if word[-1:] in ",;:" else 0))
    return np.asarray(w, dtype=float)


def distribute(words: list[str], start: float, end: float,
               weights: np.ndarray | None = None) -> list[Word]:
    if not words:
        return []
    if weights is None or len(weights) != len(words):
        weights = word_weights(words)
    edges = start + (end - start) * np.concatenate([[0], np.cumsum(weights)]) / weights.sum()
    return [Word(w, float(a), float(b)) for w, a, b in zip(words, edges[:-1], edges[1:])]


# --------------------------------------------------------------------------
# Engines
# --------------------------------------------------------------------------

_PIPER_CACHE: dict[str, object] = {}


def _piper(text: str, voice_cfg: dict, out: Path) -> None:
    try:
        from piper.config import SynthesisConfig
    except ImportError as e:  # pragma: no cover - depends on the machine
        raise SystemExit("Piper is not installed: pip install piper-tts") from e
    model = ROOT / voice_cfg["model"]
    if not model.exists():
        raise SystemExit(f"Voice model missing: {model}\nRun: ytc voices download")
    _load_piper(voice_cfg)
    voice = _PIPER_CACHE[str(model)]
    syn = SynthesisConfig(length_scale=voice_cfg.get("length_scale", 1.0))
    with wave.open(str(out), "wb") as w:
        voice.synthesize_wav(text, w, syn_config=syn)


def _edge(text: str, voice_cfg: dict, out: Path) -> None:
    try:
        import edge_tts
    except ImportError as e:  # pragma: no cover
        raise SystemExit("edge-tts is not installed: pip install edge-tts") from e
    mp3 = out.with_suffix(".mp3")

    async def run():
        comm = edge_tts.Communicate(text, voice_cfg["voice"], rate=voice_cfg.get("rate", "+0%"))
        await comm.save(str(mp3))

    asyncio.run(run())
    audio.write_wav(out, audio.load_audio(mp3))
    mp3.unlink(missing_ok=True)


ENGINES = {"piper": _piper, "edge": _edge}


def phoneme_weights(sentence: str, voice: str) -> np.ndarray | None:
    """Per-word spoken length from Piper's phonemes (None if unavailable)."""
    cfg = load_config()["voices"][voice]
    model = str(ROOT / cfg.get("model", ""))
    if cfg["engine"] != "piper" or model not in _PIPER_CACHE:
        return None
    try:
        phon = "".join("".join(p) for p in _PIPER_CACHE[model].phonemize(sentence))
    except Exception:  # noqa: BLE001 - fall back to letter counts
        return None
    words = [w for w in phon.split(" ") if w]
    if len(words) != len(sentence.split()):
        return None
    pause = {",": 4, ";": 4, ":": 4, ".": 3, "!": 3, "?": 3}
    return np.asarray([sum(0 if ch in "ˈˌː" else pause.get(ch, 1) for ch in w) + 1 for w in words], float)


def _load_piper(cfg: dict) -> None:
    from piper import PiperVoice

    model = str(ROOT / cfg["model"])
    if model not in _PIPER_CACHE and Path(model).exists():
        _PIPER_CACHE[model] = PiperVoice.load(model)


def synth_sentence(text: str, voice: str) -> np.ndarray:
    """Synthesise one sentence (cached) and return trimmed mono audio."""
    cfg = load_config()["voices"][voice]
    if cfg["engine"] == "piper":
        _load_piper(cfg)
    digest = hashlib.sha1(repr((sorted(cfg.items()), text)).encode()).hexdigest()[:16]
    cache = BUILD / "cache" / "tts" / f"{voice}-{digest}.wav"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(".tmp.wav")
        ENGINES[cfg["engine"]](text, cfg, tmp)
        tmp.replace(cache)
    return audio.trim_silence(audio.load_audio(cache))


def pauses(clip: np.ndarray, min_len: float = 0.12, thresh: float = 0.004) -> list[tuple[float, float]]:
    """(start, end) of silent gaps inside a clip, in seconds."""
    w = int(0.02 * audio.SR)
    if len(clip) < w * 3:
        return []
    e = np.abs(clip[: len(clip) // w * w]).reshape(-1, w).mean(1)
    quiet = e < thresh
    gaps, start = [], None
    for i, q in enumerate(quiet):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) * 0.02 >= min_len and start > 0:
                gaps.append((start * 0.02, i * 0.02))
            start = None
    return gaps


def time_sentence(sentence: str, clip: np.ndarray, voice: str) -> list[Word]:
    """Word timings for one synthesised sentence, snapped to comma pauses."""
    words = sentence.split()
    dur = len(clip) / audio.SR
    weights = phoneme_weights(sentence, voice)
    if weights is None or len(weights) != len(words):
        weights = word_weights(words)
    est = distribute(words, 0.03, dur - 0.03, weights)
    breaks = [i for i, w in enumerate(words[:-1]) if w[-1] in ",;:—"]
    gaps = pauses(clip)
    if not breaks or not gaps:
        return est
    # match each clause break to the nearest unused real pause
    anchors = [(0, 0.03)]
    used: set[int] = set()
    for b in breaks:
        guess = est[b + 1].start
        best = min((g for g in range(len(gaps)) if g not in used),
                   key=lambda g: abs(gaps[g][1] - guess), default=None)
        if best is not None and abs(gaps[best][1] - guess) < 0.7 and gaps[best][1] > anchors[-1][1]:
            used.add(best)
            anchors.append((b + 1, gaps[best][1]))
    anchors.append((len(words), dur - 0.03))
    out: list[Word] = []
    for (i0, t0), (i1, t1) in zip(anchors, anchors[1:]):
        out += distribute(words[i0:i1], t0, t1, weights[i0:i1])
    return out


def speak(text: str, voice: str, spoken: str | None = None) -> Speech:
    """Synthesise a block of narration and return audio + word timings.

    `text` is what appears in captions; `spoken` (optional) is what the voice
    actually reads, e.g. to fix a pronunciation.
    """
    pause = load_config()["audio"]["sentence_pause"]
    gap = np.zeros(int(pause * audio.SR), np.float32)
    chunks: list[np.ndarray] = []
    words: list[Word] = []
    t = 0.0
    if spoken:
        clip = synth_sentence(spoken, voice)
        dur = len(clip) / audio.SR
        return Speech(clip, distribute(text.split(), 0.0, dur))
    for sentence in split_sentences(text):
        clip = synth_sentence(sentence, voice)
        dur = len(clip) / audio.SR
        # the trimmed clip keeps ~30 ms of padding at each end
        words += [Word(w.text, w.start + t, w.end + t) for w in time_sentence(sentence, clip, voice)]
        chunks += [clip, gap]
        t += dur + pause
    return Speech(np.concatenate(chunks[:-1]) if chunks else np.zeros(1, np.float32), words)


# --------------------------------------------------------------------------
# Voice downloads
# --------------------------------------------------------------------------

def download_voices(names: list[str] | None = None) -> list[Path]:
    import urllib.request

    cfg = load_config()["voices"]
    got = []
    for name, vc in cfg.items():
        if vc["engine"] != "piper" or (names and name not in names):
            continue
        model = ROOT / vc["model"]
        stem = model.name.removesuffix(".onnx")            # en_US-kristin-medium
        _, speaker, quality = stem.split("-")
        VOICES.mkdir(exist_ok=True)
        for suffix in (".onnx", ".onnx.json"):
            dest = model.with_name(stem + suffix)
            if dest.exists():
                continue
            url = f"{PIPER_BASE}/{speaker}/{quality}/{stem}{suffix}"
            print(f"downloading {url}")
            urllib.request.urlretrieve(url, dest)
        got.append(model)
    return got
