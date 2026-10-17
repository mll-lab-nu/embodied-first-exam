Rows run after their `submit` has answered, so what a row said comes back in the next response: `meta["results"]`
lists the rows that said something (a clipped value, a pose the arm could not reach, an answer) or were refused since
the last response, `{"step", "call", "type", "ok", "result"}` or `{..., "ok": false, "error"}` (`step`: the control
step it ran at; `call`: the `chunk_id` of the `submit` whose plan gave it, -1 for a held step). The operator's answer
to an `ask_operator` comes back in `meta["operator"]` of the first response after it was asked (and stays in
`status()["last_operator_answer"]`); messages that reach the robot in `meta["messages"]`.

**Pictures cost robot time.** While the clock runs, every picture a response carries (each camera's, and a depth
image) costs @@PICTURE_S@@ s of robot time (@@PICTURE_STEPS@@ control steps; two cameras cost twice that): the world, and
your plan, move on by that much while it is made, so a snapshot is no pause. A request returns pictures of at most @@MAX_CAMERAS@@ cameras while
the clock runs, a watch (`get_obs(seconds=s)`) at most @@WATCH_IMAGES@@ pictures per second and no depth
(`spec()["timing"]`); anything more is refused (`ValueError`) and changes nothing. `cameras=None` (the default of
`get_obs` and `submit`) asks for every camera, more than that limit, so once the clock runs pass `cameras=[...]` or
`cameras=[]` on every request, `stop` and the exits included. A controller's calls should ask for
no pictures at all (`cameras=[]`: the fastest call) and read `res.meta["proprio"]["now"]`; look with one camera at a
time. Before the clock starts pictures cost nothing, and every request may ask for every camera and depth.
