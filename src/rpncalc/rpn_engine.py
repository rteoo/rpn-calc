"""The HP 50g command line and scientific function set, wired to `RpnStack`.

This is the heart of the project: the distinction between an OPEN command
line (mid-entry, editing a number) and an EMPTY one (nothing pending, keys
act on the stack itself) drives every row of the input table below. See
`docs/plans/rpn-on-omacalc.md`'s CP3 semantics table - this module is a
direct implementation of it.

No Qt. The stack always holds plain floats; angle mode is applied only at
the trig function boundary, and display formatting only in `stack_lines`.
"""

from __future__ import annotations

import math

from .numeric import NumberFormat, format_number, parse_number, seal_number
from .stack import RpnStack, StackError

# omacalc/the 50g accept both the ASCII operator keys and the typographic
# glyphs already used on-screen; normalize to ASCII once, at the door.
_NORMALIZE = {"−": "-", "×": "*", "÷": "/"}

_DIGITS = set("0123456789")

# The mode a fresh calculator starts in. `backend.py` imports this so a saved
# setting and a missing one cannot disagree about the default.
DEFAULT_ANGLE_MODE = "RAD"
ANGLE_MODES = ("DEG", "RAD")

# The interactive stack's soft menu, in F1..F6 order, exactly as the 50g draws
# it. VIEW opens a full-screen object viewer, which says nothing a plain number
# has not already said on its own line, so it stays unimplemented and dimmed.
INTERACTIVE_MENU = ("ECHO", "VIEW", "EDIT", "PICK", "ROLL", "ROLLD")
_INTERACTIVE_COMMANDS = {
    "ist_echo", "ist_view", "ist_edit", "ist_pick", "ist_roll", "ist_rolld",
    "ist_drop", "ist_exit", "ist_top", "ist_bottom",
}
_MENU_COMMANDS = ("ist_echo", "ist_view", "ist_edit", "ist_pick", "ist_roll",
                  "ist_rolld")


class CalcError(Exception):
    """A math error that is not stack underflow: infinite/undefined results
    and out-of-domain inputs. Always raised *before* any stack mutation for
    the failing operation, so `press` can turn it into `self.error` while
    leaving the stack exactly as it was found.
    """


