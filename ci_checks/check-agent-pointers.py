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
     `datasets/<org>/<name>` id;
  4. a key that names the demonstration or episode a file was made from (IDS): `"demo": "<demo id>"`, `demo_id`,
     `episode_id`, `source_demo`, ... (board 0105: DexJoCo's instance.npz `meta` named the demonstration whose actions
     are the reference solution).
Files the agent's image takes from a files-only image (`COPY --from=<image>` in environment/Dockerfile, the image pinned
by an images/<name>/FILES.json, scripts/files_image.py) are scanned from their one source in the repository, reported as
`files:<name>/<file>`.
Binary files are skipped except numpy archives (`.npz`, a zip of `.npy` members): their string members (`<U`, `S`) and
any text member are read and scanned like a text file (the members' names are reported as `file.npz[member]`); numeric
members are not read past their header. Images and other binaries are skipped.
A legitimate mention (a licence notice that must name its source) is listed in ALLOW with its reason. The egress
allowlist is what stops a download; this check keeps the address out of the task. Board 0072: RoboTangle's
`reference_scene.json` carried `source_url` of the upstream demonstration, and one trial downloaded and replayed it.
That file was in the simulator image, which this check cannot read: an image's own files are reviewed when the image
is built (docs/protocol/leakage.md).

Usage: check-agent-pointers.py [task dirs...]   (default: every task dir, tasks/*/*)
"""
import ast, pathlib, re, sys, zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402  (iter_tasks: the task tree)
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
IDS = re.compile(r"""["']((?:source_|reference_)?(?:demo|demo_id|demo_name|demonstration|demonstration_id|episode|episode_id|
                             episode_name|trajectory_id|recording|recording_id))["']\s*:\s*["']""", re.I | re.X)
FILES = re.compile(r"""(?<![\w.-])(?:[\w.-]+\.(?:hdf5|h5|mcap|parquet|rlds|tfrecord)\b|datasets/[\w.-]+/[\w.-]+)""", re.I)
# (task-name regex, path regex, matched-text regex, reason)
ALLOW = [
    (r"^maniguard-", r"^environment/instance/NOTICE$", r"datasets/IDEAS-Lab-Northwestern/ManiGuard-Bench|github\.com/NU-IDEAS-Lab/ManiGuard",
     "CC BY-NC 4.0 attribution the licence requires, of the scene files' dataset (its demonstrations are other datasets, not named)"),
    (r"^roboengineer-anycar-", r"^(?:environment/public/(?:scripts/control_transfer/components/)?anycarbench/(?:NOTICE|circuits\.json)|files:control-transfer-anycar-files/circuits\.json)$",
     r"^https://github\.com/f1db/f1db/?$",
     "CC BY 4.0 attribution the licence requires, of F1DB's historical circuit outlines (track geometry the instruction "
     "gives the agent, not a controller or a demonstration)"),
]


def files_images() -> dict:
    """{pinned image ref: (name, source dir, files)} of the files-only images (images/<name>/FILES.json)."""
    import json
    out = {}
    for f in sorted((ROOT / "images").glob("*/FILES.json")):
        s = json.loads(f.read_text())
        out[s["image"]] = (f.parent.name, ROOT / s["source"], s["files"])
    return out


FILES_IMAGES = files_images()
COPY_FROM = re.compile(r"^COPY\s+--from=(\S+)\s+/(\S+)\s+\S+\s*$", re.M)


def agent_files(task: pathlib.Path):
    """(path, the name it is reported under) of every file the agent's container gets from the task."""
    f = task / "instruction.md"
    if f.is_file():
        yield f, "instruction.md"
    env = task / "environment"
    for p in sorted(env.rglob("*")) if env.is_dir() else []:
        rel = p.relative_to(env).parts
        if p.is_file() and not p.is_symlink() and rel[0] not in SIDECAR_DIRS and "__pycache__" not in rel:
            yield p, p.relative_to(task).as_posix()
    df = env / "Dockerfile"
    for ref, file in COPY_FROM.findall(df.read_text()) if df.is_file() else []:
        if ref in FILES_IMAGES:   # a file from a files-only image: its one source in the repository
            name, src, files = FILES_IMAGES[ref]
            if file in files:
                yield src / file, f"files:{name}/{file}"


def npy_text(f) -> str | None:
    """The text of one `.npy` member (an open binary stream): a string array's contents, or None for a numeric array
    (only its header is read). Pickled (object) arrays are read as raw bytes: their strings are stored verbatim."""
    head = f.read(10)
    if head[:6] != b"\x93NUMPY":
        rest = f.read(MAX_BYTES)
        raw = head + rest
        return None if b"\0" in raw[:4096] else raw.decode("utf-8", "replace")
    n = int.from_bytes(head[8:10], "little") if head[6] == 1 else int.from_bytes(head[8:10] + f.read(2), "little")
    try:
        descr = str(ast.literal_eval(f.read(n).decode("latin-1")).get("descr", ""))
    except (ValueError, SyntaxError):
        return None
    kind = descr.lstrip("<>|=")[:1]
    if kind == "U":
        return f.read(MAX_BYTES).decode("utf-32-be" if descr.startswith(">") else "utf-32-le", "replace").replace("\0", "")
    if kind in ("S", "O") or descr.startswith("[") or descr.startswith("{"):
        return f.read(MAX_BYTES).decode("utf-8", "replace").replace("\0", " ")
    return None


def texts(p: pathlib.Path, rel: str):
    """(name, text) of each readable text in one agent file: the file itself, or a numpy archive's string members."""
    if p.suffix == ".npz":
        try:
            with zipfile.ZipFile(p) as z:
                for i in z.infolist():
                    if not i.is_dir():
                        with z.open(i) as f:
                            t = npy_text(f)
                        if t:
                            yield f"{rel}[{i.filename}]", t
        except (zipfile.BadZipFile, OSError, EOFError) as exc:
            print(f"WARN {rel}: unreadable numpy archive ({exc!r}), not scanned")
        return
    if p.stat().st_size > MAX_BYTES:
        return
    raw = p.read_bytes()
    if b"\0" not in raw[:4096]:
        yield rel, raw.decode("utf-8", "replace")


def findings(task: pathlib.Path):
    for p, name in agent_files(task):
        for rel, text in texts(p, name):
            text = text.replace("\\/", "/")    # JSON may escape "/"
            for kind, rx in (("URL", HOSTS), ("key", KEYS), ("file", FILES), ("id", IDS)):
                for m in rx.finditer(text):
                    hit = m.group(1) if kind in ("key", "id") else m.group(0)
                    if any(re.search(t, task.name) and re.search(pp, rel) and re.search(h, hit) for t, pp, h, _ in ALLOW):
                        continue
                    yield rel, text.count("\n", 0, m.start()) + 1, kind, hit[:120]


def main(argv):
    tasks = [pathlib.Path(a) for a in argv] or tc.iter_tasks()
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
