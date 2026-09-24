# Echo Lantern

A small Godot 4 2D prototype for the independent M2 workflow check. Move with
WASD or arrows; Space toggles the lantern; R restarts. Beacons can be seen and
collected only while the lantern is lit, and the pursuer moves only while it is
lit. Collect all three beacons without being caught.

The first prompt, hypothesis, scope, and execution record are in
`docs/evaluations/m2-unseen-prototype.md`. This is a candidate for an external
playtest, not evidence that players understand or enjoy the mechanic.

To verify the deterministic mechanic inside Godot:

```sh
LOOPFORGE_ECHO_SELF_TEST=1 godot4 --headless --path examples/echo-lantern --quit-after 60
```

A successful check prints `ECHO_LANTERN_SELF_TEST_OK`. For a visible capture,
set `LOOPFORGE_ECHO_CAPTURE=1` and record a frame using Godot's `--write-movie`
option; this turns the lantern on at startup without changing normal play.
