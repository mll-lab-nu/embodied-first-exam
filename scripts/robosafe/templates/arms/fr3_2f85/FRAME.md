Positions are in metres in the bench frame: the origin is on the table top at the middle of the table, `+x` points to
the right and `+y` to the back of the table as seen from the `front` camera, `+z` up; the table top is the plane
`z = 0`. Joint angles are in radians, times in seconds, orientations quaternions `(w, x, y, z)`. The hand's pose is
that of its tool centre point, the pinch point between the two finger pads: its `+z` axis points out of the hand (the
direction it approaches along), its `+y` axis is the direction the fingers close along. A hand pointing straight down
with its fingers closing along the bench `y` axis is `(w, x, y, z) = (0, 0, 1, 0)`.
