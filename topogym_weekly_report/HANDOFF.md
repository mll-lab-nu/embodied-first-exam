# Handoff — Real2Sim weekly report deck

`presentation.html` is the English slide deck (28 slides, dark theme).
**It is generated. Never edit it by hand — the next build overwrites your edits.**

`index.html` is the original Chinese single-page report. It is the source of
record for content and is **deliberately left untouched**. Do not overwrite it.

---

## Build

```bash
cd tmp/16_real_to_sim_direct_3dgs
python _gen/prep_assets.py      # only after touching assets/  (see below)
python _gen/build_index.py      # -> presentation.html
```

Any Python with `opencv` works; on this box:
`/u/qwang23/miniconda3/envs/phystwin/bin/python`.

---

## Which file to edit

| I want to change | Edit |
|---|---|
| Wording, numbers, slide order, which figure sits on which slide, adding/removing a slide | `_gen/build_index.py` |
| Colours, spacing, typography, any layout | `_gen/report_style.css` |
| Navigation, keyboard, lazy loading, the index overlay, carousels | `_gen/report_deck.js` |
| The figures and videos themselves | `assets/img/`, `assets/videos/` → then re-run `prep_assets.py` |

`_gen/index.html.pre_en.bak` is a snapshot of the Chinese page taken before the
English rewrite, kept only for diffing.

---

## Adding or replacing an asset

```bash
cp new_figure.jpg assets/img/
python _gen/prep_assets.py       # measures it, and extracts video posters
python _gen/build_index.py
```

`prep_assets.py` writes `_gen/asset_dims.json` (aspect ratios, so an unloaded
figure still reserves the right space) and `assets/posters/*.jpg` (first frame of
every video). Skipping it means a new figure has no aspect ratio and a new video
shows as a black rectangle until played.

---

## Content structure in `build_index.py`

The file is: helpers first, then the slides in order, then the page shell.
Slides are declared top to bottom exactly as they appear in the deck.

```python
slide(sid, part, num, title, lead, body)      # one numbered slide
opener(sid, part, kicker, title, sub, [bullets])   # a Part divider slide
```

`sid` becomes the URL hash (`presentation.html#p22`), so keep ids stable if
anyone has linked to a slide. `part` is `P1` / `P2` / `P3` and drives the tint,
the top-bar highlight and the tick strip.

### Body helpers

| Helper | Use | Rule that matters |
|---|---|---|
| `fig(path, cap)` | one figure | |
| `gallery(items)` | several figures/videos at once | **always exactly 2 per row** — user requirement. Overflow scrolls. Do not go back to `.grid g2`, its `auto-fit` silently gives 3 columns on a wide screen |
| `car(items)` | carousel, 2 per page with arrows | now only on **1.2 / 1.5 / 3.6**. Carousels were removed from 3.2–3.5, 3.7+ and then from **1.4 / 1.6** as well — those show everything expanded via `gallery()`. Do not reintroduce them |
| `embed(src, cap, h)` | a self-contained sub-page inside a slide | used for `mm_gallery/gallery.html` on 2.7. Pair it with `attrs=' data-autoviewer="1"'` on the slide so it loads on entry and is destroyed on leave |
| `scene_card(name, clip, poster, vsrc, mesh, gauss, obj)` | one captured scene on 3.8 | capture clip &#124; its raw 3DGS viewer (load on demand) &#124; the mesh extracted from it |
| `stack(items)` | 4-across pipeline strip | for slides that also carry content below |
| `stack(items, cols=2)` | 2×2 pipeline with a ↓ turn arrow | for slides where the pipeline **is** the whole slide (currently only 2.1) |
| `pills([(text, kind)])` | metric chips | `kind` ∈ `""` / `"win"` / `"bad"` |
| `table(head, rows)`, `note(t)`, `grid(*items)` | | |
| `viewer(shot, page, title, cap, note_, src=None)` | viewer slot | with `src` it is a live, load-on-demand viewer; without it, a placeholder |

