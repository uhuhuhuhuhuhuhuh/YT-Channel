"""Fast unit tests: no voice models or network needed."""

import numpy as np
import pytest

from ytc import audio, captions, scenes, tts
from ytc.episode import EpisodeError, Sprite, list_episodes, load_episode
from ytc.render import ease_out_back, sprite_pose
from ytc.upload import build_body, build_description


def test_all_episodes_load():
    eps = [load_episode(p) for p in list_episodes()]
    assert eps, "no episodes found"
    for ep in eps:
        assert ep.sources, f"{ep.slug} has no sources"
        assert len(ep.title) <= 100


def test_episode_level_bg_params_apply_only_to_default_bg():
    ep = load_episode("007")
    assert ep.segments[0].bg == "party" and ep.segments[0].bg_params == {"scheme": "sunset"}
    meadow = next(s for s in ep.segments if s.bg == "meadow")
    assert meadow.bg_params == {}


def test_bad_motion_rejected(tmp_path):
    ep_dir = tmp_path / "999-bad"
    ep_dir.mkdir()
    (ep_dir / "episode.yaml").write_text(
        "title: x\nsources: [a]\nsegments:\n  - say: hi\n    sprites: [{name: octopus, motion: moonwalk}]\n")
    with pytest.raises(EpisodeError):
        load_episode(ep_dir)


def test_split_sentences():
    assert tts.split_sentences("Hi there! How are you? Fine.") == ["Hi there!", "How are you?", "Fine."]


def test_distribute_covers_span_in_order():
    words = tts.distribute("one two three".split(), 1.0, 4.0)
    assert words[0].start == pytest.approx(1.0)
    assert words[-1].end == pytest.approx(4.0)
    assert all(a.end == pytest.approx(b.start) for a, b in zip(words, words[1:]))


def test_pauses_detects_gap():
    sr = audio.SR
    tone = np.sin(np.arange(sr // 2) / sr * 2 * np.pi * 220).astype(np.float32) * 0.5
    clip = np.concatenate([tone, np.zeros(sr // 4, np.float32), tone])
    gaps = tts.pauses(clip)
    assert len(gaps) == 1
    assert gaps[0][0] == pytest.approx(0.5, abs=0.05)
    assert gaps[0][1] == pytest.approx(0.75, abs=0.05)


def test_caption_chunks_break_on_punctuation_and_length():
    words = tts.distribute("Did you know an octopus has three hearts? Yes!".split(), 0, 5)
    chunks = captions.chunk_words(words, max_words=3, max_chars=16)
    texts = [c.text for c in chunks]
    assert texts[-1] == "Yes!"
    assert all(len(c.words) <= 3 for c in chunks)
    assert any(t.endswith("hearts?") for t in texts)


def test_srt_format():
    srt = captions.to_srt(tts.distribute("hello there friend".split(), 0, 1.5))
    assert srt.startswith("1\n00:00:00,000 --> ")


@pytest.mark.parametrize("name", sorted(scenes.BACKGROUNDS))
def test_backgrounds_render(name):
    bg = scenes.make(name, 216, 384, {}, seed=1)
    a, b = bg.frame(0.0), bg.frame(1.0)
    assert a.size == (216, 384) and a.mode == "RGB"
    assert b.size == a.size


def test_backgrounds_deterministic():
    f1 = scenes.make("ocean", 216, 384, {}, seed=5).frame(0.7)
    f2 = scenes.make("ocean", 216, 384, {}, seed=5).frame(0.7)
    assert f1.tobytes() == f2.tobytes()


def test_music_generators_are_deterministic_and_bounded():
    for name, fn in audio.MUSIC.items():
        a = fn(3.0, seed=2)
        b = fn(3.0, seed=2)
        assert len(a) == 3 * audio.SR, name
        assert np.array_equal(a, b), name
        assert np.max(np.abs(a)) <= 1.0


def test_mix_ducks_music_under_speech():
    sr = audio.SR
    speech = np.zeros(sr * 2, np.float32)
    speech[sr:] = 0.5 * np.sin(np.arange(sr) / sr * 2 * np.pi * 200)
    music = np.full(sr * 2, 0.5, np.float32)
    out = audio.mix(speech, music, np.zeros(1, np.float32), 1.0, 0.25, 0)
    quiet_part = np.abs(out[sr // 4: sr // 2]).mean()
    assert quiet_part == pytest.approx(0.5, rel=0.05)


def test_pop_entrance_overshoots_then_settles():
    assert ease_out_back(0) == pytest.approx(0)
    assert ease_out_back(1) == pytest.approx(1)
    assert max(ease_out_back(p / 20) for p in range(21)) > 1.0
    s = Sprite(name="octopus", motion="none")
    assert sprite_pose(s, 0.0, 5, 1080, 1920).sx == pytest.approx(0)
    assert sprite_pose(s, 2.0, 5, 1080, 1920).sx == pytest.approx(1)


def test_walk_reaches_destination():
    s = Sprite(name="octopus", motion="walk", x=0.2, to=(0.8, 0.45), enter="none")
    end = sprite_pose(s, 4.0, 4.0, 1000, 1000)
    assert end.x == pytest.approx(800)


def test_upload_body_is_made_for_kids_and_private():
    ep = load_episode("001")
    body = build_body(ep)
    assert body["status"]["selfDeclaredMadeForKids"] is True
    assert body["status"]["privacyStatus"] == "private"
    assert body["snippet"]["categoryId"] == "27"
    scheduled = build_body(ep, privacy="public", publish_at="2026-10-05T15:30:00Z")
    assert scheduled["status"]["privacyStatus"] == "private"
    assert scheduled["status"]["publishAt"] == "2026-10-05T15:30:00Z"


def test_description_has_sources_and_disclosure():
    desc = build_description(load_episode("001"))
    assert "Sources" in desc and "text-to-speech" in desc and "#shorts" in desc
    assert len(desc) <= 5000


def test_check_flags_emoji_headline():
    from ytc.cli import check_episode

    ep = load_episode("001")
    ep.segments[0].headline = "YAY 🎉"
    assert any("can't draw" in p for p in check_episode(ep, with_voice=False))
