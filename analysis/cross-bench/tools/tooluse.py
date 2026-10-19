#!/usr/bin/env python3
"""Tool calls per harness-independent group, overall and per tenth of the stated time limit: data/tooluse.csv.

usage: tools/tooluse.py            # all valid trials of the main benches (not rsb) with a raw trajectory
       tools/tooluse.py --check    # per-agent mean group shares + 5 random trials with their first 15 classified calls

The four harness formats are read by atif.events (codex, claude_code, antigravity_cli, dsh). This module only adds
the grouping. One CALL = one tool call of the model. Codex `exec` steps run a JavaScript snippet that may call several
tools (Promise.all of exec_command ...); each inner `tools.X(...)` counts as one call, in the step's time.

Groups (one per call; priority order, first match wins when a shell command mixes several):
  run_python  python/python3/ipython/pytest, .py scripts, heredoc or -c snippets that run code (including code that
              drives the robot or simulator through rcb_client / rcb_<bench> Session)
  robot_api   the robot service or simulator client called straight from the shell: curl/wget to a local service,
              the `game` command, `python /opt/tools/<tool>.py <subcommand>` (replay, film, status ...), rcb_client CLI,
              and a short python snippet whose only action is one HTTP call to a local service
  search      grep/rg/find/locate/tree/ls (listing a directory counts as looking for files), glob/list_dir tools
  read        Read/view_file tools, cat/head/tail/sed -n/less/awk/jq on files, python snippets that only print a file
              or source (inspect.getsource, help, .read())
  write       Write/Edit/apply_patch tools, heredoc or redirect into a file, mkdir/cp/mv/rm/touch/chmod/sed -i/tar x
  view_image  image view tools, Read of a png/jpg
  web         web search/fetch tools, curl/wget/requests to an outside host, pip download, git clone, hf download
  plan        todo / plan tools
  other_shell everything else in a shell: pip install, ps, kill, sleep/wait/poll of background jobs, date, bash x.sh ...
  other       a tool this module does not know
Codex write_stdin: empty chars (polling a running process) is other_shell; typed code or commands (a python session the agent
started) is run_python. A web part (curl/git clone/pip download to an outside host) outranks everything but run_python.
Within a compound command, weak parts (cd, echo, date, ls, sleep ...) only count when nothing else is present;
pipeline consumers (head, tail, wc, sort ...) never decide the group.
"""
from __future__ import annotations
import argparse, csv, json, os, random, re, sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import atif
from common import AGENTS, RAW, read_csv, write_csv

GROUPS = [("run_python", "跑 Python"), ("robot_api", "调机器人接口"), ("search", "搜索"), ("read", "读文件或源码"),
          ("write", "写或改文件"), ("view_image", "看图"), ("web", "上网"), ("plan", "计划或待办"),
          ("other_shell", "其他命令"), ("other", "其他")]
G = [g for g, _ in GROUPS]
RANK = {g: i for i, g in enumerate(G)}
NBIN = 10
WEB_RANK = 0.5                                   # a command that reaches an outside host is "web" whatever else it does, except running python
WRITE_BODY = RANK["robot_api"] + 0.5             # a heredoc or redirect that writes a file outranks reading and listing in the same command


# ---------------------------------------------------------------------------------------------------------------
# Codex `exec`: JavaScript calling tools.<name>({...}); pull out each inner call and its main string argument.

def _skip_string(s: str, i: int) -> int:
    q, i = s[i], i + 1
    while i < len(s):
        if s[i] == "\\":
            i += 2
        elif s[i] == q:
            return i + 1
        else:
            i += 1
    return len(s)


def _unescape(lit: str) -> str:
    body, q = lit[1:-1] if len(lit) > 1 and lit[-1] == lit[0] else lit[1:], lit[0]
    if q == '"':
        try:
            return json.loads('"' + body + '"')
        except ValueError:
            pass
    return re.sub(r"\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)", lambda m: {"n": "\n", "t": "\t", "r": "\r"}.get(m.group(1)) or
                  (chr(int(m.group(1)[1:], 16)) if m.group(1)[0] in "ux" and len(m.group(1)) > 1 else m.group(1)), body)