### The viewers — now live, loaded on demand

Slides 1.1 and 3.1 carry four live viewers:

| Slide | Viewer | What it is | Size |
|---|---|---|---|
| 1.1 | `kiri_mesh.html` | Kiri Engine LiDAR scan, textured mesh — where we started | 30 MB glb |
| 1.1 | `box4_viewer_ba_raw.html` | box4 scene 3DGS, **BA raw, 1,072,005 gaussians** | 46 MB |
| 3.1 | `box4_franka_compose.html` | scene + Franka, θ-driven | 46 MB |
| 3.1 | `box4_g1_compose.html` | scene + G1/Dex5, 69 joints | 46 MB |
| 3.8 | `bag1 / bag2 / hang1 / cross1 _viewer_raw.html` | the four other captured scenes, raw | 44–58 MB each |

Slide 3.8 is the closing recap: per scene, the capture clip, that viewer, and the
object mesh extracted from the scene (`gs_seg/*_tsdf.ply`, rendered to a still by
a small painter's-algorithm rasteriser — same one as the Kiri poster, and with
the same brightness gain, because those vertex colours also already carry the
room lighting).

**No carved / purged version appears anywhere.** Every pre-existing scene viewer
in `_review/` (`bag1_viewer.html`, `bag2_viewer.html`, …) is a carved build —
compare the gaussian count in its title against `splat.ply ÷ 248` and they are
all short. All five were rebuilt from the untouched `splat.ply` as
`*_viewer_raw.html` (`_gen`-adjacent script:
`self_assets/02_real_to_sim/scripts/_build_raw_viewers.sh`). The
user's position is that carving buys little and must not be reported; do not
reintroduce it, in a viewer, a figure or a sentence.

Everything in `assets/viewers/` is a **symlink** — the three 3DGS pages and the
Kiri `.glb` are not copied in. The two compose viewers `fetch()` their robot
data relative to their own URL, so `franka_local.bin`, `franka_kin.json`,
`g1_local.bin`, `g1_kin.json` are symlinked next to them. Verified 200 over
`http.server`; if a viewer shows the scene but no robot, that symlink is what
broke. (`fetch("save_pose")` 404s and is caught — harmless.)

`kiri_mesh.html` is written by hand (it is not generated) and uses **three.js
vendored locally** in `assets/viewers/vendor/` — no CDN, so it still works on
conference wifi. Two things there will bite you if you touch it:

- the addons (`GLTFLoader`, `OrbitControls`) import the bare specifier `three`,
  so the page carries an **import map**; without it the whole module graph fails
  silently and the viewer sits on "loading" forever;
- they also import each other by relative path (`../utils/BufferGeometryUtils.js`),
  so `vendor/` must keep the upstream `loaders/ utils/ controls/` layout — do not
  flatten it.

Materials are deliberately **unlit** (`MeshBasicMaterial`). A photogrammetry
texture already is the lit appearance of the room; shading it again is what made
it look dark. The brightness slider is a plain exposure multiplier on top. It renders the glb converted from
`work/my_videos/kiri_scene2/processed/model.obj`, with texture / wireframe / reset
buttons and a load progress bar. Its home camera sits **inside** the room: an
outside-in framing of a room scan just shows the shell.

`_gen/test_viewers.py` (playwright) is the runtime check for all of this: nothing
loads until clicked, a click does not open the lightbox, each embedded page
reaches its own ready state, and leaving a slide destroys the frames. Run it
after touching `report_deck.js` or any viewer. It clicks via `evaluate` on
purpose — a live viewer never becomes "stable", so playwright's normal
actionability wait can never pass.

Both 1.1 posters are rendered at their viewer's own opening camera, so the still
matches what appears after loading — `_box4_raw_poster.py` (gsplat) and the
painter's-algorithm rasteriser used for the Kiri mesh.

