"""Encode and audit the eight presentation replays; never package privileged poses."""

import argparse
import hashlib
import html
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont

ORDER = [
    "neural-fly",
    "neural-landing",
    "anycar",
    "g1",
    "go2-attitude",
    "go2-weave",
    "go2-forward-jump",
    "go2-yaw-jump",
]
FONT = Path("/usr/share/fonts/truetype/dejavu")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def run(args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)


def overlay(spec, destination, index, width=1920, height=1080):
    im = Image.new("RGBA", (width, height))
    d = ImageDraw.Draw(im)

    def font(n, bold=False):
        return ImageFont.truetype(
            str(FONT / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")), n
        )

    d.rectangle((0, 0, width, 142), fill=(13, 22, 28, 232))
    if spec["name"] == "g1":
        # Keep foot contact visible throughout the stair approach and descent.
        d.rectangle((1120, height - 100, width, height), fill=(13, 22, 28, 238))
    else:
        d.rectangle((0, height - 68, width, height), fill=(13, 22, 28, 238))
    d.rectangle((0, 0, 7, 142), fill=(66, 212, 178, 255))
    d.text((40, 18), "roboEngineer", font=font(23, True), fill=(86, 226, 192, 255))
    d.text((40, 52), spec["title"], font=font(37, True), fill="white")
    d.text((40, 102), spec["subtitle"], font=font(22), fill=(195, 210, 218, 255))
    d.text(
        (width - 40, 22),
        (f"{index + 1:02d} / 08" if index is not None else "EXTRA DEMO")
        + "    •    BLENDER CYCLES",
        anchor="ra",
        font=font(19),
        fill=(195, 210, 218, 255),
    )
    good = bool(spec["metrics"].get("success"))
    d.text(
        (width - 40, 63),
        spec["status"],
        anchor="ra",
        font=font(22, True),
        fill=(102, 231, 180, 255) if good else (255, 187, 105, 255),
    )
    d.text(
        (width - 40, 104),
        "Reference controller replay  •  1× speed",
        anchor="ra",
        font=font(19),
        fill=(195, 210, 218, 255),
    )
    if spec["name"] == "g1":
        d.text(
            (1140, height - 85), spec["note"], font=font(17), fill=(218, 225, 230, 255)
        )
        d.text(
            (1140, height - 56),
            "Presentation render • exact MuJoCo motion",
            font=font(16),
            fill=(149, 169, 180, 255),
        )
        d.text(
            (1140, height - 29),
            "New cameras / materials / lighting • not agent feedback",
            font=font(16),
            fill=(149, 169, 180, 255),
        )
    else:
        d.text(
            (40, height - 54), spec["note"], font=font(19), fill=(218, 225, 230, 255)
        )
        d.text(
            (40, height - 28),
            "Presentation render • exact MuJoCo motion • cameras / materials / lighting changed • not agent feedback",
            font=font(16),
            fill=(149, 169, 180, 255),
        )
    im.save(destination)


def audit(video, expected_frames=None):
    raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(video),
        ]
    )
    info = json.loads(raw)
    stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (stream["width"], stream["height"]) == (1920, 1080)
    assert stream["r_frame_rate"] == "25/1"
    if expected_frames is not None:
        assert int(stream["nb_read_frames"]) == expected_frames, (
            video,
            stream["nb_read_frames"],
            expected_frames,
        )
    run(["ffmpeg", "-v", "error", "-threads", "4", "-i", str(video), "-f", "null", "-"])
    return dict(
        sha256=sha(video),
        bytes=video.stat().st_size,
        frames=int(stream["nb_read_frames"]),
        duration_s=float(info["format"]["duration"]),
        width=1920,
        height=1080,
        fps=25,
        full_decode_passed=True,
    )


def encode(root, name):
    spec = json.loads((root / "captures" / name / "scene.json").read_text())
    frames = root / "renders" / name
    receipt = json.loads((frames / "render-receipt.json").read_text())
    assert receipt["source_record_sha256"] == spec["source_record_sha256"]
    assert len(list(frames.glob("[0-9][0-9][0-9][0-9][0-9].png"))) == spec["frames"]
    out = root / "delivery"
    out.mkdir(exist_ok=True)
    overlay_path = out / (name + "-overlay.png")
    overlay(spec, overlay_path, ORDER.index(name) if name in ORDER else None)
    video = out / (name + ".mp4")
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-threads",
            "4",
            "-framerate",
            "25",
            "-i",
            str(frames / "%05d.png"),
            "-i",
            str(overlay_path),
            "-filter_complex_threads",
            "4",
            "-filter_complex",
            "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p",
            "-c:v",
            "libx264",
            "-threads",
            "6",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-movflags",
            "+faststart",
            "-an",
            str(video),
        ]
    )
    checked = audit(video, spec["frames"])
    poster = out / (name + ".jpg")
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-ss",
            str(spec.get("poster_time_s", min(spec["duration_s"] * 0.35, 5))),
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(poster),
        ]
    )
    result = dict(
        name=name,
        title=spec["title"],
        subtitle=spec["subtitle"],
        status=spec["status"],
        note=spec["note"],
        source_record_sha256=spec["source_record_sha256"],
        original_state_sha256=spec["original_state_sha256"],
        presentation_only=True,
        agent_feedback=False,
        video=video.name,
        poster=poster.name,
        **checked,
        render=receipt,
        rotor_animation=spec.get("rotor_animation"),
    )
    if spec.get("showcase_revision"):
        result.update(
            showcase_revision=spec["showcase_revision"],
            benchmark_case=spec["benchmark_case"],
            gap_m=spec["course"]["gap"],
        )
    (out / (name + ".json")).write_text(json.dumps(result, indent=2) + "\n")
    print("ENCODED", name, checked, flush=True)