def _close(s: str, i: int) -> int:
    """Index of the ')' matching the '(' just before i."""
    depth = 1
    while i < len(s):
        c = s[i]
        if c in "\"'`":
            i = _skip_string(s, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(s)


JS_CALL = re.compile(r"\b(?:tools|functions)\.(\w+)\s*\(")
JS_HINT = re.compile(r"\bawait\b|\bconst\b|\btext\(|\bimage\(|\blet\b")
JS_ARG = re.compile(r"\b(cmd|command|chars|input|path|patch|query|url)\s*:\s*(?=[\"'`])")


def js_calls(code: str) -> list[tuple[str, str, str]]:
    """[(tool name, main string argument or the raw argument text, raw argument text)] for every tools.X(...) in the snippet."""
    out, pos = [], 0
    while True:
        m = JS_CALL.search(code, pos)
        if not m:
            return out
        end = _close(code, m.end())
        args = code[m.end():end]
        a = JS_ARG.search(args)
        if a:
            j = a.end()
            val = _unescape(args[j:_skip_string(args, j)])
        elif args[:1] in "\"'`" and args:
            val = _unescape(args[:_skip_string(args, 0)])
        else:
            val = args
        out.append((m.group(1), val, args))
        pos = end + 1


# ---------------------------------------------------------------------------------------------------------------
# Shell: tokenizer (quotes, $(...), heredocs, redirects) -> segments -> pipelines -> command words.

HEREDOC = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][\w.-]*)\2")


def split_heredocs(cmd: str) -> tuple[str, dict[str, str]]:
    """Replace each heredoc body by nothing and the `<<TAG` by a marker word; return the bodies by marker."""
    lines, out, bodies, i = cmd.split("\n"), [], {}, 0
    while i < len(lines):
        line = lines[i]
        i += 1
        pend = []
        def mark(m):
            pend.append((m.group(1), m.group(3)))
            return f" __HD{len(bodies) + len(pend) - 1}__ "
        line = HEREDOC.sub(mark, line)
        out.append(line)
        for dash, tag in pend:
            body = []
            while i < len(lines) and (lines[i].strip() if dash else lines[i]) != tag:
                body.append(lines[i])
                i += 1
            i += 1
            bodies[f"__HD{len(bodies)}__"] = "\n".join(body)
    return "\n".join(out), bodies


OPS = ("&&", "||", ";", "|&", "|", "&", "\n")
REDIR = re.compile(r"&>>|&>|>>|>\||>&|>|<<<|<&|<")


def tokenize(s: str) -> list[tuple[str, str]]:
    """[(kind, text)] kind: w word (quotes removed), op separator, r redirect operator."""
    toks, cur, i, n, has = [], [], 0, len(s), False
    def flush():
        nonlocal cur, has
        if has:
            toks.append(("w", "".join(cur)))
        cur, has = [], False
    while i < n:
        c = s[i]
        if c == "\\" and i + 1 < n:
            if s[i + 1] != "\n":
                cur.append(s[i + 1])
                has = True
            i += 2
        elif c == "'":
            j = s.find("'", i + 1)
            j = n if j < 0 else j
            cur.append(s[i + 1:j]); has = True
            i = j + 1
        elif c == '"':
            j = i + 1
            while j < n and s[j] != '"':
                j += 2 if s[j] == "\\" else 1
            cur.append(s[i + 1:j]); has = True
            i = j + 1
        elif c == "`":
            j = s.find("`", i + 1)
            j = n if j < 0 else j
            cur.append(s[i:j + 1]); has = True
            i = j + 1
        elif s.startswith("$(", i):
            j = _close(s, i + 2)
            cur.append(s[i:j + 1]); has = True
            i = j + 1
        elif c in " \t\r":
            flush(); i += 1
        elif c == "#" and not has:
            while i < n and s[i] != "\n":
                i += 1
        elif c in "()":
            flush(); i += 1
        elif c in "<>" or s.startswith("&>", i):
            if has and "".join(cur).isdigit():
                cur, has = [], False                 # fd number in front of the redirect (2>&1)
            flush()
            m = REDIR.match(s, i)
            toks.append(("r", m.group(0)))
            i = m.end()
        elif s.startswith(OPS, i):
            flush()
            op = next(o for o in OPS if s.startswith(o, i))
            toks.append(("op", op)); i += len(op)
        else:
            cur.append(c); has = True; i += 1
    flush()
    return toks


