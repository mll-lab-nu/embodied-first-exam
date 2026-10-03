"""The program-play prompt for turn-based (precision) sports: one fixed structure, like program_prompt.py (2026-10-02).

Turn-based sports (darts, archery, bowling, golf putting, basketball shooting, billiards, curling) wait for the player:
nothing moves between shots, and time is a chess clock that runs only on the player's own turn. Principles: clear,
simple, general. Sections, in this order:
  1. Task                  sport-specific  who you control, the opponent, how to win (including any shot limit)
  2. Time                  general         the waiting world, the chess clock, the review after each shot
  3. Write a program       general         program play, staying in the loop, rules, the container
  4. Interface             general format  commands and HTTP endpoints; then the sport's observation and action
  5. Rules                 sport-specific  scoring, turns; the opponent in a sentence or two
  6. Geometry and physics  sport-specific  coordinates, sizes and the physics needed to play
A sport supplies the sport-specific texts; `single()` and `duel()` assemble the prompt.
"""

CLOCK = "60 minutes"     # every precision sport, single and duel (decided 2026-10-02)

TIME = """## Time
Nothing moves while you think: the world waits for your shot. Time is a chess clock: you have {clock} of real time
for the whole {contest}, and your clock runs only on your turn (thinking, tool calls, the model API, your programs and
your reviews all count; {not_counted}). `clock_left_s` is in every reply. **If your clock runs out, the
{contest} ends {as_loss}.**

After each of your shots (except one that ends the {contest}), send `game ready "WHY" "PLAN"` (a short review: why the shot went well or badly and what you
will change) before the game goes on. {goal}{duel_time} The {contest} is graded when your session ends: stay until it is
over."""

DUEL_TIME = """ After one player runs `game start`, the other has {start} to start."""

PROGRAM = """## Write a program
You may write a program that observes, measures your shots in the images, computes your next command and sends it,
without a new model response for each shot. You may also act yourself. You stay in the loop: watch its log, and stop,
fix and restart it whenever needed. Use the reviews to improve it. Only you send `game start` and `game ready`.

- Use only the camera images, the service's replies and this document; no simulator internals or hidden state.
- One action at a time: an action sent before the previous one has returned is refused (HTTP 429).{turns}
- Your container: Python 3.12 with numpy, SciPy, Pillow and OpenCV (headless); {cpus} CPUs, {memory}; no internet during
  the {contest}. Keep your scripts, logs and notes in `/app/output/`."""

TURNS = """
- Players take turns: an action sent when it is not your turn is refused (HTTP 409); `game wait` returns when it is
  your turn (or the match is over)."""

INTERFACE_HEAD = """## Interface
Use the `game` command, or, from a program, the same calls as HTTP with JSON at `{url}` (faster than starting a process):

| `game` command | HTTP | |
| --- | --- | --- |
{rows}

{replies}"""

GOAL_OPPONENT = """Your goal is to win, not only to score: watch how your shots and your opponent's turns go and
adapt your program and strategy."""
GOAL_SOLO = """Do as well as you can: reaching the success line above is the minimum. Watch how your shots go and adapt
your program and strategy."""


def _time(opponent, contest, duel_time=""):
    return TIME.format(clock="{clock}", contest=contest,
                       as_loss="as a loss" if opponent else "and counts as a failure",
                       not_counted="your opponent's turns and the simulation do not" if opponent else "the simulation does not",
                       goal=GOAL_OPPONENT if opponent else GOAL_SOLO, duel_time=duel_time)


REPLIES_OPPONENT = """Every reply includes the current state ({state}, whose turn it is, `clock_left_s`) and the result of any shot
since your previous call."""
REPLIES_SOLO = """Every reply includes the current state ({state}, `clock_left_s`) and the result of any shot since your previous
call."""


def _rows(cmds):
    return "\n".join(f"| `{c}` | `{h}` | {w} |" for c, h, w in cmds)


def single(*, title, task, url, commands, observation, action, rules, physics, opponent=True, clock=CLOCK,
           cpus=4, memory="8 GB", contest=None, state="score"):
    """Single-player prompt; opponent=False for a sport played alone (archery, bowling, ...). contest: the noun for the
    whole game (default "match" with an opponent, "round" alone); state: what the reply's state shows besides the turn
    and the clock (default "score"). commands: [(game command, HTTP call, what it does)]."""
    contest = contest or ("match" if opponent else "round")
    replies = (REPLIES_OPPONENT if opponent else REPLIES_SOLO).format(state=state)
    return "\n\n".join([
        f"# {title}", task,
        _time(opponent, contest).format(clock=clock),
        PROGRAM.format(cpus=cpus, memory=memory, turns="", contest=contest),
        INTERFACE_HEAD.format(url=url, rows=_rows(commands), replies=replies), observation, action,
        "## Rules\n" + rules, "## Geometry and physics\n" + physics]) + "\n"


def duel(*, title, task, url, commands, observation, action, rules, physics, start, clock=CLOCK, cpus=2,
         memory="4 GB", contest="match", state="score"):
    """Two-player prompt: both players receive it. Each player has its own chess clock; the sport's service must
    implement `game wait` (returns when it is the caller's turn or the match is over)."""
    return "\n\n".join([
        f"# {title}", task,
        _time(True, contest, DUEL_TIME.format(start=start)).format(clock=clock),
        PROGRAM.format(cpus=cpus, memory=memory, turns=TURNS, contest=contest),
        INTERFACE_HEAD.format(url=url, rows=_rows(commands), replies=REPLIES_OPPONENT.format(state=state)), observation,
        action, "## Rules\n" + rules, "## Geometry and physics\n" + physics]) + "\n"
