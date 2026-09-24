extends Node2D

const SCREEN := Vector2(960, 540)
const PLAYER_START := Vector2(90, 430)
const PURSUER_START := Vector2(480, 270)
const PLAYER_SPEED := 190.0
const PURSUER_SPEED := 100.0
const BEACONS := [Vector2(190, 130), Vector2(770, 130), Vector2(790, 410)]

var player := PLAYER_START
var pursuer := PURSUER_START
var lantern_on := false
var collected := [false, false, false]
var outcome := "running"


func _ready() -> void:
	if OS.get_environment("LOOPFORGE_ECHO_SELF_TEST") == "1":
		_run_self_test()
	elif OS.get_environment("LOOPFORGE_ECHO_CAPTURE") == "1":
		lantern_on = true
	return


func _input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo:
		return
	if event.keycode == KEY_R:
		_reset()
	elif event.keycode == KEY_SPACE and outcome == "running":
		lantern_on = not lantern_on
		queue_redraw()


func _process(delta: float) -> void:
	if outcome != "running":
		return
	var direction := Vector2.ZERO
	if Input.is_key_pressed(KEY_LEFT) or Input.is_key_pressed(KEY_A):
		direction.x -= 1.0
	if Input.is_key_pressed(KEY_RIGHT) or Input.is_key_pressed(KEY_D):
		direction.x += 1.0
	if Input.is_key_pressed(KEY_UP) or Input.is_key_pressed(KEY_W):
		direction.y -= 1.0
	if Input.is_key_pressed(KEY_DOWN) or Input.is_key_pressed(KEY_S):
		direction.y += 1.0
	_move_player(direction, delta)
	_advance_pursuer(delta)
	_update_collisions()
	queue_redraw()


func _move_player(direction: Vector2, delta: float) -> void:
	player += direction.normalized() * PLAYER_SPEED * delta
	player = player.clamp(Vector2(24, 75), SCREEN - Vector2(24, 24))


func _advance_pursuer(delta: float) -> void:
	if lantern_on and outcome == "running":
		pursuer = pursuer.move_toward(player, PURSUER_SPEED * delta)


func _update_collisions() -> void:
	if lantern_on:
		for index in BEACONS.size():
			if not collected[index] and player.distance_to(BEACONS[index]) < 27.0:
				collected[index] = true
		if collected.all(func(value: bool) -> bool: return value):
			outcome = "won"
			lantern_on = false
	if outcome == "running" and player.distance_to(pursuer) < 27.0:
		outcome = "caught"
		lantern_on = false


func _reset() -> void:
	player = PLAYER_START
	pursuer = PURSUER_START
	lantern_on = false
	collected = [false, false, false]
	outcome = "running"
	queue_redraw()


func _draw() -> void:
	var background := Color("233449") if lantern_on else Color("101923")
	draw_rect(Rect2(Vector2.ZERO, SCREEN), background)
	draw_rect(Rect2(18, 67, 924, 451), Color("415469"), false, 2.0)
	for index in BEACONS.size():
		if not collected[index] and lantern_on:
			draw_circle(BEACONS[index], 21.0, Color("f1cf73"))
			draw_circle(BEACONS[index], 9.0, Color("fff3bc"))
	if lantern_on or outcome == "caught":
		draw_circle(pursuer, 23.0, Color("d45c68"))
		draw_circle(pursuer + Vector2(-7, -5), 3.0, Color.WHITE)
		draw_circle(pursuer + Vector2(7, -5), 3.0, Color.WHITE)
	draw_circle(player, 17.0, Color("8bd9d0"))
	if lantern_on:
		draw_arc(player, 34.0, 0.0, TAU, 48, Color("f1cf73"), 2.0)
	var found := 0
	for value in collected:
		if value:
			found += 1
	var font := ThemeDB.fallback_font
	draw_string(font, Vector2(24, 34), "ECHO LANTERN   Beacons: %d/3" % found,
		HORIZONTAL_ALIGNMENT_LEFT, -1, 22, Color.WHITE)
	draw_string(font, Vector2(24, 60), "WASD / arrows: move   SPACE: light   R: restart",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color("cad7de"))
	var hint := "Light reveals beacons, but lets the pursuer move."
	if outcome == "won":
		hint = "All beacons found! Press R to play again."
	elif outcome == "caught":
		hint = "The pursuer caught you. Press R to try again."
	draw_string(font, Vector2(25, 503), hint,
		HORIZONTAL_ALIGNMENT_LEFT, -1, 17, Color("f1cf73"))


func _run_self_test() -> void:
	var frozen := pursuer
	_advance_pursuer(1.0)
	if pursuer != frozen:
		_fail_self_test("pursuer moved in darkness")
		return
	var light_key := InputEventKey.new()
	light_key.keycode = KEY_SPACE
	light_key.pressed = true
	_input(light_key)
	if not lantern_on:
		_fail_self_test("space did not light the lantern")
		return
	_advance_pursuer(1.0)
	if pursuer == frozen:
		_fail_self_test("pursuer did not move in light")
		return
	_input(light_key)
	player = BEACONS[0]
	_update_collisions()
	if lantern_on or collected[0]:
		_fail_self_test("a beacon was collected in darkness")
		return
	_input(light_key)
	for point in BEACONS:
		player = point
		_update_collisions()
	if outcome != "won" or not collected.all(func(value: bool) -> bool: return value):
		_fail_self_test("beacon collection did not win")
		return
	var restart_key := InputEventKey.new()
	restart_key.keycode = KEY_R
	restart_key.pressed = true
	_input(restart_key)
	if outcome != "running" or lantern_on or collected.any(func(value: bool) -> bool: return value):
		_fail_self_test("restart did not reset the game")
		return
	var old_player := player
	_move_player(Vector2.RIGHT, 0.1)
	if player.x <= old_player.x:
		_fail_self_test("player did not move right")
		return
	player = pursuer
	_update_collisions()
	if outcome != "caught":
		_fail_self_test("pursuer collision did not fail")
		return
	print("ECHO_LANTERN_SELF_TEST_OK")
	get_tree().quit(0)


func _fail_self_test(message: String) -> void:
	push_error(message)
	get_tree().quit(1)
