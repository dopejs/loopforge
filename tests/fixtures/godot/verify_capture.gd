extends SceneTree

## Checks pixels in a frame recorded from the running fixture. A project icon
## or empty image cannot substitute for the visible play state.
func _initialize() -> void:
	var arguments := OS.get_cmdline_user_args()
	if arguments.size() != 1:
		push_error("expected one captured PNG path")
		quit(2)
		return
	var capture := Image.load_from_file(arguments[0])
	if capture.is_empty() or capture.get_width() != 640 or capture.get_height() != 360:
		push_error("capture is missing or has the wrong viewport")
		quit(3)
		return
	var player := capture.get_pixel(120, 264)
	var hazard := capture.get_pixel(420, 264)
	if player.b < 0.7 or player.r > 0.5:
		push_error("the blue player is not visible in the recorded play state")
		quit(4)
		return
	if hazard.r < 0.7 or hazard.b > 0.5:
		push_error("the red moving hazard is not visible in the recorded play state")
		quit(5)
		return
	quit(0)
