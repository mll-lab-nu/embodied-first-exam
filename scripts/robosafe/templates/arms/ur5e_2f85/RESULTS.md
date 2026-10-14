`meta["results"]` lists the rows of the call that said something (a clipped value, a pose the arm could not reach, an
answer) or were refused, `{"row", "type", "ok", "result"}` or `{"row", "type", "ok": false, "error"}` (`row`: its
index in the chunk), and `meta["result"]` is the last executed row's result. A chunk stops at the first row the robot
refuses (`meta["blocked"]`, `meta["error"]`).
