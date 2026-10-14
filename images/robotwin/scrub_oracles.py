"""Remove RoboTwin's built-in reference solutions from the image so agents cannot look them up.

Every task class in envs/<task>.py ships an expert `play_once` (plus helpers such as `pick_and_place_block`).
Keep only the scene definition and the success predicate: `setup_demo`, `load_actors`, `check_success` and
whatever those call; every other method body becomes `raise NotImplementedError("scrubbed")`.

The kept methods also compute data that only the expert reads: `load_actors` of 18 tasks sets reference poses
(where to hold, hand over or put an object; `dump_bin_bigbin.pour_actions` is the whole pouring motion as a
ready-made Action list). Those attributes (LEAKS) are removed from the kept methods too, statement and all, with the
local values and comments that only feed them, so neither the env object nor the source shows them. A removed
statement that draws from numpy's random stream is replaced by the same number of bare draws, so the scene that
`load_actors` builds (the frozen instance and its hash) is unchanged. None of them is read by `check_success`.
The oracles (solution/, never in the image) restore them by rebuilding the scene with upstream's `load_actors`.

Also deletes code_gen/ (LLM prompts with worked task solutions), description/, XPolicyLab/.
Fails loudly if a `play_once` body or a LEAKS attribute survives, or if a kept method sets a pose-like attribute
(name with "pose", "pos" or "action") that no kept method reads and that is neither in LEAKS nor in NOT_LEAKS.

    python scrub_oracles.py [root]      # default /opt/RoboTwin (the image build)
Importable (scripts/robotwin_mk_task.py uses LEAKS): the scrub runs only as a script."""
import ast, pathlib, re, shutil, sys

KEEP = {"setup_demo", "load_actors", "check_success", "__init__"}
# Attributes the kept methods set that only the scrubbed expert reads (AST scan of the 50 upstream task files,
# board 0100). Poses the expert moves to or places at, and the pouring action list.
LEAKS = {
    "adjust_bottle": ["left_target_pose", "right_target_pose"],
    "blocks_ranking_rgb": ["block1_target_pose", "block2_target_pose", "block3_target_pose"],
    "blocks_ranking_size": ["block1_target_pose", "block2_target_pose", "block3_target_pose"],
    "dump_bin_bigbin": ["middle_pose", "pour_actions"],
    "handover_block": ["block_middle_pose"],
    "handover_mic": ["handover_middle_pose"],
    "hanging_mug": ["middle_pos"],
    "move_can_pot": ["target_pose"],
    "move_stapler_pad": ["pad_pose"],              # the pad's position + the expert's placing orientation
    "place_dual_shoes": ["right_shoe_middle_pose"],  # unread upstream (dead code), still a waypoint
    "place_mouse_pad": ["target_pose"],            # the pad's position + the expert's placing orientation
    "put_bottles_dustbin": ["right_middle_pose"],
    "rotate_qrcode": ["target_pose"],
    "scan_object": ["left_object_target_pose", "right_object_target_pose"],
    "stack_blocks_three": ["block1_target_pose"],  # unread upstream (dead code), still a placement pose
    "stack_blocks_two": ["block1_target_pose"],    # unread upstream (dead code), still a placement pose
    "stack_bowls_three": ["bowl1_target_pose", "quat_of_target_pose"],
    "stack_bowls_two": ["bowl1_target_pose", "quat_of_target_pose"],
}
# Pose-like attributes of kept methods that stay: an object's own initial pose, nothing more (unread upstream).
NOT_LEAKS = {
    "move_playingcard_away": {"target_pose": "= self.playingcards.get_pose(), the cards' initial pose"},
    "stamp_seal": {"target_pose": "= self.target.get_pose(), the target pad's initial pose"},
    "pick_diverse_bottles": {"actor_pose": "a flag check_success sets"},
    "pick_dual_bottles": {"actor_pose": "a flag check_success sets"},
}
POSE_LIKE = re.compile(r"pose|pos$|pos_|action")
RNG_ONE_DOUBLE = {"rand", "random", "random_sample", "uniform"}  # scalar calls: exactly one double from the stream


def self_attrs(fn: ast.AST) -> set[str]:
    return {n.attr for n in ast.walk(fn)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self"}


def kept_methods(cls: ast.ClassDef) -> tuple[dict, set]:
    fns = {f.name: f for f in cls.body if isinstance(f, ast.FunctionDef)}
    keep, todo = set(), list(KEEP)
    while todo:  # transitive closure of self.<method> references from the kept methods
        k = todo.pop()
        if k in keep or k not in fns:
            continue
        keep.add(k); todo.extend(self_attrs(fns[k]))
    return fns, keep


def _stores(stmt: ast.AST) -> set[str]:
    return {n.attr for n in ast.walk(stmt) if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
            and isinstance(n.value, ast.Name) and n.value.id == "self"}


def _name_target(stmt: ast.AST) -> str | None:
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
        return stmt.targets[0].id
    return None


def _reads(stmt: ast.AST, name: str) -> bool:
    return any(isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Load) for n in ast.walk(stmt))


def _rng_draws(stmt: ast.AST, where: str) -> int:
    k = 0
    for n in ast.walk(stmt):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Attribute)
                and n.func.value.attr == "random" and isinstance(n.func.value.value, ast.Name) and n.func.value.value.id == "np"):
            if n.func.attr not in RNG_ONE_DOUBLE or any(kw.arg == "size" for kw in n.keywords) or \
                    (n.func.attr in ("rand", "random", "random_sample") and n.args):
                raise SystemExit(f"{where}: cannot keep the random stream of {ast.unparse(n)}")
            k += 1
        elif isinstance(n, ast.Call) and "rand" in ast.unparse(n.func) and not ast.unparse(n.func).startswith("np.random"):
            raise SystemExit(f"{where}: unexpected random call {ast.unparse(n)} in a removed statement")
    return k


