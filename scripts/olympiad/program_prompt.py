"""The program-play prompt: one fixed structure for every real-time sport (2026-10-02).

Principles: clear, simple, general. Only what a player needs; no history, no implementation detail.
Sections, in this order:
  1. Task                  sport-specific  who you control, the opponent, how to win (including any shot/time limit)
  2. Time                  general         the slowed real-time world, when it freezes, the session limit
  3. Write a program       general         program play, staying in the loop, rules, the container
  4. Interface             general format  commands and HTTP endpoints; then the sport's observation and action
  5. Rules                 sport-specific  how points are won and lost; the opponent in a sentence or two
  6. Geometry and physics  sport-specific  coordinates, sizes, reach and the physics needed to play
A sport supplies the sport-specific texts; `single()` and `duel()` assemble the prompt.
"""

TIME = """## Time
The world runs on its own in real time, slowed by a factor S (`timing.slowdown` in `game spec`; S = 1 is real speed):
one second of game time takes S seconds of real time. It does not wait for you: your thinking, tool calls, the model
API and your program's computation all take real time while the game goes on. All times below are game seconds.

The world is frozen only before `game start` and after each {unit} until you send `game ready "WHY" "PLAN"` (a short
review: why the {unit} ended and what you will change). {goal}
Frozen time does not advance the game, but it counts toward your session limit of {session} of real time, preparation
included.{duel_time} The {contest} is graded when your session ends: stay until it is over."""

DUEL_TIME = """ After one player runs `game start`, the other has {start} to start.
**After each {unit}, send `game ready` within {review} of real time or you forfeit the {contest}**; do not sleep through a
review."""

PROGRAM = """## Write a program
You may write a player program that observes, finds and tracks the {object}, predicts its flight and sends commands on
its own, without a new model response for each command. You may also act yourself. Prepare and test it before
`game start`, run it in the background, watch its log, and stop, fix and restart it whenever needed, also during a
{unit}. Use the reviews to improve it. Only you send `game start` and `game ready`; actions are refused while the world
is frozen.

- Use only the camera images, the service's replies and this document; no simulator internals or hidden state.
- One action at a time: an action sent before the previous one has returned is refused (HTTP 429).
- Your container: Python 3.12 with numpy, SciPy, Pillow and OpenCV (headless); {cpus} CPUs, {memory}; no internet during
  the {contest}. Keep your scripts, logs and notes in `/app/output/`."""

INTERFACE_HEAD = """## Interface
Use the `game` command, or, from a program, the same calls as HTTP with JSON at `{url}` (faster than starting a process):

| `game` command | HTTP | |
| --- | --- | --- |
{rows}

{replies} If a {unit} ends before an action takes effect, the action is dropped."""

REPLIES_SINGLE = """Every reply includes the current state (score, game time, whether the world is running, your robot and command) and
the result of any shot or {unit} since your previous call."""
REPLIES_DUEL = """Every reply includes the current state (score, game time, whether the world is running, your robot and command)."""


GOAL = """Your goal is to win points, not only to return the {object}:
watch how points are won and lost (your own errors and how your opponent plays) and adapt your program and strategy."""


def _words(obj, unit, contest, goal):
    """The sport's nouns: unit (what each review follows: point, pitch, ...), contest (match, game, ...), goal sentence."""
    return dict(object=obj, unit=unit, contest=contest, goal=(goal or GOAL).format(object=obj))


def _rows(cmds):
    return "\n".join(f"| `{c}` | `{h}` | {w} |" for c, h, w in cmds)


def single(*, title, task, obj, url, commands, observation, action, rules, physics, session="2 hours", cpus=4, memory="8 GB",
           unit="point", contest="match", goal=None):
    """Single-player prompt. commands: [(game command, HTTP call, what it does)]. unit / contest / goal: the sport's
    nouns (defaults for rally sports; baseball: unit="pitch", contest="game", its own goal sentence)."""
    w = _words(obj, unit, contest, goal)
    return "\n\n".join([
        f"# {title}", task,
        TIME.format(session=session, duel_time="", **w),
        PROGRAM.format(cpus=cpus, memory=memory, **w),
        INTERFACE_HEAD.format(url=url, rows=_rows(commands), replies=REPLIES_SINGLE.format(**w), **w), observation,
        action, "## Rules\n" + rules, "## Geometry and physics\n" + physics]) + "\n"


def duel(*, title, task, obj, url, commands, observation, action, rules, physics, start, review,
         session="2 hours", cpus=2, memory="4 GB", unit="point", contest="match", goal=None):
    """Two-player prompt: both players receive it."""
    w = _words(obj, unit, contest, goal)
    return "\n\n".join([
        f"# {title}", task,
        TIME.format(session=session, duel_time=DUEL_TIME.format(start=start, review=review, **w), **w),
        PROGRAM.format(cpus=cpus, memory=memory, **w),
        INTERFACE_HEAD.format(url=url, rows=_rows(commands), replies=REPLIES_DUEL.format(**w), **w), observation,
        action, "## Rules\n" + rules, "## Geometry and physics\n" + physics]) + "\n"
