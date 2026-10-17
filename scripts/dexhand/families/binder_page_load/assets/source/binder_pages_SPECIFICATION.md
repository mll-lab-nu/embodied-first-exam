# T37: Load punched pages into a ring binder

The target product is the white Avery Standard View Mini Binder, item 05806,
with 1-inch round rings, a 1.4-inch spine, back-mounted hardware, two pockets,
and 5.5 by 8.5-inch paper. The empty binder starts with closed rings and its
covers spread on an ordinary desk. Two loose punched sheets start outside it.

Two complete fixed-base Tianji Marvin arms carry real 22-DoF Sharpa Wave hands.
Only the fourteen arm and forty-four hand actuators may receive controls.
The left hand must grasp, support and align the flexible punched sheets. The
right hand must physically open the ring mechanism, assist threading and close
the ring halves. Both hands must withdraw after successful loading.

## Physical task gates

1. Begin closed and empty. Record initial gaps and zero captured holes.
2. Open through articulated finger contact with the real booster paddle or
   ring halves. All three measured clear tip gaps must exceed 18 mm and remain
   open for at least 0.30 seconds after the opening hand withdraws.
3. Thread both paper sheets through all three intended rings. Each sheet has
   actual empty 16-sided hole boundaries, nominal 6.35 mm punch diameter, and
   69.85 mm center spacing. Capture must be established geometrically and
   topologically, not inferred from center positions alone.
4. Close all three ring gaps to at most 0.30 mm and preserve every hole.
5. Withdraw both hands and retain all six intended holes for at least 1 second.
   Require finite states, no gross interpenetration, no excessive paper strain
   or inverted collapsed hole boundary. A paper tear is failure.

The first bounded trial is only the closed-start booster opening gate. A
pre-open or mechanically incomplete trial never establishes full task success.
Two fresh positive replays and a same-model no-op are required for a successful
candidate. Every native motor control is retained, including steps omitted from
the short movie. No expensive presentation film is authorized before review.