def pipelines(cmd: str) -> list[list[dict]]:
    """Segments (split on && || ; & newline), each a list of stages (split on |): {words, out_redirect, heredoc}."""
    text, bodies = split_heredocs(cmd)
    segs, stages, words, out, hd, target, last_r = [], [], [], None, None, False, ""
    def end_stage():
        nonlocal words, out, hd
        if words or hd:
            stages.append({"words": words, "out": out, "hd": hd})
        words, out, hd = [], None, None
    def end_seg():
        nonlocal stages
        end_stage()
        if stages:
            segs.append(stages)
        stages = []
    for kind, t in tokenize(text):
        if target:
            target = False
            if kind == "w":
                if t.startswith("__HD"):
                    hd = bodies.get(t, "")
                elif t not in ("/dev/null", "-") and not t.isdigit() and last_r.startswith((">", "&>")):
                    out = out or t
                continue
        if kind == "r":
            target, last_r = True, t
            continue
        if kind == "op":
            end_stage() if t in ("|", "|&") else end_seg()
        elif t.startswith("__HD") and t in bodies:
            hd = bodies[t]
        else:
            words.append(t)
    end_seg()
    return segs


# ---------------------------------------------------------------------------------------------------------------
# Classification of one stage / segment / command.

PY = re.compile(r"^(python[\d.]*|ipython[\d]*|pypy3?|pytest|py\.test|jupyter|papermill)$")
ENV = re.compile(r"^[A-Za-z_]\w*=")
WRAP = {"sudo", "time", "nohup", "nice", "stdbuf", "setsid", "exec", "env", "command", "builtin", "unbuffer", "xvfb-run",
        "taskset", "ionice", "chrt", "timeout", "xargs", "script", "watch"}
VALUE_FLAGS = {"env": ("-u", "-C", "-S"), "timeout": ("-s", "-k"), "nice": ("-n",), "taskset": ("-c",), "ionice": ("-c", "-n"), "sudo": ("-u", "-g"),
               "xvfb-run": ("-s", "-n", "-e"), "watch": ("-n",)}
SEARCH = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "find", "locate", "fd", "fdfind", "tree", "zgrep", "glob"}
READ = {"cat", "head", "tail", "less", "more", "nl", "bat", "batcat", "wc", "file", "stat", "xxd", "od", "strings", "hexdump", "diff",
        "cmp", "md5sum", "sha256sum", "sha1sum", "zcat", "zless", "awk", "gawk", "jq", "column", "tac", "readlink", "realpath",
        "basename", "dirname", "cut", "sort", "uniq", "tr", "fold", "paste", "rev", "comm", "join", "pdftotext", "identify", "exiftool"}
WRITE = {"tee", "cp", "mv", "mkdir", "rm", "rmdir", "touch", "ln", "chmod", "chown", "install", "rsync", "patch", "dd", "truncate",
         "unzip", "tar", "gunzip", "gzip", "zip", "unlink", "shred", "mktemp", "cp2"}
WEB_CMD = {"git-clone", "gdown", "aria2c", "huggingface-cli", "hf", "youtube-dl", "yt-dlp", "scp", "sftp", "ssh"}
WEAK = {"cd", "echo", "printf", "date", "pwd", "true", "false", "export", "set", "unset", "source", ".", "sleep", "test", "[", "[[",
        "ls", "dir", "exit", "return", "wait", "alias", "umask", "ulimit", "hostname", "whoami", "id", "uname", "type", "which",
        "local", "declare", "read", "mapfile", ":", "pushd", "popd", "history", "clear", "trap", "then", "do", "done", "fi", "else", "if", "for", "while"}
