"""Film engine tests: tracks, projection, the octopus, and the example film (no TTS needed)."""

import math

import numpy as np
import pytest
from PIL import Image

from ytc import tts
from ytc.film import core, octopus, paper
from ytc.film.world import Camera, Layer, Track, draw_layer, paste_affine, scale_at, to_screen


def test_track_holds_then_eases_to_keys():
    tr = Track(0.0).move(1.0, 2.0, 10.0, "linear").set(3.0, 5.0)
    assert tr(0.5) == 0.0
    assert tr(1.5) == pytest.approx(5.0)
    assert tr(2.5) == 10.0
    assert tr(3.0) == 5.0
    tup = Track((0.0, 0.0)).move(0, 1, (2.0, 4.0), "linear")
    assert tup(0.5) == pytest.approx((1.0, 2.0))


def test_parallax_far_layers_move_less():
    cam0, cam1 = Camera(0, 0), Camera(100, 0)
    near = to_screen(0, 0, 1.0, cam0, 1920, 1080)[0] - to_screen(0, 0, 1.0, cam1, 1920, 1080)[0]
    far = to_screen(0, 0, 4.0, cam0, 1920, 1080)[0] - to_screen(0, 0, 4.0, cam1, 1920, 1080)[0]
    assert near == pytest.approx(100)
    assert far == pytest.approx(25)
    assert scale_at(1.0, Camera(0, 0, 0.5)) == pytest.approx(2.0)


def test_draw_layer_places_pixels_where_projection_says():
    img = Image.new("RGBA", (40, 40), (255, 0, 0, 255))
    L = Layer("t", 1.0, img, ox=-20, oy=-20, q=1.0)
    frame = Image.new("RGBA", (200, 100), (0, 0, 0, 255))
    draw_layer(frame, L, Camera(0, 0))
    assert frame.getpixel((100, 50))[:3] == (255, 0, 0)       # centre of the frame
    assert frame.getpixel((10, 10))[:3] == (0, 0, 0)


def test_paste_affine_offscreen_is_a_noop():
    frame = Image.new("RGBA", (50, 50), (0, 0, 0, 255))
    paste_affine(frame, Image.new("RGBA", (10, 10), (255, 255, 255, 255)), (1, 0, 500, 0, 1, 500))
    assert frame.getpixel((25, 25)) == (0, 0, 0, 255)


def test_paper_cut_has_grain_and_soft_edges():
    m = Image.new("L", (200, 200), 0)
    from PIL import ImageDraw

    ImageDraw.Draw(m).ellipse((20, 20, 180, 180), fill=255)
    piece = paper.cut(m, (200, 100, 50))
    assert piece.size == (100, 100)
    alphas = set(np.unique(np.asarray(piece.getchannel("A"))).tolist())
    assert 0 in alphas and 255 in alphas and len(alphas) > 2      # anti-aliased edge


def test_heartbeat_envelope_has_two_thumps():
    vals = [octopus.beat(t / 100, 60) for t in range(100)]
    peaks = [i for i in range(1, 99) if vals[i] > vals[i - 1] and vals[i] > vals[i + 1] and vals[i] > 0.3]
    assert len(peaks) == 2


@pytest.mark.parametrize("pose", [octopus.Pose(), octopus.Pose(xray=1, count=2), octopus.Pose(stretch=1.35, heading=60),
                                  octopus.Pose(hearts=0.4, xray=1, big_on=0)])
def test_octopus_renders_in_every_mode(pose):
    img, (ax, ay) = octopus.Octopus().render(pose, 1.0, 40)
    assert img.mode == "RGBA" and img.getbbox() is not None
    assert 0 < ax < img.width and 0 < ay < img.height


def fake_timing(spec):
    """Word timings without running TTS: ~0.35 s per word."""
    t = spec.module.INTRO
    starts, ends, words = [], [], []
    for b in spec.module.BEATS:
        n = len(b.text.split())
        starts.append(t)
        words.append(tts.distribute(b.text.split(), t, t + 0.35 * n))
        t += 0.35 * n
        ends.append(t)
        t += b.pause
    return core.Timing(starts, ends, words, t + spec.module.OUTRO)


def test_example_film_builds_and_renders_small_frames():
    spec = core.load_film("olive")
    st = core.Stage(spec, fake_timing(spec), scale=0.25)
    assert st.W == 480 and st.H == 270
    for t in (1.0, st.cue(5, "three") + 1.0, st.cue(10, "Whoosh"), st.duration - 1):
        f = st.frame(t)
        assert f.size == (480, 270)
    # every sound cue lands inside the film
    assert all(0 <= e.t <= st.duration for e in st.events)
    assert any(e.kind == "heartbeat" for e in st.events)


def test_cue_finds_nth_word():
    spec = core.load_film("olive")
    st = core.Stage(spec, fake_timing(spec), scale=0.25)
    first = st.cue(14, "three")
    second = st.cue(14, "three", nth=2)
    assert second > first
    with pytest.raises(KeyError):
        st.cue(0, "giraffe")
    assert math.isfinite(st.cue(2))
