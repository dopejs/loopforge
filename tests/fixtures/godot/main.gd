extends Node2D

## Quits immediately with a controllable exit code.
##
## `run test` boots this scene with `--headless --quit`, and the adapter reads
## the process exit code to decide whether the test evidence records a pass or
## a failure. Driving that code from the environment lets one fixture exercise
## both outcomes, so the failure path is covered by a real engine run rather
## than by a stub that never boots.
func _ready() -> void:
	var code := 0
	if OS.has_environment("LOOPFORGE_FIXTURE_EXIT_CODE"):
		code = OS.get_environment("LOOPFORGE_FIXTURE_EXIT_CODE").to_int()
	get_tree().quit(code)
