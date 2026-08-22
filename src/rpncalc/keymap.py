"""The HP 50g lower keyboard as data, plus its shift state machine.

Grid geometry comes from the Emu48 faceplate descriptor (`50G.kml`); the shift
legends are transcribed from the faceplate bitmap itself, not from memory. On
the 50g the left shift is white and the right shift is orange - the purple/green
pairing belongs to the older 48 series.

Keys the calculator cannot honour yet (symbolic algebra, the CAS, soft menus)
keep their real legend but carry no action, so the face stays honest rather than
pretending a key works.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# Faceplate legend colors, sampled from 50G.bmp.
LEFT_SHIFT_COLOR = "#f2f2f2"
RIGHT_SHIFT_COLOR = "#e08a2e"
ALPHA_COLOR = "#f0c419"


class Shift(Enum):
    NONE = "none"
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True)
class Key:
    """One physical key and its three planes."""

    key_id: str
    label: str
    action: str | None = None
    left_label: str = ""
    left_action: str | None = None
    right_label: str = ""
    right_action: str | None = None
    alpha: str = ""
    style: str = "normal"  # normal | operator | enter | shift_left | shift_right | alpha

    def action_for(self, shift: Shift) -> str | None:
        if shift is Shift.LEFT:
            return self.left_action
        if shift is Shift.RIGHT:
            return self.right_action
        return self.action

    def is_live(self) -> bool:
        return any((self.action, self.left_action, self.right_action))


def _k(*args, **kwargs) -> Key:
    return Key(*args, **kwargs)


# The navigation row leads (the 50g keeps these as a cluster beside APPS/MODE/
# TOOL, none of which are on this face); then the faceplate rows top to bottom,
# matching 50G.kml y-offsets 347/385/422/459/500/541/582.
#
# Two deliberate deviations from the real 50g, both forced by having no soft
# menus: the X key (no symbolic variables here) carries the stack commands the
# 50g keeps in its STACK menu, and left-shift DEL clears the command line rather
# than editing text. Everything else is the genuine layout.
KEY_ROWS: tuple[tuple[Key, ...], ...] = (
    (
        _k("stk", "STK", "up", "", None, "", None, style="nav"),
        _k("up", "", "up", "", None, "", None, style="nav"),
        _k("down", "", "down", "", None, "", None, style="nav"),
        _k("left", "", "left", "", None, "", None, style="nav"),
        _k("right", "", "right", "", None, "", None, style="nav"),
    ),
    (
        _k("hist", "HIST", None, "CMD", None, "UNDO", "undo", alpha="M"),
        _k("eval", "EVAL", None, "PRG", None, "CHARS", None, alpha="N"),
        _k("quote", "'", None, "MTRW", None, "EQW", None, alpha="O"),
        _k("symb", "SYMB", None, "MTH", None, "CAT", None, alpha="P"),
        _k("backspace", "\u2190", "backspace", "DEL", "clear_entry", "CLEAR", "clear"),
    ),
    (
        _k("pow", "Y^x", "pow", "e^x", "exp", "LN", "ln", alpha="Q"),
        _k("sqrt", "\u221ax", "sqrt", "x\u00b2", "sq", "\u207f\u221ay", "xroot", alpha="R"),
        _k("sin", "SIN", "sin", "ASIN", "asin", "\u03a3", None, alpha="S"),
        _k("cos", "COS", "cos", "ACOS", "acos", "\u2202", None, alpha="T"),
        _k("tan", "TAN", "tan", "ATAN", "atan", "\u222b", None, alpha="U"),
    ),
    (
        _k("eex", "EEX", "eex", "10^x", "alog", "LOG", "log", alpha="V"),
        _k("chs", "+/\u2212", "chs", "\u2260", None, "=", None, alpha="W"),
        _k("stack", "SWAP", "swap", "ROT", "rot", "OVER", "over", alpha="X"),
        _k("inv", "1/X", "inv", "\u2265", None, ">", None, alpha="Y"),
        _k("divide", "\u00f7", "/", "ABS", "abs", "ARG", None, alpha="Z", style="operator"),
    ),
    (
        _k("alpha", "ALPHA", None, "USER", None, "ENTRY", None, style="alpha"),
        _k("7", "7", "7", "S.SLV", None, "NUM.SLV", None),
        _k("8", "8", "8", "EXP&LN", None, "TRIG", None),
        _k("9", "9", "9", "FINANCE", None, "TIME", None),
        _k("multiply", "\u00d7", "*", "[ ]", None, '" "', None, style="operator"),
    ),
    (
        _k("shift_left", "\u21e6", "shift_left", style="shift_left"),
        _k("4", "4", "4", "CALC", None, "ALG", None),
        _k("5", "5", "5", "MATRICES", None, "STAT", None),
        _k("6", "6", "6", "CONVERT", None, "UNITS", None),
        _k("minus", "\u2212", "-", "( )", None, "_", None, style="operator"),
    ),
    (
        _k("shift_right", "\u21e8", "shift_right", style="shift_right"),
        _k("1", "1", "1", "ARITH", None, "CMPLX", None),
        _k("2", "2", "2", "DEF", None, "LIB", None),
        _k("3", "3", "3", "#", None, "BASE", None),
        _k("plus", "+", "+", "{ }", None, "\u00ab \u00bb", None, style="operator"),
    ),
    (
        _k("on", "ON", "clear_entry", "CONT", None, "OFF", None),
        _k("0", "0", "0", "\u221e", None, "\u2192", None),
        _k("dot", ".", ".", "::", None, "\u21b5", None),
        _k("spc", "SPC", "spc", "\u03c0", "pi", ",", None),
        _k("enter", "ENTER", "enter", "ANS", None, "\u2192NUM", None, style="enter"),
    ),
)

KEYS_BY_ID: dict[str, Key] = {k.key_id: k for row in KEY_ROWS for k in row}


class ShiftState:
    """The 50g's one-shot shift.

    Pressing a shift arms it for exactly the next key. Pressing the same shift
    again cancels it; pressing the opposite one switches planes.
    """

    def __init__(self) -> None:
        self._shift = Shift.NONE

    @property
    def shift(self) -> Shift:
        return self._shift

    def press_shift(self, which: Shift) -> Shift:
        self._shift = Shift.NONE if self._shift is which else which
        return self._shift

    def consume(self) -> Shift:
        """Take the armed plane and disarm."""
        armed, self._shift = self._shift, Shift.NONE
        return armed

    def clear(self) -> None:
        self._shift = Shift.NONE


def resolve(key_id: str, state: ShiftState) -> str | None:
    """Translate a physical key press into a command, consuming any armed shift.

    Returns None for a key with nothing bound in the active plane; the shift is
    still consumed, matching the calculator's behaviour of spending a shift on
    whatever you press next.
    """
    key = KEYS_BY_ID.get(key_id)
    if key is None:
        return None

    if key.action == "shift_left":
        state.press_shift(Shift.LEFT)
        return None
    if key.action == "shift_right":
        state.press_shift(Shift.RIGHT)
        return None

    return key.action_for(state.consume())