Quota note: `/work/nvme/bfuo` has ~430 GB free (1.52 T of 1.95 T soft) — it is
`/work/hdd/bfuo` and the `bfaq` / `bhao` allocations that are over. Use `quota`
and read the right row before assuming there is no room.

**Why they are not plain iframes:** each is a live WebGL context on a 40 MB
document. Three resident at once pin GPU memory and keep render loops running
for the whole talk. So:

- a slot is a **poster with a Load button** — nothing is fetched until clicked;
- leaving the slide **destroys** the iframe (`src='about:blank'` then
  `.remove()`); hiding it would not release the context;
- a `×` in the corner unloads it manually without leaving the slide;
- add `data-autoviewer="1"` on a slide to load its viewers on entry instead of
  on click — deliberately off, three heavy loads on a page turn is worse.

Keyboard focus inside the iframe belongs to the viewer, so `←`/`→` will not flip
slides while you are dragging the model. Click outside the frame first.

`viewer(shot, page, title, cap, note_, src=None)`: pass `src` for a live viewer,
omit it for a placeholder. All four slots are live now — no placeholders remain.

### 2.7 — the Mitsuba / MuJoCo wipe gallery

`mm_gallery/` is a **self-contained component written separately** (its own
`gallery.html`, images, and an inline-embed variant). The deck embeds it with
`embed()` in an iframe, on a slide marked `data-autoviewer="1"`: it appears as
soon as you reach 2.7 and its ~4 MB of panels are dropped when you leave. That
was chosen over the inline variant so the component keeps its own scroll and
theme and cannot collide with the deck's CSS.

Its UI was translated to English **at the generator** (`_gen/build_mm_gallery.py`
for the labels and presets, `_gen/mm_gallery.py` for the per-robot notes), not in
the generated files — regenerate with:

```bash
python _gen/build_mm_gallery.py         # page only, seconds
# GPU re-render of the panels, ~2 min, only if samples/robots change:
python _gen/mm_gallery.py
```

The frame height comes from `--eh` on the slot. The `.viewer-slot.embed` rules
must stay **after** the `.vlive.live` ones in the stylesheet: those give `.vstage`
`flex:1` inside a 660 px slot at equal specificity, and if they win the iframe
collapses to its 150 px default.

---

## Deck behaviour (already built, in `report_deck.js`)

- `←` `→` change slide; `↑` `↓` scroll within a slide; `Home`/`End`; type a
  number + `Enter` to jump; `G` opens the slide index; `Esc` closes overlays.
- A slide scrolls internally — a tall slide is fine and expected.
- **Lazy media**: `src` lives in `data-src` and is attached only while that slide
  is on screen, then dropped. The unload is delayed 380 ms so it does not fight
  the transition, and it re-checks that the slide is still not current before
  firing — without that check, two navigations inside 380 ms strip the media off
  the slide you just landed on and the figures come up blank. This is what keeps a 26 MB asset folder usable.
  If you add media by hand rather than via the helpers, give it
  `class="lz" data-src="..."` or it will load eagerly.
- The bottom bar shows deck progress (tinted per Part), the current Part + title,
  a scroll meter that appears only when the slide overflows, a go-to box and the
  index button.

---

## House rules learned the hard way

- Keep the **dark background**. Several figures are rendered on dark and invert
  badly on white.
- `/work` is **past its soft quota** (grace timer running). Check with the
  `quota` command — not `df -h`, which reports the whole Lustre filesystem and
  shows 100 % / 0 available even when the allocation has room. Do not copy large
  files in; symlink or reference in place.
- The audience reads the visuals; the speaker narrates. Prefer a figure, a short
  problem line and keyword chips over paragraphs.
- Headless Chromium from Playwright has **no H.264 decoder**, so `.mp4` will not
  play there and screenshots of videos come out black. That is a test-harness
  limitation, not a page bug — check videos in a real browser.
