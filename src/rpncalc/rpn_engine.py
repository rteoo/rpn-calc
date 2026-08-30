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

from .finance import FinanceError, FinanceMemory
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

_ARROWS = frozenset({"up", "down", "left", "right"})


def _mean(values: list[float]) -> float:
    try:
        return math.fsum(values) / len(values)
    except OverflowError:
        # Only scale after fsum overflows, preserving its ordinary rounding
        # for the usual path while keeping a representable mean finite.
        scale = max(abs(value) for value in values)
        return scale * (math.fsum(value / scale for value in values) / len(values))


def _median(values: list[float]) -> float:
    """The middle value; the mean of the two middles for an even sample.

    The two middles are averaged directly, and only halved separately when
    that sum overflows. Both halves of that are load-bearing: `(a + b) / 2`
    goes infinite for middles near the float ceiling, reporting "Infinite
    Result" for a median that is simply one of the numbers entered - while
    `a/2 + b/2` underflows to 0.0 for two copies of `5e-324`, the smallest
    denormal, where the median is that same number. A property test found the
    second case within minutes of the first being fixed the naive way.
    """
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    low, high = ordered[middle - 1], ordered[middle]
    total = low + high
    if math.isinf(total):
        return low / 2.0 + high / 2.0
    return total / 2.0