class RpnEngine:
    _UNARY_METHODS = {
        "sqrt": "_fn_sqrt",
        "sq": "_fn_sq",
        "inv": "_fn_inv",
        "ln": "_fn_ln",
        "exp": "_fn_exp",
        "log": "_fn_log",
        "alog": "_fn_alog",
        "sin": "_fn_sin",
        "cos": "_fn_cos",
        "tan": "_fn_tan",
        "asin": "_fn_asin",
        "acos": "_fn_acos",
        "atan": "_fn_atan",
        "abs": "_fn_abs",
        "neg": "_fn_neg",
    }
    _BINARY_METHODS = {
        "+": "_fn_add",
        "-": "_fn_sub",
        "*": "_fn_mul",
        "/": "_fn_div",
        "pow": "_fn_pow",
        "mod": "_fn_mod",
        "percent": "_fn_percent",
        "xroot": "_fn_xroot",
    }
    # Stack commands that take no operand from the entry itself - DEPTH and
    # the fixed-arity reorder commands (roll/rolld/pick pop their own count
    # argument off level 1, see `_roll`/`_rolld`/`_pick`).
    _STACK_COMMANDS = frozenset(
        {"drop", "swap", "dup", "over", "rot", "unrot", "roll", "rolld", "pick", "depth"}
    )

    def __init__(self) -> None:
        self.stack = RpnStack()
        # None = command line closed. A str (possibly "") = open for entry.
        self.command_line: str | None = None
        self.angle_mode = DEFAULT_ANGLE_MODE
        self.number_format = NumberFormat()
        self.error: str | None = None
        # Engine-level UNDO: a snapshot of the whole stack taken before the
        # last *command* (as opposed to `RpnStack.last_args`, which records
        # only the single most recent low-level stack primitive - not enough
        # to undo "commit entry, then apply operator" as one user action).
        self._undo_snapshot: list[float] | None = None
        # The interactive stack browser: None when closed, otherwise the level
        # the cursor sits on (1 = level 1, counting up into the stack).
        self.cursor_level: int | None = None

    # -- UI-facing surface -------------------------------------------------

    @property
    def depth(self) -> int:
        return self.stack.depth

    def stack_lines(self) -> list[str]:
        """Formatted stack, level 1 first, honoring the current display mode."""
        return [format_number(v, self.number_format) for v in self.stack.to_list()]

    def set_angle_mode(self, mode: str) -> None:
        if mode not in ANGLE_MODES:
            raise ValueError(f"unknown angle mode: {mode!r}")
        self.angle_mode = mode

    def set_number_format(self, fmt: NumberFormat) -> None:
        self.number_format = fmt

    # -- entry point ---------------------------------------------------------

    def knows(self, key: str) -> bool:
        """Whether `key` is a command this engine can dispatch.

        The keyboard and the engine are built separately, so this is what the
        keymap contract test checks a face full of legends against.
        """
        key = _NORMALIZE.get(key, key)
        return (
            key in _DIGITS
            or key in (".", "eex", "enter", "spc", "backspace", "chs",
                       "clear", "clear_entry", "undo", "pi")
            or key in self._UNARY_METHODS
            or key in self._BINARY_METHODS
            or key in self._STACK_COMMANDS
            or key in _INTERACTIVE_COMMANDS
            or key in ("up", "down", "left", "right")
        )

    def press(self, key_id: str) -> None:
        key = _NORMALIZE.get(key_id, key_id)
        # "Errors ... clear the message on the next keypress" - every press
        # gets a clean slate before it does anything else.
        self.error = None
        try:
            self._dispatch(key)
        except (StackError, CalcError) as exc:
            self.error = str(exc)

    def _dispatch(self, key: str) -> None:
        if not self.knows(key):
            return  # an unbound key is a no-op, never a crash
        if key in ("up", "down", "left", "right"):
            self._handle_arrow(key)
        elif self.cursor_level is not None:
            self._dispatch_interactive(key)
        elif key in _INTERACTIVE_COMMANDS:
            return  # menu keys mean nothing while the browser is closed
        elif key in _DIGITS or key in (".", "eex"):
            self._handle_entry_key(key)
        elif key == "enter":
            self._handle_enter()
        elif key == "spc":
            self._handle_spc()
        elif key == "backspace":
            self._handle_backspace()
        elif key == "chs":
            self._handle_chs()
        elif key == "clear_entry":
            self._handle_clear_entry()
        elif key == "clear":
            self._handle_clear()
        elif key == "undo":
            self._handle_undo()
        else:
            # Every operator, function, and stack command: implicit ENTER of
            # any open command line first, then apply. This is the one rule
            # that makes "3 SPC 4 +" and "clicking [+] mid-entry" both work.
            # Recorded before the commit, not after the command: a command
            # that errors has still entered the command line onto the stack,
            # and UNDO has to take that back too.
            self._undo_snapshot = self.stack.to_list()
            self._commit_entry()
            self._apply_command(key)

    # -- the interactive stack -----------------------------------------------
    #
    # The 50g's stack browser, reached with the up arrow: a cursor walks the
    # levels and the soft menu acts on whichever one it sits on. This is the
    # feature that makes a deep stack workable instead of something you have to
    # unpick with SWAP and ROT.

    def menu_labels(self) -> list[str]:
        """The soft-menu row, or empty when no menu is showing."""
        return list(INTERACTIVE_MENU) if self.cursor_level is not None else []

    def menu_enabled(self) -> list[bool]:
        return [self.knows_menu(i) for i in range(len(INTERACTIVE_MENU))]

    def knows_menu(self, index: int) -> bool:
        if self.cursor_level is None or not 0 <= index < len(_MENU_COMMANDS):
            return False
        return _MENU_COMMANDS[index] != "ist_view"  # VIEW is not implemented

    def press_menu(self, index: int) -> None:
        if self.knows_menu(index):
            self.press(_MENU_COMMANDS[index])

    def _handle_arrow(self, key: str) -> None:
        if self.cursor_level is None:
            # Up opens the browser on level 1, as pressing it on the 50g does.
            # An empty stack has nothing to browse.
            if key == "up" and self.stack.depth >= 1:
                self.cursor_level = 1
            return
        if key == "up":
            self.cursor_level = min(self.cursor_level + 1, self.stack.depth)
        elif key == "down":
            # Stepping below level 1 leaves the browser, which is the quickest
            # way out and matches how the cursor got in.
            if self.cursor_level == 1:
                self.cursor_level = None
            else:
                self.cursor_level -= 1
        elif key == "left":
            self.cursor_level = 1
        else:  # right - ours, not the 50g's: jump to the deepest level.
            self.cursor_level = self.stack.depth

    def _dispatch_interactive(self, key: str) -> None:
        """While the browser is open it owns the keyboard.

        Anything not part of browsing is ignored rather than applied, so a
        mistyped key cannot silently rearrange a stack mid-reorganisation.
        """
        if key in ("enter", "clear_entry", "ist_exit"):
            self.cursor_level = None
        elif key == "backspace" or key == "ist_drop":
            self._interactive_drop()
        elif key == "ist_echo":
            self._interactive_echo()
        elif key == "ist_edit":
            self._interactive_edit()
        elif key == "ist_pick":
            self._interactive_reorder(self.stack.pick, grows=True)
        elif key == "ist_roll":
            self._interactive_reorder(self.stack.roll, grows=False)
        elif key == "ist_rolld":
            self._interactive_reorder(self.stack.rolld, grows=False)

    def _interactive_reorder(self, op, grows: bool) -> None:
        level = self.cursor_level
        assert level is not None
        self._undo_snapshot = self.stack.to_list()
        op(level)
        # The cursor stays on the same level *number* rather than following the
        # value it acted on - PICK shifts everything up by one, and the 50g
        # leaves the pointer where it was rather than chasing the object.
        self.cursor_level = min(level, self.stack.depth)

    def _interactive_echo(self) -> None:
        """Copy the selected level into the command line, leaving the stack."""
        level = self.cursor_level
        assert level is not None
        text = format_number(self.stack.peek(level), self.number_format)
        if self.command_line is None:
            self.command_line = text
        else:
            self.command_line += " " + text

    def _interactive_edit(self) -> None:
        """Lift the selected level off the stack and into the command line."""
        level = self.cursor_level
        assert level is not None
        self._undo_snapshot = self.stack.to_list()
        value = self.stack.peek(level)
        self.stack.roll(level)  # bring it to level 1 so it can be dropped
        self.stack.drop()
        self.command_line = format_number(value, self.number_format)
        self.cursor_level = None

    def _interactive_drop(self) -> None:
        level = self.cursor_level
        assert level is not None
        self._undo_snapshot = self.stack.to_list()
        self.stack.roll(level)
        self.stack.drop()
        # Browsing a stack that no longer has levels makes no sense.
        self.cursor_level = min(level, self.stack.depth) or None

    # -- command-line editing ------------------------------------------------

    def _handle_entry_key(self, key: str) -> None:
        if self.command_line is None:
            if key == "eex":
                # Judgment call: the 50g defaults the mantissa to 1 when EEX
                # opens a fresh entry (so "EEX 3" alone reads as 1E3), rather
                # than leaving a bare "E3" with no digits before it.
                self.command_line = "1E"
            elif key == ".":
                self.command_line = "."
            else:
                self.command_line = key
            return

        if key == "eex":
            if "E" not in self.command_line:  # only one exponent marker
                self.command_line += "E"
        elif key == ".":
            if "E" in self.command_line:
                return  # exponents are whole numbers; the 50g ignores the key
            if "." not in self.command_line:  # only one decimal point
                self.command_line += "."
        else:
            self.command_line += key

    def _handle_enter(self) -> None:
        snapshot = self.stack.to_list()
        if self.command_line is not None:
            self._commit_entry()
        else:
            self.stack.dup()  # ENTER on an empty command line: DUP level 1
        self._undo_snapshot = snapshot

    def _handle_spc(self) -> None:
        if self.command_line is None:
            return  # no-op when the command line is empty
        if self.command_line != "" and not self.command_line.endswith(" "):
            self.command_line += " "

    def _handle_backspace(self) -> None:
        if self.command_line is not None:
            trimmed = self.command_line[:-1]
            self.command_line = trimmed if trimmed != "" else None
            return
        snapshot = self.stack.to_list()
        self.stack.drop()  # backspace on an empty command line: DROP level 1
        self._undo_snapshot = snapshot

    def _handle_chs(self) -> None:
        if self.command_line is not None:
            self.command_line = _toggle_sign_in_entry(self.command_line)
            return
        snapshot = self.stack.to_list()
        self._apply_unary(self._fn_neg)  # CHS on an empty command line: NEG level 1
        self._undo_snapshot = snapshot

    def _handle_clear(self) -> None:
        """CLEAR empties the stack, as right-shift CLEAR does on the 50g."""
        self._undo_snapshot = self.stack.to_list()
        self.command_line = None
        self.stack.clear()

    def _handle_clear_entry(self) -> None:
        """CANCEL/DEL: abandon what is being typed, leave the stack alone."""
        self.command_line = None

    def _handle_undo(self) -> None:
        if self._undo_snapshot is None:
            return
        self.stack.clear()
        for value in reversed(self._undo_snapshot):  # to_list() is level-1-first
            self.stack.push(value)
        self._undo_snapshot = None  # single-level UNDO, like the 50g's UNDO key

    def paste_value(self, value: float) -> None:
        """Adopt a pasted number as a new level 1, as if it had been entered."""
        if not math.isfinite(value):
            raise CalcError("Infinite Result")
        self._undo_snapshot = self.stack.to_list()
        self.command_line = None
        self.stack.push(value)

    def copy_text(self) -> str:
        """What Ctrl+C should take: whatever the eye is on."""
        if self.command_line is not None:
            return self.command_line
        if self.stack.depth:
            return format_number(self.stack.peek(1), self.number_format)
        return ""

    def _commit_entry(self) -> None:
        """Parse the open command line (SPC-separated -> one push per token,
        left to right) and close it. No-op if the command line is closed.
        """
        if self.command_line is None:
            return
        # Parse everything before pushing anything: an entry like "1 2 1E999"
        # must not leave half its numbers on the stack.
        values = [_parse_token(token) for token in self.command_line.split()]
        for value in values:
            self.stack.push(value)
        self.command_line = None

    # -- operators, functions, stack commands --------------------------------

    def _apply_command(self, key: str) -> None:
        if key in self._UNARY_METHODS:
            self._apply_unary(getattr(self, self._UNARY_METHODS[key]))
        elif key in self._BINARY_METHODS:
            self._apply_binary(getattr(self, self._BINARY_METHODS[key]))
        elif key == "pi":
            self.stack.push(math.pi)
        elif key == "drop":
            self.stack.drop()
        elif key == "swap":
            self.stack.swap()
        elif key == "dup":
            self.stack.dup()
        elif key == "over":
            self.stack.over()
        elif key == "rot":
            self.stack.rot()
        elif key == "unrot":
            self.stack.unrot()
        elif key == "roll":
            self._roll()
        elif key == "rolld":
            self._rolld()
        elif key == "pick":
            self._pick()
        elif key == "depth":
            self.stack.depth_command()
        else:  # pragma: no cover - _dispatch filters unknown keys first
            raise ValueError(f"unknown key id: {key!r}")

    def _apply_unary(self, fn) -> None:
        if self.stack.depth < 1:
            raise StackError("Too Few Arguments")
        x = self.stack.peek(1)
        result = self._evaluate(fn, x)  # raises before the stack is touched
        self.stack.pop()
        self.stack.push(result)

    def _apply_binary(self, fn) -> None:
        if self.stack.depth < 2:
            raise StackError("Too Few Arguments")
        b = self.stack.peek(1)
        a = self.stack.peek(2)
        result = self._evaluate(fn, a, b)
        self.stack.pop()
        self.stack.pop()
        self.stack.push(result)

    @staticmethod
    def _evaluate(fn, *args: float) -> float:
        """Run a calculator function and let only a finite float out.

        Every function goes through here rather than guarding itself, because
        the per-function version was easy to forget: x squared pushed inf onto
        the stack, which then made the whole display unrenderable, and e^x's
        own guard was unreachable because math.exp raises before returning.
        """
        try:
            result = fn(*args)
        except OverflowError:
            raise CalcError("Infinite Result") from None
        except ZeroDivisionError:
            # 0 ** -n. Python raises where IEEE-754 would say infinity.
            raise CalcError("Infinite Result") from None
        except ValueError:
            raise CalcError("Invalid Input") from None
        if isinstance(result, complex):
            raise CalcError("Invalid Input")
        if not math.isfinite(result):
            raise CalcError("Infinite Result")
        return result

    def _fn_percent(self, base: float, pct: float) -> float:
        """HP's %: level 2 times level 1 percent, consuming both operands."""
        return base * pct / 100.0
    def _roll(self) -> None:
        self._reorder_with_count(self.stack.roll)

    def _rolld(self) -> None:
        self._reorder_with_count(self.stack.rolld)

    def _pick(self) -> None:
        self._reorder_with_count(self.stack.pick)

    def _reorder_with_count(self, op) -> None:
        # ROLL/ROLLD/PICK take their level count from level 1 itself, as on
        # the real 50g: "3 ROLL" means "pop 3, then roll level 3 to level 1".
        if self.stack.depth < 1:
            raise StackError("Too Few Arguments")
        n = int(self.stack.peek(1))
        if n < 1 or self.stack.depth - 1 < n:
            raise StackError("Too Few Arguments")
        self.stack.pop()
        op(n)

    # -- angle mode boundary --------------------------------------------------

    def _to_rad(self, x: float) -> float:
        return math.radians(x) if self.angle_mode == "DEG" else x

    def _from_rad(self, x: float) -> float:
        return math.degrees(x) if self.angle_mode == "DEG" else x

    # -- unary functions --------------------------------------------------

    def _fn_sqrt(self, x: float) -> float:
        if x < 0:
            raise CalcError("Invalid Input")
        return math.sqrt(x)

    def _fn_sq(self, x: float) -> float:
        return x * x

    def _fn_inv(self, x: float) -> float:
        return self._fn_div(1.0, x)

    def _fn_ln(self, x: float) -> float:
        if x <= 0:
            raise CalcError("Invalid Input")
        return math.log(x)

    def _fn_exp(self, x: float) -> float:
        return math.exp(x)

    def _fn_log(self, x: float) -> float:
        if x <= 0:
            raise CalcError("Invalid Input")
        return math.log10(x)

    def _fn_alog(self, x: float) -> float:
        return 10.0**x

    def _fn_sin(self, x: float) -> float:
        return math.sin(self._to_rad(x))

    def _fn_cos(self, x: float) -> float:
        return math.cos(self._to_rad(x))

    def _fn_tan(self, x: float) -> float:
        # Not special-cased at 90 degrees/pi-2 radians: the input is a float
        # approximation of the angle, so tan never actually sees an exact
        # asymptote - it returns a large-but-finite number there, same as
        # the 50g's own floating point does. Documented, not "fixed".
        return math.tan(self._to_rad(x))

    def _fn_asin(self, x: float) -> float:
        if not -1 <= x <= 1:
            raise CalcError("Invalid Input")
        return self._from_rad(math.asin(x))

    def _fn_acos(self, x: float) -> float:
        if not -1 <= x <= 1:
            raise CalcError("Invalid Input")
        return self._from_rad(math.acos(x))

    def _fn_atan(self, x: float) -> float:
        return self._from_rad(math.atan(x))

    def _fn_abs(self, x: float) -> float:
        return abs(x)

    def _fn_neg(self, x: float) -> float:
        return -x

    # -- binary functions -------------------------------------------------

    def _fn_add(self, a: float, b: float) -> float:
        return a + b

    def _fn_sub(self, a: float, b: float) -> float:
        return a - b

    def _fn_mul(self, a: float, b: float) -> float:
        return a * b

    def _fn_div(self, a: float, b: float) -> float:
        if b == 0:
            raise CalcError("Undefined Result" if a == 0 else "Infinite Result")
        return a / b

    def _fn_xroot(self, value: float, degree: float) -> float:
        """XROOT: the `degree`-th root of `value`, level 2 rooted by level 1."""
        if degree == 0:
            raise CalcError("Infinite Result")
        if value < 0 and float(degree).is_integer() and int(degree) % 2 == 1:
            # Odd real roots of a negative are real; ** would go complex.
            return -((-value) ** (1.0 / degree))
        if value < 0:
            raise CalcError("Invalid Input")
        return value ** (1.0 / degree)

    def _fn_pow(self, a: float, b: float) -> float:
        # A negative base with a fractional exponent goes complex in Python;
        # _evaluate turns that into a domain error, since no complex value is
        # allowed onto the stack.
        return a**b

    def _fn_mod(self, a: float, b: float) -> float:
        # Judgment call: HP 50g's MOD has no published divide-by-zero wording
        # distinct from division's; reusing "Infinite Result"/"Undefined
        # Result" keeps the error vocabulary consistent across the engine.
        if b == 0:
            raise CalcError("Undefined Result" if a == 0 else "Infinite Result")
        return math.fmod(a, b)


