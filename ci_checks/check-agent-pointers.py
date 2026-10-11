#!/usr/bin/env python3
"""No pointer to an upstream solution in what the agent can read (PROTOCOL §2.7: "a solution, or a pointer to one,
anywhere the agent can reach" is a MUST NOT).

The agent reads `instruction.md` and what `environment/` puts in its container; `environment/sim/`, `environment/scorer/`
and `environment/rcb_monitor/` run in other containers (check-standard-agent-image.sh) and are not scanned. In those
files this check refuses:
  1. an http(s) URL to a host that serves code, datasets, models or videos (HOSTS): upstream repositories, demonstration
     datasets, trained policies, project pages, solution videos;
  2. a key that locates a source (KEYS): `source_url`, `source_viewer_url`, `demo_url`, `dataset_url`, ...;
  3. the name of a demonstration or dataset file (FILES): `*.hdf5`, `*.mcap`, `*.parquet`, `*.rlds`, a Hugging Face
     `datasets/<org>/<name>` id.
A legitimate mention (a licence notice that must name its source) is listed in ALLOW with its reason. The egress
allowlist is what stops a download; this check keeps the address out of the task. Board 0072: RoboTangle's
`reference_scene.json` carried `source_url` of the upstream demonstration, and one trial downloaded and replayed it.
That file was in the simulator image, which this check cannot read: an image's own files are reviewed when the image
is built (docs/LEAKAGE.md).

Usage: check-agent-pointers.py [task dirs...]   (default: all of tasks/*)
"""
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIDECAR_DIRS = {"sim", "scorer", "rcb_monitor"}          # other containers' files under environment/
MAX_BYTES = 8 << 20                                        # larger files are assets (meshes, arrays), not text
HOSTS = re.compile(
    r"https?://(?:[A-Za-z0-9-]+\.)*(?:github\.com|githubusercontent\.com|github\.io|gitlab\.com|bitbucket\.org|"
    r"huggingface\.co|hf\.co|kaggle\.com|zenodo\.org|drive\.google\.com|docs\.google\.com|sites\.google\.com|"
    r"storage\.googleapis\.com|dropbox\.com|box\.com|amazonaws\.com|youtube\.com|youtu\.be|vimeo\.com|bilibili\.com)"
    r"(?:[/:?#][^\s\"'<>)\]]*)?", re.I)
KEYS = re.compile(r"""["']?\b((?:source|demo|demonstration|dataset|video|viewer|source_viewer|methods|reference|solution|
                               checkpoint|ckpt|policy|pretrained|repo|download)[_-]?(?:url|uri|link|repo|repo_id)|repo_id)\b["']?\s*[:=]""",
                  re.I | re.X)
FILES = re.compile(r"""(?<![\w.-])(?:[\w.-]+\.(?:hdf5|h5|mcap|parquet|rlds|tfrecord)\b|datasets/[\w.-]+/[\w.-]+)""", re.I)
# (task-name regex, path regex, matched-text regex, reason)
ALLOW = [
    (r"^maniguard-", r"^environment/instance/NOTICE$", r"datasets/IDEAS-Lab-Northwestern/ManiGuard-Bench|github\.com/NU-IDEAS-Lab/ManiGuard",
     "CC BY-NC 4.0 attribution the licence requires, of the scene files' dataset (its demonstrations are other datasets, not named)"),
]


def agent_files(task: pathlib.Path):
    f = task / "instruction.md"
    if f.is_file():
        yield f
    env = task / "environment"
    for p in sorted(env.rglob("*")) if env.is_dir() else []:
        rel = p.relative_to(env).parts
        if p.is_file() and not p.is_symlink() and rel[0] not in SIDECAR_DIRS and "__pycache__" not in rel:
            yield p


def findings(task: pathlib.Path):
    for p in agent_files(task):
        if p.stat().st_size > MAX_BYTES:
            continue
        raw = p.read_bytes()
        if b"\0" in raw[:4096]:
            continue
        text = raw.decode("utf-8", "replace").replace("\\/", "/"); rel = p.relative_to(task).as_posix()    # JSON may escape "/"
        for kind, rx in (("URL", HOSTS), ("key", KEYS), ("file", FILES)):
            for m in rx.finditer(text):
                hit = m.group(1) if kind == "key" else m.group(0)
                if any(re.search(t, task.name) and re.search(pp, rel) and re.search(h, hit) for t, pp, h, _ in ALLOW):
                    continue
                yield rel, text.count("\n", 0, m.start()) + 1, kind, hit[:120]


def main(argv):
    tasks = [pathlib.Path(a) for a in argv] or sorted(p for p in (ROOT / "tasks").iterdir() if (p / "task.toml").is_file())
    bad = 0
    for t in tasks:
        for rel, line, kind, hit in findings(t):
            print(f"FAIL {t.name}: {rel}:{line}: {kind} `{hit}` locates upstream material in a file the agent reads (PROTOCOL §2.7)")
            bad += 1
    if bad:
        print(f"{bad} pointer(s). Remove them from the agent's files, or list a legitimate one in ALLOW with its reason.")
    else:
        print(f"agent pointers: the agent's files of {len(tasks)} task(s) locate no upstream material (PROTOCOL §2.7)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