def _stddev(values: list[float]) -> float:
    """Sample standard deviation, n-1, by the corrected two-pass algorithm.

    Not the textbook `Σx² - n·x̄²`: that subtracts two enormous nearly-equal
    numbers, and for `1e9, 1e9+1, 1e9+2` - spread exactly 1 - it returns 0.0.

    Subtracting the mean first fixes that, but not completely. The mean of a
    tight cluster far from zero is not representable, and the leftover bias
    rides into every deviation; a property test found `733007751635` twice
    and `…634` once, where plain two-pass drifts in the ninth digit. The
    `- fsum(deviations)²/n` term cancels exactly that bias, which is why this
    agrees with `statistics.stdev` - exact rational arithmetic - to the last
    bit on the cases that break the other two forms.
    """
    average = _mean(values)
    deviations = [value - average for value in values]
    n = len(values)
    corrected = math.fsum(d * d for d in deviations) - math.fsum(deviations) ** 2 / n
    # Cauchy-Schwarz says this cannot be negative, and 300k adversarial
    # samples never made it so; the clamp is here because the alternative to a
    # rounding artefact would be `Invalid Input` on a sample whose spread is
    # simply zero, and a max() is cheaper than being wrong about that.
    return math.sqrt(max(corrected, 0.0) / (n - 1))


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
        "fact": "_fn_fact",
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
        "delta_percent": "_fn_delta_percent",
    }
    _FINANCE_COMMANDS = frozenset({
        "fin_n", "fin_i", "fin_pv", "fin_pmt", "fin_fv",
        "fin_nj", "fin_irr", "fin_npv", "fin_cfo", "fin_cfj",
    })
    # Fields the 50g FINANCE screen cursor walks, in display order.
    _FINANCE_FIELDS = ("n", "i_yr", "pv", "pmt", "fv", "pyr", "begin")
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
        self.finance = FinanceMemory()
        # Index into `_FINANCE_FIELDS` while the FINANCE screen is open.
        self.finance_cursor = 0
        # Set when digits (or a paste) put a value ready for a 12C register
        # store; cleared by operators and by the store/solve itself.
        self._finance_store_pending = False
        # Every accumulated (x, y) pair, not running totals. MEDIAN needs the
        # individual points - no set of sums can produce one - and keeping them
        # also lets STD take a two-pass mean-first route instead of the
        # Σx² - n·x̄² form, which loses most of its digits to cancellation on
        # data far from zero. Snapshotted with the stack, so UNDO takes a Σ+
        # back whole.
        self._stats: list[tuple[float, float]] = []
        self._undo_stats: list[tuple[float, float]] = []

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
                       "clear", "clear_entry", "undo", "pi", "e", "sum_plus",
                       "mean", "sigma_sum", "sigma_minus", "median",
                       "stddev", "clear_sigma")
            or key in self._UNARY_METHODS
            or key in self._BINARY_METHODS
            or key in self._STACK_COMMANDS
            or key in self._FINANCE_COMMANDS
            or key in _INTERACTIVE_COMMANDS
            or key in _ARROWS
        )

    def press(self, key_id: str) -> None:
        key = _NORMALIZE.get(key_id, key_id)
        # "Errors ... clear the message on the next keypress" - every press
        # gets a clean slate before it does anything else.
        self.error = None
        try:
            self._dispatch(key)
        except (StackError, CalcError, FinanceError) as exc:
            self.error = str(exc)
        except (OverflowError, ZeroDivisionError):
            self.error = "Infinite Result"

    def _dispatch(self, key: str) -> None:
        if not self.knows(key):
            return  # an unbound key is a no-op, never a crash
        if key in _ARROWS:
            resolved = self._resolve_arrow(key)
            if resolved is None:
                return
            # The arrow resolved to an ordinary stack command; let it take the
            # usual route so it commits an open command line first, like every
            # other command does.
            key = resolved
        if self.cursor_level is not None:
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
        elif key in self._FINANCE_COMMANDS:
            store = self.command_line is not None or self._finance_store_pending
            self._mark_undo()
            self._commit_entry()
            self._apply_finance(key, store=store)
            self._finance_store_pending = False
        else:
            # Every operator, function, and stack command: implicit ENTER of
            # any open command line first, then apply. This is the one rule
            # that makes "3 SPC 4 +" and "clicking [+] mid-entry" both work.
            # Recorded before the commit, not after the command: a command
            # that errors has still entered the command line onto the stack,
            # and UNDO has to take that back too.
            self._mark_undo()
            self._commit_entry()
            self._finance_store_pending = False
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

    def _resolve_arrow(self, key: str) -> str | None:
        """What an arrow means right now.

        Returns a stack command to run, or None when the arrow has already done
        its job (moving the browser cursor) or means nothing here.

        Outside the browser the horizontal arrows are stack commands - the right
        arrow swaps levels 1 and 2 on a real 50g, confirmed frame by frame
        against a recording of one. Inside the browser they are not used: the
        cursor moves vertically and the soft menu does the work.
        """
        if self.cursor_level is not None:
            if key == "up":
                self.cursor_level = min(self.cursor_level + 1, self.stack.depth)
            elif key == "down":
                # Stepping below level 1 leaves the browser, which is the
                # quickest way out and mirrors how the cursor got in.
                self.cursor_level = None if self.cursor_level == 1 else self.cursor_level - 1
            return None

        if key == "up":
            # Up opens the browser on level 1, as pressing it on the 50g does.
            # An empty stack has nothing to browse.
            if self.stack.depth >= 1:
                self.cursor_level = 1
            return None
        if key == "down":
            return None
        return "rot" if key == "left" else "swap"

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
        self._mark_undo()
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
        self._mark_undo()
        value = self.stack.peek(level)
        self.stack.roll(level)  # bring it to level 1 so it can be dropped
        self.stack.drop()
        self.command_line = format_number(value, self.number_format)
        self.cursor_level = None

    def _interactive_drop(self) -> None:
        level = self.cursor_level
        assert level is not None
        self._mark_undo()
        self.stack.roll(level)
        self.stack.drop()
        # Browsing a stack that no longer has levels makes no sense.
        self.cursor_level = min(level, self.stack.depth) or None

    # -- command-line editing ------------------------------------------------

    def _handle_entry_key(self, key: str) -> None:
        self._finance_store_pending = True
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
            self._finance_store_pending = True
        else:
            self.stack.dup()  # ENTER on an empty command line: DUP level 1
        self._mark_undo(snapshot)

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
        self._mark_undo(snapshot)

    def _handle_chs(self) -> None:
        if self.command_line is not None:
            self.command_line = _toggle_sign_in_entry(self.command_line)
            return
        snapshot = self.stack.to_list()
        self._apply_unary(self._fn_neg)  # CHS on an empty command line: NEG level 1
        self._mark_undo(snapshot)

    def _handle_clear(self) -> None:
        """CLEAR empties the stack, as right-shift CLEAR does on the 50g."""
        self._mark_undo()
        self.command_line = None
        self._finance_store_pending = False
        self.stack.clear()

    def _handle_clear_entry(self) -> None:
        """CANCEL/DEL: abandon what is being typed, leave the stack alone."""
        self.command_line = None
        self._finance_store_pending = False

    def _mark_undo(self, snapshot: list[float] | None = None) -> None:
        """Record what one UNDO steps back to: the stack and the Σ registers.

        Every snapshot point goes through here so the two cannot drift apart -
        a Σ+ undone after an unrelated ENTER used to restore the stack while
        leaving the accumulated totals ahead of it.
        """
        self._undo_snapshot = self.stack.to_list() if snapshot is None else snapshot
        self._undo_stats = list(self._stats)

    def _handle_undo(self) -> None:
        if self._undo_snapshot is None:
            return
        self.stack.clear()
        for value in reversed(self._undo_snapshot):  # to_list() is level-1-first
            self.stack.push(value)
        self._stats = list(self._undo_stats)
        self._undo_snapshot = None  # single-level UNDO, like the 50g's UNDO key
        self._finance_store_pending = False

    def paste_value(self, value: float) -> None:
        """Adopt a pasted number as a new level 1, as if it had been entered."""
        if not math.isfinite(value):
            raise CalcError("Infinite Result")
        self._mark_undo()
        self.command_line = None
        self.stack.push(value)
        self._finance_store_pending = True

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

    def finance_move(self, direction: str) -> None:
        """Move the FINANCE screen cursor; wraps at both ends."""
        self.error = None
        n = len(self._FINANCE_FIELDS)
        if direction == "up":
            self.finance_cursor = (self.finance_cursor - 1) % n
        elif direction == "down":
            self.finance_cursor = (self.finance_cursor + 1) % n

    def clear_finance(self) -> None:
        """CLEAR on the FINANCE screen: empty the registers.

        P/YR and Begin/End survive. They are how the form is configured rather
        than data entered into it - the same line a 50g draws between its TVM
        variables and the payment mode - and clearing the numbers is no reason
        to forget that the problem is monthly and paid at the end.
        """
        self.error = None
        self.command_line = None
        self.finance.n = 0.0
        self.finance.i = 0.0
        self.finance.pv = 0.0
        self.finance.pmt = 0.0
        self.finance.fv = 0.0
        self.finance.clear_cash_flows()

    def commit_finance_entry(self) -> None:
        """ENTER on the FINANCE screen: what was typed goes into the field.

        The form reuses the ordinary command line for entry, so digits, `.`,
        EEX, CHS and backspace all behave exactly as they do on the stack -
        the only difference is where ENTER puts the result. On the Begin/End
        row there is nothing to type, so ENTER toggles it instead.
        """
        self.error = None
        field = self._FINANCE_FIELDS[self.finance_cursor]
        if field == "begin":
            self.finance.begin = not self.finance.begin
            self.command_line = None
            return
        if self.command_line is None:
            return
        value = parse_number(self.command_line)
        self.command_line = None
        if value is None:
            self.error = "Invalid Input"
            return
        try:
            self._store_finance_field(field, value)
        except FinanceError as exc:
            self.error = str(exc)

    def finance_menu(self, index: int) -> None:
        """Soft keys on the FINANCE screen: EDIT / AMOR / SOLVE."""
        self.error = None
        try:
            field = self._FINANCE_FIELDS[self.finance_cursor]
            if index == 0:  # EDIT — pull level 1 into the selected register
                if field == "begin":
                    self.finance.begin = not self.finance.begin
                    return
                if self.stack.depth < 1:
                    raise StackError("Too Few Arguments")
                self._store_finance_field(field, self.stack.peek(1))
            elif index == 2:  # SOLVE
                if field == "begin":
                    self.finance.begin = not self.finance.begin
                    return
                if field == "pyr":
                    return
                self.stack.push(self._solve_finance_field(field))
            # index 1 AMOR is intentionally inert (dimmed in the UI)
        except (StackError, CalcError, FinanceError) as exc:
            self.error = str(exc)
        except (OverflowError, ZeroDivisionError):
            self.error = "Infinite Result"

    def _store_finance_field(self, field: str, value: float) -> None:
        if field == "n":
            self.finance.n = value
        elif field == "i_yr":
            self.finance.i_yr = value
        elif field == "pv":
            self.finance.pv = value
        elif field == "pmt":
            self.finance.pmt = value
        elif field == "fv":
            self.finance.fv = value
        elif field == "pyr":
            if value == 0:
                raise FinanceError("Compound Interest Error")
            self.finance.pyr = value

    def _solve_finance_field(self, field: str) -> float:
        if field == "n":
            return self.finance.solve_n()
        if field == "i_yr":
            self.finance.solve_i()
            return self.finance.i_yr
        if field == "pv":
            return self.finance.solve_pv()
        if field == "pmt":
            return self.finance.solve_pmt()
        if field == "fv":
            return self.finance.solve_fv()
        raise FinanceError("Compound Interest Error")

    def _apply_finance(self, key: str, *, store: bool) -> None:
        """12C-style register keys: store after a fresh entry, else solve."""
        store_keys = {
            "fin_n": "n", "fin_i": "i", "fin_pv": "pv",
            "fin_pmt": "pmt", "fin_fv": "fv",
        }
        if key in store_keys:
            name = store_keys[key]
            if store:
                if self.stack.depth < 1:
                    raise StackError("Too Few Arguments")
                setattr(self.finance, name, self.stack.peek(1))
            else:
                solver = getattr(self.finance, f"solve_{name}")
                self.stack.push(solver())
            return
        if key == "fin_cfo":
            if self.stack.depth < 1:
                raise StackError("Too Few Arguments")
            self.finance.set_cfo(self.stack.peek(1))
            return
        if key == "fin_cfj":
            if self.stack.depth < 1:
                raise StackError("Too Few Arguments")
            self.finance.add_cfj(self.stack.peek(1))
            return
        if key == "fin_nj":
            if self.stack.depth < 1:
                raise StackError("Too Few Arguments")
            times = self.stack.peek(1)
            if not times.is_integer():
                raise FinanceError("Nj must be between 1 and 99")
            self.finance.set_nj(int(times))
            return
        if key == "fin_npv":
            self.stack.push(self.finance.npv())
            return
        if key == "fin_irr":
            self.stack.push(self.finance.irr())
            return
        raise ValueError(f"unknown finance key: {key!r}")

    def _apply_command(self, key: str) -> None:
        if key in self._UNARY_METHODS:
            self._apply_unary(getattr(self, self._UNARY_METHODS[key]))
        elif key in self._BINARY_METHODS:
            self._apply_binary(getattr(self, self._BINARY_METHODS[key]))
        elif key == "pi":
            self.stack.push(math.pi)
        elif key == "e":
            self.stack.push(math.e)
        elif key == "sum_plus":
            self._fn_sum_plus()
        elif key == "mean":
            self._fn_mean()
        elif key == "sigma_sum":
            self._fn_sigma_sum()
        elif key == "sigma_minus":
            self._fn_sigma_minus()
        elif key == "median":
            self._fn_median()
        elif key == "stddev":
            self._fn_stddev()
        elif key == "clear_sigma":
            self._clear_stats()
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

    def _fn_delta_percent(self, y: float, x: float) -> float:
        """12C Δ%: percent change from y to x."""
        if y == 0:
            raise CalcError("Infinite Result")
        return (x - y) / y * 100.0

    def _fn_fact(self, x: float) -> float:
        if x < 0 or not float(x).is_integer() or x > 170:
            raise CalcError("Invalid Input")
        return float(math.factorial(int(x)))

    def _fn_sum_plus(self) -> None:
        """Σ+: accumulate one (y, x) pair, leaving n in level 1.

        12C semantics: x is read from level 1 and y from level 2, but only
        level 1 is consumed - the y value survives for the next pair, exactly
        as the 12C's Y register does. A one-variable sample, with nothing in
        level 2, accumulates y = 0 the way a 12C's zeroed Y register would.
        """
        self._stats.append(self._read_pair())
        self.stack.pop()
        self.stack.push(float(len(self._stats)))

    def _fn_sigma_minus(self) -> None:
        """Σ-: take one accumulated pair back out, leaving n in level 1.

        The 12C's correction key: key the wrong entry in again and press Σ-.
        Reading (y, x) exactly as Σ+ does means the same keystrokes undo the
        same point. Unlike a 12C, which subtracts from its sums whether or not
        the pair was ever added, this refuses a pair it never saw - the totals
        cannot be driven somewhere no data could put them.
        """
        pair = self._read_pair()
        if pair not in self._stats:
            raise CalcError("Statistics Error")
        self._stats.remove(pair)
        self.stack.pop()
        self.stack.push(float(len(self._stats)))

    def _read_pair(self) -> tuple[float, float]:
        """The (x, y) Σ+ and Σ- both read off the stack."""
        if self.stack.depth < 1:
            raise StackError("Too Few Arguments")
        x = self.stack.peek(1)
        y = self.stack.peek(2) if self.stack.depth >= 2 else 0.0
        return (x, y)

    def _stats_columns(self, *, minimum: int) -> tuple[list[float], list[float]]:
        """The x and y samples, refusing a question too small to answer."""
        if len(self._stats) < minimum:
            raise CalcError("Statistics Error")
        return [x for x, _ in self._stats], [y for _, y in self._stats]

    def _push_readback(self, summarise, xs: list[float], ys: list[float]) -> None:
        """Every statistics readback lands the same way: x in 1, y in 2.

        Routed through `_evaluate` for the same reason the unary and binary
        functions are: a sample of values near the float ceiling overflows
        while being summarised, and an OverflowError out of here is not one of
        the exceptions `press` catches - it would take the window down rather
        than show "Infinite Result".
        """
        x_value = self._evaluate(summarise, xs)
        y_value = self._evaluate(summarise, ys)
        self.stack.push(y_value)
        self.stack.push(x_value)

    def _fn_sigma_sum(self) -> None:
        """Σ: Σx into level 1, Σy into level 2, as the 12C's RCL Σ+ leaves them.

        The reason the accumulator exists. MEAN is Σ divided by n, not the
        other way round, so this is the more basic of the two readbacks.
        """
        xs, ys = self._stats_columns(minimum=1)
        self._push_readback(math.fsum, xs, ys)

    def _fn_mean(self) -> None:
        """MEAN: x̄ into level 1, ȳ into level 2, as the 12C's x̄ leaves them."""
        xs, ys = self._stats_columns(minimum=1)
        self._push_readback(_mean, xs, ys)

    def _fn_median(self) -> None:
        """MEDIAN: the middle value of each column, averaging the two middles
        of an even-sized sample. Needs the points themselves, which is why the
        accumulator keeps them rather than running totals."""
        xs, ys = self._stats_columns(minimum=1)
        self._push_readback(_median, xs, ys)

    def _fn_stddev(self) -> None:
        """STD: the sample standard deviation, dividing by n-1 as the 12C does.

        One point has no spread to report - the n-1 denominator is zero - so
        this asks for two, where MEAN and MEDIAN are happy with one.
        """
        xs, ys = self._stats_columns(minimum=2)
        self._push_readback(_stddev, xs, ys)

    def _clear_stats(self) -> None:
        """CLΣ: forget every accumulated pair. The stack is not touched."""
        self._stats.clear()

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

    def _fn_xroot(self, degree: float, value: float) -> float:
        """`y√x`: the level-2-th root of level 1 - index in y, radicand in x.

        The operand order is the label's, read left to right, which is how
        `y^x` on the same face already reads: y is level 2, x is level 1. A
        real 50g's XROOT takes them the other way round (radicand in level 2,
        index in level 1), and its `ⁿ√y` legend spells the stack backwards.
        Matching the label was worth breaking with the 50g here.
        """
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
