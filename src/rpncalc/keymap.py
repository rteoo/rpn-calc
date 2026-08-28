"""The calculator faceplate as data, plus its shift state machine.

The layout is our own: a single yellow shift plane (HP 12C-style finance keys
on the face, with a FINANCE screen for the 50g TVM form). Left/right legend
slots are placement only — both fire when shift is armed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Shift legends and the shift keycap: yellow, matching the outline face.
# CalcButton carries the same value as its own default; nothing else reads it.
SHIFT_COLOR = "#f0c419"


class Shift(Enum):
    NONE = "none"
    # Single plane. The value stays "right" so existing QML `armedShift === "right"`
    # bindings keep working without a rename sweep.
    RIGHT = "right"


@dataclass(frozen=True)
class Key:
    """One physical key and its unshifted / shifted planes."""

    key_id: str
    label: str
    action: str | None = None
    left_label: str = ""
    left_action: str | None = None
    right_label: str = ""
    right_action: str | None = None
    style: str = "normal"  # normal | operator | enter | shift_right | nav
    span: int = 1

    def action_for(self, shift: Shift) -> str | None:
        if shift is Shift.NONE:
            return self.action
        # One shift plane; left_/right_ slots are legend placement only.
        if self.right_action is not None:
            return self.right_action
        return self.left_action

    def is_live(self) -> bool:
        return any((self.action, self.left_action, self.right_action))


def _k(*args, **kwargs) -> Key:
    return Key(*args, **kwargs)


# Eight rows. The bottom row is ON / 0 / . / ENTER(×2). Shift legends sit in
# the left_ or right_ slot purely for where they are drawn above the cap.
KEY_ROWS: tuple[tuple[Key, ...], ...] = (
    (
        _k("menu", "MENU", "settings"),
        _k("up", "", "up", right_label="FINANCE", right_action="finance", style="nav"),
        _k("down", "", "down", right_label="CUT", right_action="cut", style="nav"),
        _k("left", "", "left", right_label="COPY", right_action="copy", style="nav"),
        _k("right", "", "right", right_label="PASTE", right_action="paste", style="nav"),
    ),
    (
        _k("undo", "UNDO", "undo", left_label="PASTE", left_action="paste"),
        _k("eex", "EEX", "eex", right_label="10<sup>x</sup>", right_action="alog"),
        _k("n", "n", "fin_n", right_label="Nj", right_action="fin_nj"),
        _k("i", "i", "fin_i", right_label="IRR", right_action="fin_irr"),
        _k("backspace", "\u2190", "backspace", right_label="CLEAR", right_action="clear"),
    ),
    (
        _k("sqrt", "\u221ax", "sqrt", left_label="y\u221ax", left_action="xroot"),
        _k("pow", "y<sup>x</sup>", "pow", left_label="e<sup>x</sup>", left_action="exp"),
        _k("pv", "PV", "fin_pv", right_label="NPV", right_action="fin_npv"),
        _k("pmt", "PMT", "fin_pmt", right_label="CFo", right_action="fin_cfo"),
        _k("fv", "FV", "fin_fv", right_label="CFj", right_action="fin_cfj"),
    ),
    (
        _k("log", "log x", "log", left_label="ln x", left_action="ln"),
        _k("sq", "x\u00b2", "sq", left_label="e", left_action="e"),
        _k("chs", "+/\u2212", "chs", left_label="\u03c0", left_action="pi"),
        _k("inv", "1/X", "inv", left_label="x!", left_action="fact"),
        _k("divide", "\u00f7", "/", left_label="STD", left_action="stddev",
           style="operator"),
    ),
    (
        _k("sum", "\u03a3+", "sum_plus", left_label="Σ−",
           left_action="sigma_minus"),
        _k("7", "7", "7"),
        _k("8", "8", "8"),
        _k("9", "9", "9"),
        _k("multiply", "\u00d7", "*", left_label="MED", left_action="median",
           style="operator"),
    ),
    (
        _k("percent", "%", "percent", left_label="\u0394%", left_action="delta_percent"),
        _k("4", "4", "4"),
        _k("5", "5", "5"),
        _k("6", "6", "6"),
        _k("minus", "\u2212", "-", left_label="MEAN", left_action="mean",
           style="operator"),
    ),
    (
        _k("shift", "", "shift", style="shift_right"),
        _k("1", "1", "1"),
        _k("2", "2", "2"),
        _k("3", "3", "3"),
        _k("plus", "+", "+", left_label="Σ", left_action="sigma_sum",
           style="operator"),
    ),
    (
        _k("on", "ON", "clear_entry", right_label="CLΣ",
           right_action="clear_sigma"),
        _k("0", "0", "0"),
        _k("dot", ".", "."),
        _k("enter", "ENTER", "enter", style="enter", span=2),
    ),
)

KEYS_BY_ID: dict[str, Key] = {k.key_id: k for row in KEY_ROWS for k in row}


class ShiftState:
    """One-shot shift: arm, spend on the next key, or cancel with a second press."""

    def __init__(self) -> None:
        self._shift = Shift.NONE

    @property
    def shift(self) -> Shift:
        return self._shift

    def press_shift(self) -> Shift:
        self._shift = Shift.NONE if self._shift is Shift.RIGHT else Shift.RIGHT
        return self._shift

    def consume(self) -> Shift:
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

    if key.action == "shift" or key.style == "shift_right":
        state.press_shift()
        return None

    return key.action_for(state.consume())
