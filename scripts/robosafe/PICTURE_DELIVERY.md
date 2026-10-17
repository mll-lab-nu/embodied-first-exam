# Captured pictures in the control service

This adapter requires the native `capture_pictures` / `deliver_picture_frames` contract. It fails closed when
the installed simulator lacks that contract. A new candidate must include both changes; the frozen R3 trials
and their copied adapters retain their original stream semantics.

`picture_delivery.py` extends the benchmark service without editing the shared `rcb_service.py` or
`rcb_realtime.py` protocol implementations. Each camera frame has its own capture identity. Recorders carry
those identities with RGB/depth/video parts, including cached frames. Only identities remaining in a complete
response body are committed after the HTTP write and flush succeed. Constructing a response in memory, a
failed socket write, or a picture part discarded by response degradation does not count as delivery.

In realtime mode HTTP threads enqueue completion. The simulator thread applies it at its next boundary before
actions or ticks. Native events preserve both the original capture boundary and this conservative delivery
boundary; the service log separately preserves write-complete wall time. These events describe server transport,
not client display, attention, recognition or reasoning. Completions after an exit cannot change its verdict.

Capture events contain camera/time/identity metadata, not trusted external visibility claims. Native replay
recomputes geometry at the captured state. The action journal is checkpointed before capture and the picture
event log is fsynced. Recovery and both fresh-process grading replays consume the same events. Legacy offline
oracle replays without a picture log keep their existing stream semantics.

`tests/test_picture_delivery.py` exercises degradation, failed writes, a real HTTP response, same-step cache
identity, recovery, exit-tail images and two fresh-process replays. Set `RCB_PICTURE_RT_CHECK=1` for its nonzero-step
realtime snapshot/watch case, under the shared realtime slot policy. These development checks are separate from
the installed-image admission gates for a release candidate.