CONSUMER = {"head", "tail", "wc", "sort", "uniq", "cut", "tr", "awk", "gawk", "sed", "tee", "column", "jq", "less", "more", "nl", "cat",
            "xargs", "fold", "paste", "tac", "rev", "nl", "cut", "tr", "bat", "diff", "comm"}
PROC_LIST = {"ps", "pgrep", "pkill", "nvidia-smi", "env", "printenv", "lsof", "ss", "netstat", "df", "du", "mount", "dpkg", "apt", "apt-get",
             "history", "journalctl", "docker", "pip", "pip3", "uv", "conda", "top", "free", "lscpu", "nproc", "ls", "dmesg", "systemctl", "uname"}
LOCAL = re.compile(r"^(localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|\[::1?\]|::1|host\.docker\.internal|sim|simulator|robot|server|verifier|[\w-]+)$")
URL = re.compile(r"(?:https?|ftp)://\[?([^/\s:\]'\"]+)", re.I)
LOCAL_URL = re.compile(r"(?:localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|host\.docker\.internal|\[::1\]):\d+|\$\{?\w*(?:URL|HOST|ENDPOINT|PORT|SIM)\w*\}?|//sim\b|//simulator\b", re.I)
RUN_IN_PY = re.compile(r"Session\(|Robot\(|\.step\(|\.reset\(|\.submit\(|\.observe\(|\.get_obs\(|MjModel|mj_step|mj_forward|mujoco\.|np\.save|savez|"
                       r"\.save\(|write_text|write_bytes|\.write\(|open\([^)]*['\"][wa]b?['\"]|subprocess|os\.system|time\.sleep|torch|\bwhile\b|gym\.make|gymnasium|\.render\(|\bdef \b|\bfor\b|import rcb_\w+;\s*\w+\s*=")
READ_PY = re.compile(r"getsource|getsourcelines|getsourcefile|inspect\.getdoc|\bhelp\(|__doc__|__file__|\.read\(\)|read_text\(|readlines\(|"
                     r"print\(open\(|\.readlines")
LIST_PY = re.compile(r"os\.listdir|glob\.glob|os\.walk|\.glob\(|\.rglob\(|iterdir\(")
HTTP_PY = re.compile(r"urlopen|requests\.(get|post|put)|http\.client|httpx\.|urllib\.request")
NETCMD = {"curl", "wget", "http", "https", "httpie", "nc", "ncat", "telnet"}
PIP_WEB = re.compile(r"^(download|wheel)$")


def py_group(code: str, hd: bool = False) -> str:
    """Group for a python snippet (-c string, heredoc body or stdin)."""
    code = code.strip()
    if HTTP_PY.search(code) and len(code) < 600 and not RUN_IN_PY.search(code):
        urls = URL.findall(code)
        if urls and not all(LOCAL.match(u) and "." not in u or u.startswith(("127.", "0.0.0.0")) for u in urls):
            return "web"
        return "robot_api"
    if len(code) < 700 and READ_PY.search(code) and not RUN_IN_PY.search(code):
        return "read"
    if len(code) < 300 and LIST_PY.search(code) and not RUN_IN_PY.search(code) and not re.search(r"load|open\(|read", code):
        return "search"
    return "run_python"


KEYWORD = {"do", "then", "else", "elif", "if", "while", "until", "!", "{", "}", "function"}


def strip_wrappers(words: list[str]) -> list[str]:
    """Drop leading keywords, VAR=value, and wrapper commands (sudo, env, timeout 60, nohup, taskset -c 0-7 ...)."""
    while words and words[0] in KEYWORD:
        words = words[1:]
    while words:
        w = os.path.basename(words[0]) if "/" in words[0] and not words[0].startswith("-") else words[0]
        if ENV.match(words[0]):
            words = words[1:]
        elif w in WRAP:
            words = words[1:]
            while words and (words[0].startswith("-") or ENV.match(words[0])):
                flag = words[0]
                words = words[1:]
                if flag in VALUE_FLAGS.get(w, ()) and words:
                    words = words[1:]
            if w in ("timeout", "taskset", "watch") and words and re.match(r"^[\d.,-]+[smhd]?$|^0x\w+$", words[0]):
                words = words[1:]
        else:
            break
    return words