def _parse_token(token: str) -> float:
    """Turn one entered token (already free of separating spaces) into a
    float, tolerating an entry left mid-typing (trailing '.', bare '-', or
    an EEX with no exponent digits yet).
    """
    sealed = token
    if sealed.endswith("E") or sealed.endswith("E-"):
        sealed = sealed.split("E")[0]  # incomplete exponent reads as none
    sealed = seal_number(sealed)
    value = parse_number(sealed)
    if value is None:
        # parse_number rejects non-finite results, so an entry that simply
        # overflowed lands here too - report that as overflow rather than as
        # malformed input, which is what "1E999" actually is.
        try:
            float(sealed)
        except ValueError:
            # The entry keys only ever produce digits/'.'/'-'/'E', so this
            # signals a bug in the entry-building logic rather than bad input.
            raise CalcError("Invalid Input") from None
        raise CalcError("Infinite Result") from None
    return value


def _toggle_sign_in_entry(text: str) -> str:
    """CHS mid-entry: flip the mantissa's sign, or the exponent's if the
    entry already has an EEX marker in it.
    """
    if "E" in text:
        mantissa, exponent = text.split("E", 1)
        exponent = exponent[1:] if exponent.startswith("-") else "-" + exponent
        return mantissa + "E" + exponent
    return text[1:] if text.startswith("-") else "-" + text
