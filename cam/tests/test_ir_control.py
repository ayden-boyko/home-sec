from ir_control import DARK, IR, MIN_ON


def test_dark_turns_ir_on():
    ir = IR()
    assert ir.decide(0, DARK - 1) == "on"
    assert ir.on


def test_bright_keeps_ir_off():
    ir = IR()
    assert ir.decide(0, DARK + 1) == "off"
    assert not ir.on


def test_latched_ir_ignores_ir_lit_brightness():
    ir = IR()
    ir.decide(0, 0)  # dark -> on
    # A bright reading while IR is on must not turn it off before MIN_ON.
    assert ir.decide(MIN_ON - 1, 250) == "on"
    assert ir.on


def test_recheck_after_min_on():
    ir = IR()
    ir.decide(0, 0)
    assert ir.decide(MIN_ON, 250) == "recheck"


def test_recheck_bright_turns_ir_off():
    ir = IR()
    ir.decide(0, 0)
    assert ir.apply_recheck(MIN_ON, DARK + 10) == "off"
    assert not ir.on


def test_recheck_dark_keeps_ir_on():
    ir = IR()
    ir.decide(0, 0)
    assert ir.apply_recheck(MIN_ON, DARK - 10) == "on"
    assert ir.on