GREPS = {"grep", "egrep", "fgrep", "rg", "ag", "zgrep"}


def greps_files(words: list[str]) -> bool:
    """True when a grep/rg stage names a pattern and a path (it searches files); a lone pattern only filters a pipe."""
    args, skip, n = words[1:], False, 0
    for a in args:
        if skip:
            skip = False
        elif a in ("-A", "-B", "-C", "-m", "-e", "-f", "-g", "-t", "--include", "--exclude", "-d"):
            skip = True
        elif not a.startswith("-"):
            n += 1
    return n >= 2


def stage_group(st: dict, first: bool = True) -> tuple[str, str]:
    """(group, command word) of one pipeline stage."""
    words = strip_wrappers(st["words"])
    if not words:
        return ("other_shell", "") if not st["hd"] else ("other_shell", "heredoc")
    w0 = words[0]
    w = os.path.basename(w0).lower() if "/" in w0 else w0.lower()
    args = words[1:]
    hd, out = st["hd"], st["out"]
    if w in ("bash", "sh", "zsh", "dash", "source", ".") and (hd is not None or "-c" in args or "-lc" in args or "-ic" in args):
        body = hd if hd is not None else next((a for a, b in zip(args[1:], args) if b in ("-c", "-lc", "-ic")), "")
        g, c = classify_cmd(body or "")
        return g, c or w
    if PY.match(w) or w.endswith(".py") or w0.endswith(".py"):
        if w == "pytest" or w == "py.test":
            return "run_python", w
        if PY.match(w) and args[:2] and args[0] == "-m":
            mod = args[1].split(".")[0]
            if mod == "pip":
                return stage_group({"words": ["pip"] + args[2:], "out": out, "hd": hd})
            if mod in ("venv", "virtualenv", "ensurepip", "http", "site", "sysconfig"):
                return "other_shell", f"{w} -m {mod}"
        script = next((a for a in args if a.endswith(".py")), w0 if w0.endswith(".py") else "")
        if PY.match(w) and script.startswith("/opt/tools/") and "-c" not in args:
            rest = args[args.index(script) + 1:]
            if hd is None and (not rest or re.match(r"^[a-z][\w-]*$", rest[0])):
                return "robot_api", f"{w} {os.path.basename(script)} {rest[0] if rest else ''}".strip()
        if w == "rcb_client.py" or os.path.basename(script) == "rcb_client.py":
            return "robot_api", "rcb_client.py"
        if PY.match(w) and "-c" in args:
            i = args.index("-c")
            return py_group(args[i + 1] if i + 1 < len(args) else ""), f"{w} -c"
        if hd is not None and PY.match(w) and not script:
            return py_group(hd, True), f"{w} <<heredoc"
        return "run_python", w
    if w == "uv" and args[:1] == ["run"]:
        return stage_group({"words": args[1:], "out": out, "hd": hd})
    if w == "uv" and args[:1] == ["pip"]:
        return stage_group({"words": ["pip"] + args[1:], "out": out, "hd": hd})
    if w in ("pip", "pip3"):
        sub = next((a for a in args if not a.startswith("-")), "")
        return ("web" if PIP_WEB.match(sub) else "other_shell"), f"pip {sub}"
    if w in ("rcb_client", "rcb-client", "game", "robot", "rcb"):
        return "robot_api", w
    if w in NETCMD:
        urls = URL.findall(" ".join(args))
        ext = [u for u in urls if not (LOCAL.match(u) and "." not in u) and not u.startswith(("127.", "0.0.0.0", "localhost", "10.", "192.168."))]
        if ext and not LOCAL_URL.search(" ".join(args)):
            return "web", w
        return "robot_api", w
    if w == "git":
        sub = next((a for a in args if not a.startswith("-")), "")
        if sub in ("clone", "pull", "fetch", "submodule", "ls-remote"):
            return "web", f"git {sub}"
        if sub in ("grep",):
            return "search", "git grep"
        if sub in ("apply", "checkout", "restore", "reset", "stash", "add", "commit", "mv", "rm", "init"):
            return "write", f"git {sub}"
        return "read", f"git {sub}"
    if w in ("apt", "apt-get", "conda", "mamba", "npm", "yarn", "cargo", "go", "make", "cmake", "gcc", "g++", "nvcc"):
        return "other_shell", w
    if w in WEB_CMD:
        return "web", w
    if w == "ls":
        return ("search" if any(re.match(r"^-\w*R", a) or a == "--recursive" for a in args) else "search"), "ls"
    if w == "sed":
        if any(a == "-i" or a.startswith("-i") or a.startswith("--in-place") for a in args if a.startswith("-")):
            return "write", "sed -i"
        return "read", "sed"
    if w in ("echo", "printf", "cat", "tee", "true", ":", "date", "dd") and out:
        return "write", f"{w} >"
    if w == "cat" and hd is not None and not out:
        return "other_shell", "cat <<"
    if w in ("tar",) and not any(re.match(r"^-?\w*x", a) for a in args[:1]):
        return "read", "tar t"
    if w == "unzip" and "-l" in args:
        return "read", "unzip -l"
    if w == "echo" or w == "printf":
        return "other_shell", w
    if w in SEARCH:
        return "search", w
    if w in READ:
        return "read", w
    if w in WRITE:
        return "write", w
    if w in ("sleep",):
        return "other_shell", "sleep"
    if any(a.endswith(".py") for a in args) and re.match(r"^[\w./-]+$", w):      # an agent-made wrapper: run.sh job.py
        return "run_python", w
    return "other_shell", w


