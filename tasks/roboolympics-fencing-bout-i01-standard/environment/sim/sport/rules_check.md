# Fencing (epee): the rules check (fencing-7, the phrase-level sport)

Every article and value cited by the fencing tasks (README, prompt, code), checked against the two PDFs of the FIE
rules, edition of August 2026:

- Technical Rules: https://static.fie.org/uploads/40/204126-Technical%20rules%20August%202026%20ang.pdf
- Material Rules: https://static.fie.org/uploads/40/204156-book%20material%20August%202026%20ang.pdf

The bout (bout.py):

| Article | The rulebook says | Implemented | |
|---|---|---|---|
| t.22 | the fencers come on guard before 'Play!' | every phrase starts on guard, 1.95 m apart (pelvis to pelvis) | deviation D1 (the distance: closer than the on-guard lines) |
| t.37 | duration = effective fencing time between 'Play!' and 'Halt!' | each phrase takes its measured time to the halt (3 s without a touch) | match |
| t.39.1 | direct elimination: 15 hits, or three periods of three minutes with a one-minute rest between | 15 touches, 9 minutes of fencing time as one period | deviation D4 (no rests) |
| t.40.1-2 | the bout ends at 15 hits or after 9 minutes of effective fencing time; more hits wins | the same | match |
| t.40.3 | equal at the end of regulation time: one minute for a deciding hit, the winner if still equal drawn by lot before it | the same (the lot seeded by the seed, drawn for the first fencer) | match |
| t.38.1.b | (pools) at epee at 4-4 a double hit is not counted | at 14-14 a double is not counted | deviation D5 (no clause for 14-14 in direct elimination) |
| t.44.1 | at the end of time the apparatus is cut off; hits registered before count | a phrase whose touch would come after the end of time ends without it | match |
| t.92 | both hit and both registered: a double hit, one hit against each | the same; in the extra minute the scores stay equal and the minute goes on | match |
| t.124 (1, 3) | one minute of fencing without a hit: 'Halt!'; direct elimination: 1st time P-red to both, 2nd time P-black to the lower score (equal: the lower seeding, lots among fencers not ranked); no P-card at 14-14; the minute restarts after each hit, hit off the target, annulled hit, penalty hit and at each period; not when the scores are equal at the end of regulation time | 60 s of fencing time without a touch: 1st P-red to both (a penalty touch each), 2nd P-black to the lower score (equal: a seeded lot), no card at 14-14, the minute restarts after touches, doubles, annulled doubles and P-red cards; not in the extra minute | match (one period: D4; the lot: D9) |
| t.170 (0.5) | the P-cards of t.124 | the same | match |

The phrases (measured in fencing-6's world, docs/screening/fencing/phrase/):

| Article | The rulebook says | In the measured phrases | |
|---|---|---|---|
| t.24 | fencing at close quarters allowed while the weapons can be wielded | arms and blades touching: the phrase goes on | match |
| t.25, t.33-t.35, t.56.10 | corps a corps, a limit crossed, a fall halt the phrase; a hit during or after a fall is annulled | fencing-6's referee: such a phrase would end without a touch; none of the 2916 phrases did | deviation D3 |
| t.90.1 | epee: thrusting weapon, hits only with the point | only the point registers | match |
| t.91 | target: the whole body, clothing and equipment | the whole robot, not its epee | match (D2: the robot is the body) |
| t.93 / t.94.1, Annexe B (d) | hits on the ground, between points or on the guard are not registered / annulled | the point on the floor, the opponent's blade, guard or grip does not register | match |
| m.14 | the epee ready for use weighs less than 770 g | 0.455 kg (a standard-parts epee, bodies/hands/epee.xml) | match |
| m.16.3 | blade at most 90 cm | 0.90 m | match |
| m.17.1 | guard passes a 13.5 cm gauge, depth 3-5.5 cm | 13.5 cm diameter (a 1 cm disc: the library's epee) | match (diameter; depth: D10) |
| m.19.2 | the point registers under a pressure of more than 750 g | more than 7.35 N (750 g x 9.81 m/s^2) on the point along the blade | match |
| Annexe B, B. Epee (b) | under 40 ms between hits: a double; over 50 ms: one hit; tolerance between | 45 ms lockout | match |
| Annexe B, B. Epee (c) | hits of 2-10 ms registered; nothing under 2 ms | at least 2 ms (3 consecutive 1 ms samples) | match |

Deviations that are not in the rulebook's articles: the fencers are the robot library's Unitree G1 humanoids on
NVIDIA's SONIC whole-body policy, commanded by intentions (D8); the ends of the piste are drawn per phrase (D11); the
sport is a preview, a strategy special case accepted by the maintainers (D12).
