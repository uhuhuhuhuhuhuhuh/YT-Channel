"""Olive and Her Three Hearts: a Wonder Bites tiny film.

Every fact on screen is from the sources in film.yaml:
  - octopuses have three hearts: two pump blood through the gills, one to the body
  - their blood is blue because it carries oxygen with copper (hemocyanin), not iron
  - the body heart stops beating while they swim, which tires them, so they prefer to crawl
  - they jet by squirting water, and can change colour in a fraction of a second
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ytc import brand
from ytc import text as ytext
from ytc.film import fx, reef
from ytc.film.core import Beat
from ytc.film.octopus import Octopus, Pose
from ytc.film.paper import blit, hexrgb
from ytc.film.world import Sprite, draw_layer, draw_sprite, prepare_blur, to_screen

INTRO = 4.6
OUTRO = 5.0

BEATS = [
    Beat("Deep down, where the sunlight turns blue, there's a little garden of rocks and swaying kelp.", 0.9),  # 0
    Beat("And if you look very, very closely... someone is hiding.", 0.8),                                       # 1
    Beat("Hello! This is Olive. Olive is an octopus.", 0.8),                                                     # 2
    Beat("Octopuses can change their color in the blink of an eye, to hide... or to say hello!", 0.9),           # 3
    Beat("But Olive has a secret, and it's hidden inside her body.", 0.8),                                       # 4
    Beat("Olive has three hearts!", 1.2),                                                                        # 5
    Beat("Two little hearts pump blood through her gills, so she can breathe.", 0.6),                           # 6
    Beat("And one big heart sends blood all around the rest of her body.", 0.8),                                # 7
    Beat("And look! Olive's blood isn't red like ours. It's blue! It carries oxygen using copper, instead of iron.", 1.0),  # 8
    Beat("Uh-oh. A big shadow is gliding by. Olive would rather not say hello to this one.", 0.5),              # 9
    Beat("So she squirts out water, and jets away. Whoosh!", 0.9),                                               # 10
    Beat("But here's the strange part. When Olive swims, her big heart stops beating.", 0.8),                   # 11
    Beat("Swimming makes her tired very quickly. So octopuses would much rather crawl.", 0.9),                  # 12
    Beat("Olive finds a cozy new hiding spot, and settles in for the night.", 0.9),                             # 13
    Beat("And inside her, three hearts keep beating. Can you count them with me? One... two... three!", 1.0),  # 14
    Beat("See you next time, on Wonder Bites.", 0.6),                                                           # 15
]

FLOOR = 330            # hero-plane sand line (world y)
SURFACE = -1720
OLIVE_KEYS = ["pos", "R", "spread", "wave", "wspeed", "curl", "stretch", "heading", "color", "xray",
              "look", "crawl", "tuck", "big_on", "focus", "count", "blink", "hearts"]


# --------------------------------------------------------------------------
# The world
# --------------------------------------------------------------------------


def build(st) -> None:
    W, H = st.W, st.H
    rng = np.random.default_rng(5)

    # water colour by depth (precomputed strip, cropped per frame)
    stops_y = [SURFACE - 200, -1200, -300, 500]
    stops_c = [np.array(c, float) for c in [(158, 232, 246), (62, 168, 214), (26, 108, 168), (14, 58, 112)]]

    def water(frame, cam, t):
        rows = np.arange(H)
        wy = cam.y + (rows - H / 2) / cam.k * 5.0          # far "virtual" depth for the colour
        rgb = np.stack([np.interp(wy, stops_y, [c[i] for c in stops_c]) for i in range(3)], 1)
        arr = np.empty((H, W, 4), np.uint8)
        arr[..., :3] = rgb[:, None, :].astype(np.uint8)
        arr[..., 3] = 255
        frame.paste(Image.fromarray(arr, "RGBA"))

    st.stack.append(water)

    # very far haze
    far2 = reef.LayerBuilder("far2", 5.5, (-6000, -2600, 9000, 2200), seed=1, shadow=0)
    for x in range(-5800, 9000, 520):
        reef.rock(far2, x + rng.uniform(-150, 150), 1000 + rng.uniform(-60, 60), rng.uniform(300, 520),
                  rng.uniform(220, 380), int(x) % 97, moss=False)
    far2_layer = far2.build(blur=5)

    # far reef + its fish and the passing shark
    far = reef.LayerBuilder("far", 3.2, (-4400, -2400, 7600, 1800), seed=2, shadow=0.2)
    for x in range(-4200, 7600, 380):
        reef.rock(far, x + rng.uniform(-100, 100), 640 + rng.uniform(-40, 40), rng.uniform(180, 320),
                  rng.uniform(120, 230), int(x) % 89 + 3)
    for x in range(-4000, 7600, 260):
        h = rng.uniform(380, 780)
        far.lines([(x, 620, x + rng.uniform(-60, 60), 620 - h, rng.uniform(14, 24))], reef.KELP[1], shadow=0)
    far_layer = far.build(blur=3.2)

    surface = reef.surface_layer(2.2, SURFACE, (-3000, SURFACE - 900, 6000, SURFACE + 200), seed=4)
    sun = reef.glow_disc(st.px(260), (255, 255, 230), 0.9, 1.6)

    # mid reef
    mid = reef.LayerBuilder("mid", 1.8, (-3600, -300, 6600, 1300), seed=3, shadow=0.25)
    reef.sand(mid, 420, 21, amp=24, waves=9)
    for x in range(-3400, 6600, 430):
        reef.rock(mid, x + rng.uniform(-120, 120), 410 + rng.uniform(-10, 20), rng.uniform(120, 230),
                  rng.uniform(80, 160), int(x) % 83 + 11)
        if rng.random() < 0.6:
            reef.coral_branch(mid, x + rng.uniform(-200, 200), 430, int(x) % 71 + 2, rng.uniform(140, 220))
    mid_layer = prepare_blur(mid.build(), 1.4)
    mid_kelp = [prepare_blur(reef.kelp_sprite(1.8, x + rng.uniform(-160, 160), 430, rng.uniform(480, 860),
                                              int(x) % 61 + 5), 1.4)
                for x in range(-3200, 6400, 560)]

    # fish school (far, swimming right) and the shark (far, passing once)
    fish_imgs = [reef.fish_image(st.px(60), c, k, z=2.6) for k, c in
                 enumerate([hexrgb("#FFD23F"), hexrgb("#FF9F1C"), hexrgb("#7FD6FF")])]
    fish = []
    for k in range(11):
        img = prepare_blur(Sprite(fish_imgs[k % 3], (fish_imgs[k % 3].width / 2, fish_imgs[k % 3].height / 2),
                                  0, 0, 2.6, st.H / 1080), 1.6)
        ox, oy, ph = rng.uniform(-260, 260), rng.uniform(-110, 110), rng.uniform(0, 6.28)

        def path(t, ox=ox, oy=oy, ph=ph):
            x = -2600 + ((t * 55 + 800) % 7200) + ox
            return x, 60 + oy + 25 * math.sin(t * 0.8 + ph), 3 * math.sin(t * 2 + ph), True
        img.path = path
        fish.append(img)

    shark_img = reef.shark_image(st.px(520), 2.6)
    shark = prepare_blur(Sprite(shark_img, (shark_img.width / 2, shark_img.height / 2), 0, 0, 2.6,
                                st.H / 1080), 1.2)
    st.assets["shark"] = shark

    # hero plane: Olive's den and the open sand she crosses
    hb = reef.LayerBuilder("hero_back", 1.0, (-1900, -600, 4600, 900), q=1.3 * st.H / 1080, seed=4)
    reef.sand(hb, FLOOR, 7, amp=12, waves=10)
    reef.rock(hb, 60, 235, 300, 200, 301, color=reef.ROCK[1])
    reef.dark_hole(hb, 12, 262, 112, 72, 9)
    reef.coral_branch(hb, -380, FLOOR + 6, 12, 230, reef.CORAL[0])
    reef.fan_coral(hb, 360, FLOOR + 4, 13, 150, reef.CORAL[1])
    reef.seagrass(hb, -560, FLOOR + 10, 14, 150)
    reef.rock(hb, 700, FLOOR - 15, 120, 70, 15)
    reef.rock(hb, 1180, FLOOR - 40, 200, 120, 16)
    reef.coral_branch(hb, 1250, FLOOR - 70, 17, 170, reef.CORAL[2])
    reef.seagrass(hb, 1500, FLOOR + 8, 18, 110, 5)
    for x in (1700, 2050, 2350):
        hb.ellipse(x, FLOOR + 40, 26, 11, (255, 236, 214))           # shells
    reef.rock(hb, 2640, 285, 170, 130, 19, color=reef.ROCK[2])
    reef.rock(hb, 2890, 270, 210, 170, 20, color=reef.ROCK[0])
    reef.dark_hole(hb, 2762, 292, 80, 52, 21)
    reef.fan_coral(hb, 3120, FLOOR + 4, 22, 170, reef.CORAL[3])
    reef.coral_branch(hb, 3330, FLOOR + 6, 23, 210, reef.CORAL[0])
    reef.seagrass(hb, -900, FLOOR + 10, 24, 140)
    reef.seagrass(hb, 3500, FLOOR + 10, 25, 140)
    hero_back = hb.build()
    hero_kelp = [reef.kelp_sprite(1.0, x, FLOOR + 14, h, s, q=1.2 * st.H / 1080, sway=3)
                 for x, h, s in ((-760, 820, 31), (-620, 640, 32), (880, 760, 33), (3420, 860, 34), (3650, 700, 35))]

    hf = reef.LayerBuilder("hero_front", 0.97, (-1900, -200, 4600, 900), q=1.3 * st.H / 1080, seed=5)
    reef.rock(hf, 0, 336, 205, 58, 41, color=reef.ROCK[3])
    reef.seagrass(hf, -230, FLOOR + 30, 42, 120, 6)
    reef.seagrass(hf, 230, FLOOR + 34, 43, 100, 5)
    reef.rock(hf, 2765, 338, 140, 44, 44, color=reef.ROCK[3])
    reef.seagrass(hf, 2600, FLOOR + 34, 45, 110, 5)
    hero_front = hf.build()

    # foreground: big blurry kelp passing close to the lens (hidden while pushed in)
    fg = [prepare_blur(reef.kelp_sprite(0.55, x, FLOOR + 140, 900, s, q=0.55, sway=2.5), 10)
          for x, s in ((-640, 51), (3380, 53))]

    snow_far = fx.MarineSnow(2.6, (-3500, -2400, 6500, 900), 260, seed=1, size=st.px(2.4))
    snow_near = fx.MarineSnow(1.25, (-2000, -2000, 4800, 600), 140, seed=2, size=st.px(3.2))
    bubbles = fx.Bubbles(1.0, seed=3)
    st.assets["bubbles"] = bubbles

    octo = Octopus()
    rays = fx.light_rays(W, H, seed=2)
    vig = fx.vignette(W, H, 0.5)
    grains = fx.grain_frames(W, H, 6, strength=12)
    st.assets.update(octo=octo)

    def layer(L):
        return lambda frame, cam, t: draw_layer(frame, L, cam)

    def sprites(group):
        def draw(frame, cam, t):
            for sp in group:
                draw_sprite(frame, sp, cam, t)
        return draw

    def sun_draw(frame, cam, t):
        sx, sy, s = to_screen(300, SURFACE + 40, 2.2, cam, W, H)
        if sy > -sun.height:
            blit(frame, sun, sx - sun.width / 2, sy - sun.height / 2)

    def shark_draw(frame, cam, t):
        sp = st.assets["shark"]
        if sp.path is not None:
            draw_sprite(frame, sp, cam, t)

    def olive(top: bool):
        def draw(frame, cam, t):
            xr = st.tracks["olive.xray"](t)
            if (xr > 0.5) != top:
                return
            draw_olive(st, frame, cam, t)
        return draw

    def dim(frame, cam, t):
        a = st.tracks["dim"](t)
        if a > 0.01:
            frame.alpha_composite(Image.new("RGBA", frame.size, (4, 16, 40, int(255 * a))))

    def fg_draw(frame, cam, t):
        a = 0.7 * max(0.0, min(1.0, (0.18 - cam.d) / 0.12))
        if a <= 0.01:
            return
        for sp in fg:
            sp.visible = lambda _t, a=a: a
            draw_sprite(frame, sp, cam, t)

    def rays_draw(frame, cam, t):
        depth = max(0.3, min(1.0, 1 - (cam.y - SURFACE) / 2600))
        a = depth * (0.75 + 0.25 * math.sin(t * 0.5))
        im = rays
        if a < 0.999:
            im = rays.copy()
            im.putalpha(rays.getchannel("A").point(lambda v: int(v * a)))
        off = int((-cam.x * 0.06 * cam.k) % (rays.width - W)) if rays.width > W else 0
        blit(frame, im, -off, 0)

    def dusk(frame, cam, t):
        a = st.tracks["dusk"](t)
        if a > 0.01:
            frame.alpha_composite(Image.new("RGBA", frame.size, (40, 26, 92, int(110 * a))))

    def finish(frame, cam, t):
        frame.alpha_composite(vig)
        frame.alpha_composite(grains[int(t * 12) % len(grains)])
        draw_cards(st, frame, t)
        fade = st.tracks["black"](t)
        if fade > 0.01:
            frame.alpha_composite(Image.new("RGBA", frame.size, (6, 10, 24, int(255 * fade))))

    st.stack += [layer(far2_layer), sun_draw, layer(surface), layer(far_layer), sprites(fish), shark_draw,
                 snow_far.draw, layer(mid_layer), sprites(mid_kelp), layer(hero_back), sprites(hero_kelp),
                 olive(False), bubbles.draw, layer(hero_front), dim, olive(True), snow_near.draw, fg_draw]
    st.post += [rays_draw, dusk, finish]

    # screen-space cards
    st.assets["title"] = fx.title_card(["Olive", "and Her", "Three Hearts"], height=st.px(150))
    st.assets["cards"] = []
    st.assets["end"] = end_card(st)


def end_card(st) -> Image.Image:
    W, H = st.W, st.H
    from ytc import scenes

    img = scenes.gradient(W, H, [(0, "grape"), (1, "bubblegum")]).convert("RGBA")
    b = brand.bitsy(st.px(360))
    img.alpha_composite(b, (W // 2 - b.width // 2, int(H * 0.16)))
    f = ytext.font(st.px(120))
    t = ytext.render_block(["WONDER BITES"], f, fill=hexrgb("#FFD23F"), stroke_ratio=0.1)
    img.alpha_composite(t, (W // 2 - t.width // 2, int(H * 0.52)))
    f2 = ytext.font(st.px(46), ytext.BODY)
    t2 = ytext.render_block(["Tiny films about big wonders"], f2, stroke_ratio=0.14)
    img.alpha_composite(t2, (W // 2 - t2.width // 2, int(H * 0.52) + t.height))
    return img


# --------------------------------------------------------------------------
# Drawing Olive + cards
# --------------------------------------------------------------------------


def olive_pose(st, t) -> tuple[Pose, tuple[float, float], float]:
    g = {k: st.tracks["olive." + k](t) for k in OLIVE_KEYS}
    # natural blinks every few seconds, plus any scripted ones
    blink = g["blink"]
    if (t % 3.9) < 0.12 or (t % 7.3) < 0.1:
        blink = 1.0
    p = Pose(spread=g["spread"], wave=g["wave"], wspeed=g["wspeed"], curl=g["curl"], stretch=g["stretch"],
             heading=g["heading"], color=g["color"], xray=g["xray"], blink=blink, look=g["look"],
             crawl=g["crawl"], tuck=g["tuck"], big_on=g["big_on"], focus=g["focus"], count=g["count"],
             hearts=g["hearts"])
    return p, g["pos"], g["R"]


def draw_olive(st, frame, cam, t):
    p, (x, y), R = olive_pose(st, t)
    sx, sy, s = to_screen(x, y, 1.0, cam, st.W, st.H)
    Rpx = R * s
    # soft contact shadow on the sand, fading as she rises
    hgt = FLOOR - (y + R * 1.6)
    if hgt < 420:
        fx_, fy_, fs = to_screen(x, FLOOR + 6, 1.0, cam, st.W, st.H)
        w = int(R * 3.2 * fs * (1 - hgt / 700))
        if w > 6:
            sh = Image.new("RGBA", (w, max(2, w // 5)), (0, 0, 0, 0))
            ImageDraw.Draw(sh).ellipse((0, 0, w - 1, sh.height - 1), fill=(10, 20, 40, int(90 * (1 - hgt / 420))))
            sh = sh.filter(ImageFilter.GaussianBlur(max(1, w / 18)))
            blit(frame, sh, fx_ - w / 2, fy_ - sh.height / 2)
    img, (ax, ay) = st.assets["octo"].render(p, t, Rpx)
    blit(frame, img, sx - ax, sy - ay)


def draw_cards(st, frame, t):
    title = st.assets["title"]
    a = st.tracks["title"](t)
    if a > 0.01:
        fx.place(frame, title, st.W / 2, st.H * 0.42, 0.9 + 0.1 * a, 0, a)
    for img, tr, (cx, cy), ang in st.assets["cards"]:
        v = tr(t)
        if v > 0.01:
            wob = math.sin(t * 3) * 1.5
            fx.place(frame, img, cx * st.W, cy * st.H, 0.6 + 0.4 * min(1.0, v * 1.05), ang + wob * (1 - v) + wob * 0.3,
                     min(1.0, v * 1.4))
    e = st.tracks["endcard"](t)
    if e > 0.01:
        end = st.assets["end"]
        if e < 0.999:
            end = end.copy()
            end.putalpha(end.getchannel("A").point(lambda v: int(v * e)))
        frame.alpha_composite(end)


def card(st, text, t_in, t_out, pos, angle=-3.0):
    img = fx.word_card(text, height=st.px(140 if len(text) < 8 else 124), seed=len(st.assets["cards"]) + 3)
    tr = st.track(f"card{len(st.assets['cards'])}", 0.0)
    tr.move(t_in, t_in + 0.45, 1.0, "back").move(t_out - 0.35, t_out, 0.0, "in")
    st.assets["cards"].append((img, tr, pos, angle))
    st.sfx(t_in, "paper", 0.8)


# --------------------------------------------------------------------------
# Direction
# --------------------------------------------------------------------------


def direct(st) -> None:
    S, E, C = st.start, st.end, st.cue
    O = {k: st.track("olive." + k, v) for k, v in dict(
        pos=(12.0, 262.0), R=52.0, spread=0.32, wave=0.18, wspeed=0.4, curl=0.45, stretch=1.0, heading=0.0,
        color=0.0, xray=0.0, look=0.0, crawl=0.0, tuck=0.75, big_on=1.0, focus=0.0, count=0.0, blink=0.0,
        hearts=0.0).items()}
    st.track("dim", 0.0)
    st.track("dusk", 0.0)
    st.track("title", 0.0).move(0.9, 1.7, 1.0, "out").move(INTRO - 0.7, INTRO - 0.1, 0.0, "in")
    st.track("black", 1.0).move(0.0, 1.4, 0.0, "out")
    st.track("endcard", 0.0).move(E(15) + 0.2, E(15) + 1.2, 1.0, "inout")
    cam = st.cam
    st.sfx(0.6, "chime", 0.7, note=79)

    # 0 — descend from the surface into the reef
    cam.key(0.0, (0.0, -1480.0, -0.15)).move(0.0, S(0), (0.0, -820.0, -0.1), "in")
    cam.move(S(0), E(0) + 0.5, (-60.0, 15.0, -0.05), "out")
    # 1 — push into the den; something is watching
    cam.move(C(1, "closely"), E(1) + 0.4, (18.0, 195.0, 0.32), "inout")
    O["look"].move(C(1, "someone"), C(1, "someone") + 0.5, -0.7).move(C(1, "hiding") - 0.2, C(1, "hiding") + 0.5, 0.7)
    O["pos"].move(C(1, "someone"), C(1, "hiding"), (12.0, 248.0))

    # 2 — Olive pops out and shows her colours
    t = C(2, "Hello")
    O["pos"].move(t, t + 1.4, (40.0, 150.0), "out")
    O["R"].move(t, t + 1.4, 70.0, "out")
    O["tuck"].move(t, t + 1.2, 0.0)
    O["spread"].move(t, t + 1.4, 0.75)
    O["wave"].move(t, t + 1.4, 0.35)
    O["look"].move(t, t + 0.6, 0.0)
    O["color"].move(C(2, "Olive"), C(2, "Olive") + 0.6, 1.0, "out")
    st.sfx(t, "bubbles", 0.6, n=5)
    st.sfx(C(2, "Olive"), "shimmer", 0.7)
    st.assets["bubbles"].spawn(t, 30, 200, 7, 50)
    cam.move(t, E(2) + 0.4, (40.0, 122.0, 0.28), "inout")

    # 3 — colour in the blink of an eye
    O["color"].move(C(3, "hide"), C(3, "hide") + 0.3, 0.04, "out")
    O["color"].move(C(3, "hello") - 0.1, C(3, "hello") + 0.3, 1.0, "out")
    O["spread"].move(C(3, "hide"), C(3, "hide") + 0.3, 0.45).move(C(3, "hello"), C(3, "hello") + 0.4, 0.9, "back")
    st.sfx(C(3, "hide"), "shimmer", 0.5)
    st.sfx(C(3, "hello"), "shimmer", 0.7)
    cam.move(S(3), E(3) + 0.5, (70.0, 128.0, 0.32), "inout")

    # 4–8 — the x-ray: three hearts and blue blood
    cam.move(S(4), E(4) + 0.6, (42.0, 118.0, 0.5), "inout")
    O["xray"].move(C(4, "inside"), C(4, "inside") + 1.0, 1.0)
    st.track("dim").move(C(4, "inside"), C(4, "inside") + 1.0, 0.5)
    st.sfx(C(4, "inside"), "chime", 0.6, note=76)
    t3 = C(5, "three")
    O["hearts"].move(t3 - 0.1, t3 + 0.9, 1.0, "linear")      # the hearts pop in one, two, three
    card(st, "3 HEARTS", C(5, "hearts"), E(5) + 1.1, (0.24, 0.24), -4)
    for k in range(3):
        st.sfx(t3 + k * 0.3, "chime", 0.45, note=(79, 83, 86)[k])
    cam.move(S(5), E(5) + 0.6, (40.0, 112.0, 0.57), "inout")
    O["focus"].set(S(6), 1.0).set(S(7), 2.0).set(S(8), 0.0)
    cam.move(S(6), E(6) + 0.3, (8.0, 128.0, 0.62), "inout")       # lean towards the gills
    cam.move(S(7), E(7) + 0.4, (44.0, 92.0, 0.68), "inout")      # close on the big heart
    card(st, "BLUE BLOOD", C(8, "blue"), C(8, "copper") - 0.2, (0.76, 0.22), 3)
    card(st, "COPPER", C(8, "copper"), E(8) + 0.8, (0.76, 0.22), -2)
    cam.move(S(8), E(8) + 0.5, (82.0, 128.0, 0.48), "inout")      # ease back to see blood reach the arms

    # 9 — a shadow passes; pull back wide
    O["xray"].move(S(9), S(9) + 0.8, 0.0)
    st.track("dim").move(S(9), S(9) + 0.8, 0.0)
    cam.move(S(9), S(9) + 2.6, (360.0, -70.0, -0.22), "inout")
    t9 = S(9)
    sh = st.assets["shark"]

    def shark_path(t, t0=t9):
        f = (t - t0 + 0.5) / 9.5
        if f < 0 or f > 1:
            return (-99999.0, 0.0, 0.0, False)
        return (-1900 + 3900 * f, -700 + 40 * math.sin(f * 6), 2 * math.sin(f * 9), True)
    sh.path = shark_path
    st.sfx(t9, "swell", 0.9, dur=9.0)
    O["look"].move(t9 + 0.8, t9 + 1.6, -0.8).move(E(9) - 1.5, E(9), 0.6)
    O["tuck"].move(C(9, "shadow"), C(9, "shadow") + 0.5, 0.35)
    O["color"].move(C(9, "shadow"), C(9, "shadow") + 0.4, 0.55)

    # 10 — jet away!
    tj = C(10, "squirts")
    for k, v in dict(stretch=1.35, spread=0.12, wave=0.15, wspeed=1.4, curl=0.12, tuck=0.0, look=0.0,
                     color=1.0).items():
        O[k].move(tj - 0.2, tj + 0.4, v)
    O["heading"].move(tj - 0.2, tj + 0.4, 62.0)
    O["pos"].move(tj, E(10) + 0.4, (920.0, -110.0), "out")
    cam.move(tj, E(10) + 0.8, (900.0, -80.0, -0.1), "inout")
    for k in range(4):
        st.assets["bubbles"].spawn(tj + k * 0.45, 40 + k * 230, 160 - k * 70, 9, 45)
    st.sfx(tj, "bubbles", 0.8, n=10, dur=1.8)
    st.sfx(C(10, "Whoosh") - 0.15, "whoosh", 1.0)

    # 11 — gliding: the big heart stops
    O["pos"].move(S(11), E(11) + 0.5, (1520.0, -20.0), "inout")
    O["heading"].move(S(11), S(11) + 1.5, 92.0)
    O["wave"].move(S(11), S(11) + 1.0, 0.1)
    O["xray"].move(S(11) + 0.3, S(11) + 1.1, 0.95)
    st.track("dim").move(S(11) + 0.3, S(11) + 1.1, 0.35)
    O["focus"].set(S(11), 2.0)
    O["big_on"].move(C(11, "stops"), C(11, "stops") + 0.5, 0.0)
    cam.move(S(11), E(11) + 0.4, (1480.0, -10.0, 0.22), "inout")

    # 12 — tired… land and crawl
    O["xray"].move(S(12), S(12) + 0.6, 0.0)
    st.track("dim").move(S(12), S(12) + 0.6, 0.0)
    O["focus"].set(S(12) + 0.6, 0.0)
    O["blink"].set(C(12, "tired"), 1.0).set(C(12, "tired") + 0.5, 0.0)
    tl = C(12, "octopuses")
    O["pos"].move(S(12), tl, (1860.0, 252.0), "inout")
    for k, v in dict(heading=0.0, stretch=1.0, spread=1.2, curl=0.3, wave=0.25, wspeed=0.6).items():
        O[k].move(tl - 0.9, tl, v)
    O["big_on"].move(tl, tl + 0.6, 1.0)
    O["crawl"].move(tl, tl + 0.5, 1.0)
    O["pos"].move(C(12, "crawl"), E(12) + 2.2, (2460.0, 250.0), "linear")
    cam.move(S(12), tl, (1820.0, 160.0, 0.06), "inout")
    cam.move(tl, E(12) + 2.2, (2380.0, 175.0, 0.06), "linear")

    # 13 — a cozy new hiding spot, dusk falls
    O["pos"].move(S(13) + 0.4, C(13, "settles"), (2750.0, 262.0), "inout")
    O["crawl"].move(C(13, "settles") - 0.4, C(13, "settles"), 0.0)
    for k, v in dict(tuck=0.45, spread=0.55, wave=0.18, wspeed=0.35, color=0.6).items():
        O[k].move(C(13, "settles"), E(13) + 0.6, v)
    O["R"].move(C(13, "settles"), E(13), 62.0)
    st.track("dusk").move(S(13), E(13) + 1.0, 1.0)
    cam.move(S(13), E(13) + 0.5, (2730.0, 190.0, 0.28), "inout")

    # 14 — count the hearts
    O["xray"].move(S(14) + 0.2, S(14) + 1.0, 0.8)
    st.track("dim").move(S(14) + 0.2, S(14) + 1.0, 0.25)
    counting = [C(14, "One"), C(14, "two"), C(14, "three", nth=2)]     # "three hearts…" comes first
    for k, tc in enumerate(counting):
        O["count"].move(tc - 0.05, tc + 0.25, float(k + 1), "out")
        st.sfx(tc, "chime", 0.6, note=(72, 76, 79)[k])
    card(st, "1  2  3", counting[2], E(14) + 1.0, (0.5, 0.2), -2)
    cam.move(S(14), E(14) + 0.4, (2748.0, 205.0, 0.46), "inout")

    # 15 — sign off
    O["xray"].move(S(15), S(15) + 0.7, 0.0)
    st.track("dim").move(S(15), S(15) + 0.7, 0.0)
    O["count"].set(S(15) + 0.7, 0.0)
    O["blink"].set(S(15) + 0.2, 1.0)
    st.sfx(E(15) + 0.3, "chime", 0.8, note=72)

    # heartbeats you can hear whenever the hearts are on screen
    period = 60 / 54.0
    tt = 0.0
    while tt < st.duration:
        if O["xray"](tt) > 0.5:
            big = O["big_on"](tt)
            st.sfx(tt + 0.05 * period, "heartbeat", 0.35 + 0.45 * big, pitch=1.0 if big > 0.5 else 1.35)
        tt += period