def classify_cmd(cmd: str, depth: int = 0) -> tuple[str, str]:
    """(group, short label) of a whole shell command string."""
    cmd = cmd.strip()
    if not cmd:
        return "other_shell", ""
    try:
        segs = pipelines(cmd)
    except (ValueError, StopIteration, IndexError):
        segs = []
    if not segs:
        w = cmd.split()[0] if cmd.split() else ""
        return ("run_python" if PY.match(w) else "other_shell"), w
    cands = []                                   # (rank, weak, group, label)
    for stages in segs:
        gs = [stage_group(s) for s in stages]
        words0 = strip_wrappers(stages[0]["words"])
        w0 = os.path.basename(words0[0]).lower() if words0 else ""
        if w0 in PROC_LIST:
            g, c = gs[0]
            cands.append((RANK[g], w0 in WEAK, g, c))
            continue
        pick = []
        for i, (s, (g, c)) in enumerate(zip(stages, gs)):
            sw = strip_wrappers(s["words"])
            sc = os.path.basename(sw[0]).lower() if sw else ""
            if i and (sc in CONSUMER or (sc in GREPS and not greps_files(sw))):
                continue
            if i and PY.match(sc) and gs[0][0] in ("robot_api", "web", "read", "search", "other_shell") and gs[0][1] in NETCMD | {"cat", "echo", "printf", "head", "tail", "game"}:
                continue
            pick.append((WRITE_BODY if g == "write" and (s["out"] or s["hd"] is not None) else WEB_RANK if g == "web" else RANK[g], sc in WEAK, g, c))
        if not pick:
            pick = [(RANK[gs[0][0]], False, gs[0][0], gs[0][1])]
        cands.append(min(pick, key=lambda x: (x[1], x[0])))
    strong = [c for c in cands if not c[1]]
    best = min(strong or cands, key=lambda x: x[0])
    return best[2], best[3]


# ---------------------------------------------------------------------------------------------------------------
# Calls of one trial.

