"""Run the recap prompt (prompts/recap.md) once per trial with an agent that can read files, run the search command
and write the answer file. The prompt is filled in per trial and kept in prompts_sent/K.md, the agent's reply in
annotate_logs/K.log. Trials that already have recaps/K.json are skipped unless --force.
The agent command is $REVIEW_AGENT (default below: Claude Code, headless, Sonnet, only Read/Write/Bash allowed);
any agent CLI that takes the prompt on stdin works; {data} and {review} in it are replaced by the two directories.
usage: python -m pipeline annotate [--keys K ...] [--jobs 3] [--out recaps] [--force]"""
from __future__ import annotations
import argparse, os, shlex, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from .paths import DATA, REVIEW, PROMPT, keys

AGENT = os.environ.get("REVIEW_AGENT", "claude -p --model sonnet --permission-mode dontAsk --allowedTools Read Write Bash "
                                         "--add-dir {data} --add-dir {review}")


def fill(key: str, out: str) -> str:
    search = f"cd {shlex.quote(REVIEW)} && REVIEW_DATA={shlex.quote(DATA)} {shlex.quote(sys.executable)} -m pipeline search {key}"
    return (open(PROMPT).read().replace("{{KEY}}", key).replace("{{PACKET}}", f"{DATA}/packet/{key}.md")
            .replace("{{SEARCH}}", search).replace("{{OUT}}", f"{DATA}/{out}/{key}.json"))


def run(key: str, out: str) -> str:
    prompt = fill(key, out)
    for d in ("prompts_sent", "annotate_logs", out):
        os.makedirs(f"{DATA}/{d}", exist_ok=True)
    open(f"{DATA}/prompts_sent/{key}.md", "w").write(prompt)
    with open(f"{DATA}/annotate_logs/{key}.log", "w") as log:
        r = subprocess.run(shlex.split(AGENT.format(data=DATA, review=REVIEW)), input=prompt, text=True, stdout=log,
                           stderr=subprocess.STDOUT, cwd=DATA)
    done = os.path.exists(f"{DATA}/{out}/{key}.json")
    return f"{'完成' if done else '没有写出答案'}（退出码 {r.returncode}）  {key}"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipeline annotate")
    ap.add_argument("--keys", nargs="*")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default="recaps")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    todo = [k for k in keys(a.keys) if a.force or not os.path.exists(f"{DATA}/{a.out}/{k}.json")]
    print(f"{len(todo)} 个 trial 要标注；agent：{AGENT}")
    with ThreadPoolExecutor(a.jobs) as pool:
        for line in pool.map(lambda k: run(k, a.out), todo):
            print(line)
