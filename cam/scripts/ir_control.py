"""IR illuminator decision logic, kept free of Pi imports so it can be tested.

The camera's own image cannot be trusted while IR is on: the IR light lifts the
measured brightness, so deciding "bright enough, switch off" from an IR-lit
frame turns IR off, the image goes dark, and it flips straight back on. Instead
IR latches on for MIN_ON seconds, then briefly switches off to read the real
ambient light. Only that reading may turn IR off. A wrong reading self-corrects
on the next loop.

DARK is the one number to calibrate: read the "brightness" field from /health in
the dark and in light, then set DARK between the two.
"""

DARK = 45      # mean luma (0-255) below which the room counts as dark
MIN_ON = 120   # seconds IR stays on before re-checking ambient light
SETTLE = 1.5   # seconds to let auto-exposure settle before the re-check


class IR:
    def __init__(self, dark=DARK, min_on=MIN_ON):
        self.dark = dark
        self.min_on = min_on
        self.on = False
        self.since = 0.0

    def decide(self, now, brightness):
        """Next action for the caller: 'on', 'off', or 'recheck'."""
        if not self.on:
            if brightness < self.dark:
                self.on = True
                self.since = now
                return "on"
            return "off"
        if now - self.since >= self.min_on:
            return "recheck"
        return "on"

    def apply_recheck(self, now, brightness):
        """Feed the ambient reading taken with IR off; returns 'on' or 'off'."""
        if brightness < self.dark:
            self.since = now
            return "on"
        self.on = False
        return "off"