WEB_TOOL = {"search_web", "web_search", "websearch", "webfetch", "web_fetch", "read_url_content", "browse", "google_search", "fetch", "web_search_call"}
PLAN_TOOL = {"todowrite", "update_plan", "task_boundary", "exitplanmode", "enterplanmode", "todo_write", "todoread"}
BG_TOOL = {"sleep", "wait", "job_output", "job_kill", "job_list", "taskstop", "bashoutput", "killshell", "manage_task", "schedule",
           "send_command_input", "write_stdin", "clock__curr_time", "taskoutput", "monitor"}
SHELL_TOOL = {"bash", "run_command", "shell", "local_shell", "terminal", "exec_command"}
SEARCH_TOOL = {"glob", "grep", "find_by_name", "grep_search", "list_dir", "ls", "codebase_search"}
READ_TOOL = {"read", "view_file", "view_file_outline", "notebookread", "read_file", "view_code_item"}
WRITE_TOOL = {"write", "edit", "multiedit", "write_to_file", "replace_file_content", "multi_replace_file_content", "apply_patch",
              "create_file", "notebookedit", "str_replace_based_edit_tool", "str_replace_editor", "edit_file"}


def shell_text(text: str) -> str:
    """The command of a shell call whose arguments were not a plain string (atif keeps the JSON then)."""
    if not text.lstrip().startswith("{"):
        return text
    try:
        d = json.loads(text)
    except ValueError:
        m = re.search(r'"(?:command|CommandLine|cmd)"\s*:\s*"((?:[^"\\]|\\.)*)', text)
        return _unescape('"' + m.group(1) + '"') if m else text
    if isinstance(d.get("__UnparsedToolInput"), dict):
        return shell_text(d["__UnparsedToolInput"].get("raw") or "")
    return next((d[k] for k in ("command", "CommandLine", "cmd", "input") if isinstance(d.get(k), str) and d[k]), "")


def tool_group(name: str, text: str, kind: str) -> tuple[str, str]:
    """(group, command word or tool name) of one call."""
    n = name.strip().lower()
    if n in SHELL_TOOL:
        if re.match(r"^\{\s*cmd\b\s*[,:}]", text.strip()) and "\n" not in text.strip()[:2]:
            return "other", "exec_command(var)"                   # JS built the command at run time; the text is not readable
        return classify_cmd(shell_text(text))
    if n in WRITE_TOOL or kind == "write":
        return "write", n
    if kind == "image" or n in ("view_image", "read_image"):
        return "view_image", n
    if n in WEB_TOOL:
        return "web", n
    if n in PLAN_TOOL:
        return "plan", n
    if n in BG_TOOL:
        return "other_shell", n
    if n in SEARCH_TOOL:
        return "search", n
    if n in READ_TOOL:
        return "read", n
    if n.startswith("mcp__") or n.startswith("clock__"):
        return "other", n
    return "other", n[:40]


def trial_calls(ev: list[dict]) -> list[tuple[float | None, str, str, str]]:
    """[(t minutes, group, command word, call text)] for every tool call; Codex `exec` snippets are expanded into their inner calls."""
    out = []
    for e in ev:
        if e["kind"] in ("message", "thought"):
            continue
        if e["name"].lower() == "exec":
            inner = js_calls(e["text"])
            if not inner and not JS_HINT.search(e["text"]):
                g, c = tool_group("exec_command", e["text"], "")      # a plain command given to `exec`
                out.append((e["t"], g, c, "exec: " + e["text"]))
            elif not inner:
                out.append((e["t"], "other", "exec(js)", e["text"]))
            for name, val, args in inner:
                n = name.lower()
                k = "image" if n == "view_image" else "write" if n == "apply_patch" else ""
                if n == "write_stdin":                   # typing into a running process: polling the output, or feeding it code / commands
                    typed = re.search(r"\bchars\s*:", args) and re.sub(r"[\x03\x04\s]", "", val) != ""
                    g, c = ("run_python", "write_stdin(typed)") if typed else ("other_shell", "write_stdin")
                    out.append((e["t"], g, c, f"{name}: {val if typed else '(poll)'}"))
                    continue
                g, c = tool_group("exec_command" if n == "exec_command" else name, val, k)
                out.append((e["t"], g, c, f"{name}: {val}"))
        else:
            g, c = tool_group(e["name"], e["text"], e["kind"])
            out.append((e["t"], g, c, f'{e["name"]}: {e["text"]}'))
    return out