def collection(root):
    out = root / "delivery"
    items = [json.loads((out / (n + ".json")).read_text()) for n in ORDER]
    # Continuous excerpts at their original speed, including the complete jump attempts.
    excerpts = [
        ("neural-fly", 4, 7),
        ("neural-landing", 5, 7),
        ("anycar", 2, 7),
        ("g1", 7, 7),
        ("go2-attitude", 1, 6),
        ("go2-weave", 3, 6),
        ("go2-forward-jump", 0, 6),
        ("go2-yaw-jump", 0, 6),
    ]
    segments = root / "montage-segments"
    segments.mkdir(exist_ok=True)
    for name, start, duration in excerpts:
        run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-ss",
                str(start),
                "-i",
                str(out / (name + ".mp4")),
                "-t",
                str(duration),
                "-c:v",
                "libx264",
                "-threads",
                "4",
                "-preset",
                "slow",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-an",
                str(segments / (name + ".mp4")),
            ]
        )
    playlist = segments / "concat.txt"
    # All filenames here are controlled task identifiers, never shell-interpolated paths.
    playlist.write_text("".join(f"file '{name}.mp4'\n" for name, _, _ in excerpts))
    montage = out / "roboengineer-eight-objectives.mp4"
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "1",
            "-i",
            str(playlist),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(montage),
        ]
    )
    checked = audit(montage, sum(d * 25 for _, _, d in excerpts))
    manifest = dict(
        schema="roboengineer-presentation-delivery/1",
        presentation_only=True,
        agent_feedback=False,
        description="Eight existing reference-controller demonstrations, re-rendered in Blender from verified MuJoCo poses. No new agent scores.",
        montage=dict(
            video=montage.name,
            excerpts=[dict(name=n, start_s=s, duration_s=d) for n, s, d in excerpts],
            **checked,
        ),
        videos=items,
    )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    cards = []
    for i in items:
        cards.append(
            f'<article><h2>{html.escape(i["title"])} <small>{html.escape(i["subtitle"])}</small></h2><video controls preload="metadata" poster="{i["poster"]}" src="{i["video"]}"></video><p>{html.escape(i["status"])} · {i["duration_s"]:g} s</p><p class="note">{html.escape(i["note"])}</p><a href="{i["video"]}" download>Download full video</a></article>'
        )
    (out / "index.html").write_text(
        """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>roboEngineer — eight control objectives</title><style>body{margin:0;background:#0d161c;color:#e6edf2;font:17px system-ui;line-height:1.5}main{max-width:1440px;margin:auto;padding:48px 28px}h1{font-size:48px;letter-spacing:-2px;margin:0}h2{font-size:23px}small{display:block;color:#a9bcc8;font-size:16px;font-weight:400}video{width:100%;border-radius:12px;background:#080d10}section{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:30px}article{background:#16232c;border:1px solid #2c3a43;padding:20px;border-radius:16px}a{color:#66e7b4}.note{color:#a9bcc8;font-size:14px}.intro{max-width:970px}.hero{margin:24px 0 42px}</style><main><p style="color:#66e7b4">ROBOTIC ENGINEERING BENCHMARK</p><h1>Eight control objectives.</h1><p class="intro">Blender Cycles / OptiX · 1080p · 25 fps · real-time playback. Robot geometry and motion come from saved MuJoCo evaluations. Materials, cameras, lighting and the studio are presentation changes. These are reference-controller demonstrations, not new coding-agent results or the feedback videos agents received.</p><p class="note">G1’s selected case succeeds; both held-out banks remain partially solved. Go2 weave, forward jump and yaw jump are unsolved development references; their failed motion is preserved.</p><div class="hero"><video controls preload="metadata" src="roboengineer-eight-objectives.mp4"></video><p><a href="roboengineer-eight-objectives.mp4" download>Download the 52-second PR montage</a> · <a href="manifest.json">Provenance and decode checks</a></p></div><section>"""
        + "".join(cards)
        + "</section></main>"
    )
    (out / "README.txt").write_text(
        "roboEngineer PR presentation videos\n\nOpen index.html for all eight complete videos. The montage contains consecutive excerpts at 1x speed; exact start times are in manifest.json.\n\nRendered with Blender 4.5.3 LTS, Cycles, OptiX, 32 samples, GPU denoising, 1920x1080 at 25 fps. Motion was sampled from verified MuJoCo states, with no Blender physics or motion retargeting. Canonical agent feedback is unchanged.\n\nG1 selected case passes but both held-out plants remain partial. Go2 weave, forward jump and yaw jump are unsolved; failures are preserved. Neural Fly uses synthetic vector-wind dynamics, not paper-calibrated directional aerodynamics. AnyCar uses a compact Silverstone-inspired route, not the exact circuit outline.\n\nVideos contain no audio. No model score, new Harbor run, physical robot deployment or Blender-based evaluation is claimed. Captured privileged poses and bank data are deliberately excluded from this delivery.\n"
    )
    print("COLLECTION", checked, flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--only", choices=ORDER + ["anycar-jump", "anycar-drift-v3"])
    p.add_argument("--collection-only", action="store_true")
    a = p.parse_args()
    if not a.collection_only:
        for name in [a.only] if a.only else ORDER:
            encode(a.root, name)
    if not a.only:
        collection(a.root)


if __name__ == "__main__":
    main()
