The robot runs at @@CONTROL_HZ@@ control steps per second (one step is @@CONTROL_DT@@ s). One row of a motion type is
the command of one step; with `dt` longer than one step each row is reached on a straight line (of the numbers of the
row) from the command in force, one step at a time (`interpolate="linear"`), or held (`"hold"`). Nothing plans a way
for the arm and nothing stops it from running into things: where it goes is up to you. A row of the other types is one
command, executed as sent (`interpolate` does not apply; `dt` must be `control_dt`); they take no robot time.