def bins(calls: list[tuple], cutoff: float) -> list[int | None]:
    """Tenth of the stated limit for each call; a call without a time takes the previous call's tenth."""
    res, last = [], 0
    for t, *_ in calls:
        if t is not None and cutoff > 0:
            last = max(0, min(NBIN - 1, int(NBIN * t / cutoff)))
        res.append(last)
    return res


def cutoff_of(key: str, feats: dict, row: dict) -> float:
    from queries import stated_cutoff
    c = feats.get("budget_min") or stated_cutoff(key) or row.get("timeout_min") or 0
    return float(c)


def one(args: tuple) -> dict | None:
    row, feats = args
    key = row["key"]
    try:
        traj = json.load(open(os.path.join(RAW, key, "agent/trajectory.json")))
        meta = json.load(open(os.path.join(RAW, key, "trial.json")))
        ev, _ = atif.events(traj, atif.request_times(meta["detail"]))
    except (OSError, ValueError, KeyError):
        return None
    calls = trial_calls(ev)
    cut = cutoff_of(key, feats, row)
    out = {"key": key, "agent": row["agent"], "bench": row["bench"], "mode": row["mode"], "success": row["success"], "n_calls": len(calls),
           "cutoff_min": cut}
    for g in G:
        out[g] = 0
        for b in range(NBIN):
            out[f"{g}_b{b}"] = 0
    for (t, g, _, _), b in zip(calls, bins(calls, cut)):
        out[g] += 1
        out[f"{g}_b{b}"] += 1
    return out


def valid_rows() -> list[dict]:
    return [r for r in read_csv("trials.csv") if r["validity"] == "valid" and r["bench"] != "rsb"]


def build() -> int:
    feats = {f["key"]: f for f in read_csv("features.csv")}
    rows = valid_rows()
    with ProcessPoolExecutor(int(os.environ.get("XB_JOBS", "12"))) as ex:
        res = list(ex.map(one, [(r, feats.get(r["key"], {})) for r in rows], chunksize=16))
    done = [r for r in res if r]
    write_csv("tooluse.csv", done)
    print(f"{len(done)} rows written, {len(rows) - len(done)} valid trials without a parsable log")
    return 0


def check() -> int:
    rows = read_csv("tooluse.csv")
    by = defaultdict(list)
    for r in rows:
        if int(r["n_calls"]):
            by[r["agent"]].append(r)
    print("mean share of calls per group (each trial weighs the same)")
    print(f'{"agent":22s} {"n":>5s} {"calls":>6s} ' + " ".join(f"{g:>11s}" for g in G))
    for ag, rs in sorted(by.items()):
        sh = {g: sum(int(r[g]) / int(r["n_calls"]) for r in rs) / len(rs) for g in G}
        print(f'{ag:22s} {len(rs):5d} {sum(int(r["n_calls"]) for r in rs) / len(rs):6.0f} ' + " ".join(f"{100 * sh[g]:10.1f}%" for g in G))
    feats = {f["key"]: f for f in read_csv("features.csv")}
    random.seed(int(os.environ.get("SEED", "0")))
    for r in random.sample(rows, min(5, len(rows))):
        traj = json.load(open(os.path.join(RAW, r["key"], "agent/trajectory.json")))
        meta = json.load(open(os.path.join(RAW, r["key"], "trial.json")))
        ev, _ = atif.events(traj, atif.request_times(meta["detail"]))
        calls = trial_calls(ev)
        print(f'\n== {r["key"]}  ({r["agent"]}, {r["bench"]}, {r["mode"]}, {r["n_calls"]} calls, limit {r["cutoff_min"]} min)')
        for t, g, c, raw in calls[:15]:
            print(f'  {"--" if t is None else format(t, "5.1f")}  {g:11s} {" ".join(raw.split())[:100]}')
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    sys.exit(check() if ap.parse_args().check else build())
