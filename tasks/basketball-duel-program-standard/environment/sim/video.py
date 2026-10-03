"""replay.mp4: a fresh replay of the recorded shots, broadcast camera + rim camera side by side, real time during
throws and flights, score overlay."""
from __future__ import annotations

import numpy as np

import bball

W, H = 560, 420


def render(actions, seed, out, fps=25, plan=None, label=""):
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw
    g = bball.Game(seed, plan)
    g.record_snaps = False
    wr = imageio.get_writer(out, fps=fps, macro_block_size=8)
    st = {"n": 0, "last": ""}

    def frame(game, mode):
        st["n"] += 1
        every = 4
        if st["n"] % every:
            return
        a = game.render_cam("broadcast", W, H)
        b = game.render_cam("rim", W, H)
        im = Image.fromarray(np.concatenate([a, b], 1))
        dr = ImageDraw.Draw(im)
        txt = f"{label}shot {game.shot + 1}/{len(game.plan)}  made {game.made}   last: {st['last']}"
        dr.rectangle((0, 0, 2 * W, 18), fill=(0, 0, 0))
        dr.text((6, 4), txt, fill=(255, 255, 255))
        wr.append_data(np.asarray(im))

    g.frame_cb = frame
    for a in actions:
        if a["shot"] >= len(g.plan):
            g.extend(a.get("spot", 0))
        r = g.shoot(a["decision"])
        st["last"] = f"shot {r['shot']}: {r['result']}"
    wr.close()
