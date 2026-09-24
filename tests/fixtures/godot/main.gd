extends Node2D

## A deliberately small, genuinely playable risk/reward prototype.
##
## Move with A/D or the arrow keys. Hold Space near the moving hazard, then
## release it to dash and score. Charging closer to danger raises the multiplier;
## touching the hazard ends the run. R restarts without reopening the project.
##
## The fixture also exposes a deterministic self-check through an environment
## variable. CI still boots the real scene through the real Godot binary, but the
## check exercises the loop's state transitions instead of treating "process
## started" as proof that the fixture is playable.

const ARENA := Rect2(48.0, 96.0, 544.0, 216.0)
const PLAYER_Y := 264.0
const PLAYER_SPEED := 220.0
const DASH_SPEED := 520.0
const MAX_CHARGE := 1.0
const HAZARD_SPEED := 150.0
const PLAYER_RADIUS := 14.0
const HAZARD_RADIUS := 20.0
const SELF_TEST_VARIABLE := "LOOPFORGE_FIXTURE_SELF_TEST"
const EXIT_CODE_VARIABLE := "LOOPFORGE_FIXTURE_EXIT_CODE"

var player_x := 120.0
var hazard_x := 420.0
var hazard_direction := -1.0
var charge := 0.0
var dash_velocity := 0.0
var score := 0
var multiplier := 1
var game_over := false
var message := "Hold SPACE near danger, then release to dash"


func _ready() -> void:
	if OS.has_environment(EXIT_CODE_VARIABLE):
		get_tree().quit(OS.get_environment(EXIT_CODE_VARIABLE).to_int())
		return
	if OS.get_environment(SELF_TEST_VARIABLE) == "1":
		get_tree().quit(_run_self_test())
		return
	queue_redraw()


func _physics_process(delta: float) -> void:
	if game_over:
		if Input.is_action_just_pressed("restart"):
			reset_run()
		return

	_update_hazard(delta)
	_update_player(delta)
	if absf(player_x - hazard_x) <= PLAYER_RADIUS + HAZARD_RADIUS:
		fail_run()
	queue_redraw()


func _update_hazard(delta: float) -> void:
	hazard_x += hazard_direction * HAZARD_SPEED * delta
	if hazard_x <= ARENA.position.x + HAZARD_RADIUS:
		hazard_x = ARENA.position.x + HAZARD_RADIUS
		hazard_direction = 1.0
	elif hazard_x >= ARENA.end.x - HAZARD_RADIUS:
		hazard_x = ARENA.end.x - HAZARD_RADIUS
		hazard_direction = -1.0


func _update_player(delta: float) -> void:
	if absf(dash_velocity) > 1.0:
		player_x += dash_velocity * delta
		dash_velocity = move_toward(dash_velocity, 0.0, 900.0 * delta)
	else:
		player_x += Input.get_axis("move_left", "move_right") * PLAYER_SPEED * delta

	if Input.is_action_pressed("charge"):
		charge = minf(MAX_CHARGE, charge + delta)
		multiplier = multiplier_for_distance(absf(player_x - hazard_x))
		message = "Charging x%d" % multiplier
	elif Input.is_action_just_released("charge") and charge > 0.0:
		release_dash(1.0 if player_x <= hazard_x else -1.0)

	player_x = clampf(
		player_x,
		ARENA.position.x + PLAYER_RADIUS,
		ARENA.end.x - PLAYER_RADIUS,
	)


func multiplier_for_distance(distance: float) -> int:
	if distance <= 72.0:
		return 3
	if distance <= 140.0:
		return 2
	return 1


func release_dash(direction: float) -> void:
	if charge <= 0.0:
		return
	dash_velocity = direction * DASH_SPEED * (0.45 + 0.55 * charge / MAX_CHARGE)
	score += 100 * multiplier
	message = "+%d  Risk x%d" % [100 * multiplier, multiplier]
	charge = 0.0
	multiplier = 1


func fail_run() -> void:
	game_over = true
	dash_velocity = 0.0
	charge = 0.0
	message = "Run over — press R to restart"
	queue_redraw()


func reset_run() -> void:
	player_x = 120.0
	hazard_x = 420.0
	hazard_direction = -1.0
	charge = 0.0
	dash_velocity = 0.0
	score = 0
	multiplier = 1
	game_over = false
	message = "Hold SPACE near danger, then release to dash"
	queue_redraw()


func _run_self_test() -> int:
	# Far from danger, a release scores the baseline amount.
	charge = 1.0
	multiplier = multiplier_for_distance(240.0)
	release_dash(1.0)
	if score != 100 or dash_velocity <= 0.0:
		push_error("baseline dash did not score or move")
		return 20

	# Close danger must produce the declared risk/reward multiplier.
	charge = 1.0
	multiplier = multiplier_for_distance(60.0)
	release_dash(-1.0)
	if score != 400 or dash_velocity >= 0.0:
		push_error("near-hazard dash did not apply the x3 reward")
		return 21

	# Failure freezes the run and restart reconstructs the initial state.
	fail_run()
	if not game_over or not is_zero_approx(dash_velocity):
		push_error("failure did not stop the run")
		return 22
	reset_run()
	if game_over or score != 0 or not is_equal_approx(player_x, 120.0):
		push_error("restart did not reconstruct the initial state")
		return 23
	return 0


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, Vector2(640.0, 360.0)), Color("111827"))
	draw_rect(ARENA, Color("1f2937"), true)
	draw_line(
		Vector2(ARENA.position.x, PLAYER_Y + PLAYER_RADIUS + 8.0),
		Vector2(ARENA.end.x, PLAYER_Y + PLAYER_RADIUS + 8.0),
		Color("64748b"),
		2.0,
	)
	draw_circle(Vector2(hazard_x, PLAYER_Y), HAZARD_RADIUS, Color("ef4444"))
	draw_circle(Vector2(player_x, PLAYER_Y), PLAYER_RADIUS, Color("38bdf8"))
	if charge > 0.0:
		draw_arc(
			Vector2(player_x, PLAYER_Y),
			PLAYER_RADIUS + 7.0,
			-PI / 2.0,
			-PI / 2.0 + TAU * charge / MAX_CHARGE,
			24,
			Color("facc15"),
			4.0,
		)
	_draw_text(Vector2(48.0, 42.0), "LOOPFORGE RISK CHARGE", 24, Color("f8fafc"))
	_draw_text(Vector2(48.0, 72.0), "Score %d" % score, 20, Color("a7f3d0"))
	_draw_text(Vector2(48.0, 90.0), message, 16, Color("e2e8f0"))
	_draw_text(Vector2(48.0, 338.0), "A/D move   SPACE charge + dash   R restart", 16, Color("94a3b8"))


func _draw_text(position: Vector2, text: String, size: int, color: Color) -> void:
	draw_string(ThemeDB.fallback_font, position, text, HORIZONTAL_ALIGNMENT_LEFT, -1.0, size, color)