def leak_edits(task: str, cls: ast.ClassDef, lines: list[str]) -> list[tuple[int, int, str]]:
    """(start, end, replacement) line edits that remove LEAKS[task] from the kept methods."""
    leaks = set(LEAKS.get(task, ()))
    fns, keep = kept_methods(cls)
    edits = []
    for name in sorted(keep):
        body = fns[name].body
        drop = {i for i, s in enumerate(body) if _stores(s) & leaks}
        nested = [n for i, s in enumerate(body) if i not in drop for n in ast.walk(s)
                  if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self" and n.attr in leaks]
        if nested:
            raise SystemExit(f"{task}.{name}: a LEAKS attribute is used outside a top-level statement that sets it "
                             f"(line {nested[0].lineno}); extend scrub_oracles.py")
        changed = True
        while changed:  # local values that only feed removed statements go too
            changed = False
            for i, s in enumerate(body):
                v = _name_target(s)
                if i in drop or v is None:
                    continue
                users = []
                for j in range(i + 1, len(body)):
                    if _reads(body[j], v):
                        users.append(j)
                    if _name_target(body[j]) == v:
                        break
                if users and all(j in drop for j in users) and drop >= set(users):
                    drop.add(i); changed = True
        for i in sorted(drop):
            s = body[i]
            start = s.lineno - 1
            while start > 0 and lines[start - 1].strip().startswith("#"):  # its comment goes with it
                start -= 1
            indent = re.match(r"\s*", lines[s.lineno - 1]).group(0)
            k = _rng_draws(s, f"{task}.{name}:{s.lineno}")
            rep = "".join(f"{indent}np.random.random()  # a draw of a removed reference-solution value: same random stream\n"
                          for _ in range(k))
            edits.append((start, s.end_lineno, rep))
    return edits


def check_leaks(task: str, src: str) -> list[str]:
    """Problems left in a scrubbed (or upstream, before scrubbing: all LEAKS are reported) task file."""
    out = []
    cls = [n for n in ast.parse(src).body if isinstance(n, ast.ClassDef)][0]
    fns, keep = kept_methods(cls)
    leaks, fine = set(LEAKS.get(task, ())), NOT_LEAKS.get(task, {})
    for name in keep:
        stored = _stores(fns[name])
        for a in sorted(stored & leaks):
            out.append(f"{task}.{name} still sets self.{a}")
        read_elsewhere = set().union(*[self_attrs(fns[m]) - _stores(fns[m]) for m in keep if m != name] or [set()])
        for a in sorted(stored - leaks - set(fine) - read_elsewhere):
            if POSE_LIKE.search(a) and not any(a in self_attrs(fns[m]) - _stores(fns[m]) for m in keep):
                out.append(f"{task}.{name} sets self.{a}, which no kept method reads: add it to LEAKS or NOT_LEAKS")
    return out


def scrub_source(task: str, src: str) -> tuple[str, list[str]]:
    tree = ast.parse(src); lines = src.splitlines(keepends=True)
    edits, scrubbed = [], []
    for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
        fns, keep = kept_methods(cls)
        for name, f in fns.items():
            if name in keep:
                continue
            body_start = f.body[0].lineno - 1  # first statement (docstring included) -> replaced
            while body_start > f.lineno and lines[body_start - 1].strip().startswith("#"):
                body_start -= 1  # and the comments above it (they describe the expert's steps)
            indent = re.match(r"\s*", lines[body_start]).group(0)
            edits.append((body_start, f.end_lineno, f'{indent}raise NotImplementedError("scrubbed: reference solution removed")\n'))
            scrubbed.append(f"{task}.py:{name}")
        if cls.name == task:
            edits += leak_edits(task, cls, lines)
    for s, e, rep in sorted(edits, reverse=True):
        lines[s:e] = [rep] if rep else []
    return "".join(lines), scrubbed


def main(root: pathlib.Path) -> int:
    scrubbed, files, problems = [], 0, []
    for p in sorted((root / "envs").glob("*.py")):
        if p.name.startswith("_"):
            continue
        new, sc = scrub_source(p.stem, p.read_text())
        if sc or new != p.read_text():
            p.write_text(new); files += 1
        scrubbed += sc
    missing = sorted(set(LEAKS) - {p.stem for p in (root / "envs").glob("*.py")})
    if missing:
        problems.append(f"LEAKS names tasks that do not exist: {missing}")
    for d in ["code_gen", "description", "XPolicyLab", "assets/files", "policy"]:  # data/ = image codec, imported by envs
        shutil.rmtree(root / d, ignore_errors=True)
    for p in (root / "envs").glob("*.py"):
        if p.name.startswith("_"):
            continue
        src = p.read_text()
        for cls in [n for n in ast.parse(src).body if isinstance(n, ast.ClassDef)]:
            for f in cls.body:
                if isinstance(f, ast.FunctionDef) and f.name == "play_once" and not (
                        len(f.body) == 1 and isinstance(f.body[0], ast.Raise)):
                    problems.append(f"{p.name}:play_once survives")
        problems += check_leaks(p.stem, src)
        problems += [f"{p.name}: self.{a} still appears" for a in LEAKS.get(p.stem, ()) if re.search(rf"\bself\.{a}\b", src)]
    print(f"scrubbed {len(scrubbed)} methods in {files} files: {scrubbed}\n"
          f"reference values removed: {sum(map(len, LEAKS.values()))} attributes in {len(LEAKS)} tasks\nproblems: {problems}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/RoboTwin")))
