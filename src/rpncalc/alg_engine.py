"""Algebraic (infix) calculator engine, direct port of omacalc's `Backend`.

Pure Python, no Qt import - this is the token machinery from `backend.cpp`
(`m_tokens`/`m_entry`/`m_result`/... and the `pressXxx` methods), kept
headless so it can be tested and later reused without dragging Qt in.
"""

from __future__ import annotations

import math

from .numeric import (
    DIVIDE_SIGN,
    MINUS_SIGN,
    MULTIPLY_SIGN,
    PLUS_SIGN,
    format_number,
    roundtrip,
    seal_number,
)

_OPERATORS = (PLUS_SIGN, MINUS_SIGN, MULTIPLY_SIGN, DIVIDE_SIGN)


def _is_operator(token: str) -> bool:
    return token in _OPERATORS


def _divide(numerator: float, denominator: float) -> float:
    """IEEE-754 division: ±inf or NaN on a zero denominator, never a raise."""
    if denominator == 0:
        if numerator == 0:
            return math.nan
        return math.inf if (numerator > 0) == (math.copysign(1.0, denominator) > 0) else -math.inf
    return numerator / denominator


def evaluate_tokens(tokens: list[str]) -> tuple[float, bool]:
    """Evaluate an odd-length number/operator/number/... token list.

    Returns `(value, ok)`. `ok` is False for a malformed token list, a
    non-numeric token, or a non-finite result (e.g. division by zero).
    """
    if len(tokens) % 2 == 0:
        return 0.0, False

    # First fold × and ÷ into their neighbors, then sum what remains, giving
    # multiplication its usual precedence over addition.
    values: list[float] = []
    additive_operators: list[str] = []

    try:
        values.append(float(tokens[0]))
    except ValueError:
        return 0.0, False

    i = 1
    while i + 1 < len(tokens):
        op = tokens[i]
        operand_text = tokens[i + 1]
        if not _is_operator(op):
            return 0.0, False
        try:
            operand = float(operand_text)
        except ValueError:
            return 0.0, False

        if op == MULTIPLY_SIGN:
            values[-1] *= operand
        elif op == DIVIDE_SIGN:
            # Python raises on float division by zero; C++ doubles produce
            # ±inf/NaN instead, which the non-finite guard below rejects.
            values[-1] = _divide(values[-1], operand)
        else:
            additive_operators.append(op)
            values.append(operand)
        i += 2

    total = values[0]
    for index, op in enumerate(additive_operators):
        if op == PLUS_SIGN:
            total += values[index + 1]
        else:
            total -= values[index + 1]

    if not math.isfinite(total):
        return 0.0, False

    return total, True


def pretty_expression(tokens: list[str]) -> str:
    """Render tokens for the expression line.

    Operand tokens carry full round-trip precision when they come from a
    chained result; present every number at display precision instead.
    """
    pretty = [
        token if _is_operator(token) else format_number(float(token))
        for token in tokens
    ]
    return " ".join(pretty)


class AlgEngine:
    """Port of omacalc's `Backend` token/entry state machine."""

    def __init__(self) -> None:
        self._tokens: list[str] = []
        self._entry: str = ""
        self._result: str = ""
        self._result_value: float = 0.0
        self._evaluated_expression: str = ""
        self._just_evaluated: bool = False
        self._errored: bool = False

    # -- Q_PROPERTY equivalents ------------------------------------------------

    @property
    def expression(self) -> str:
        if self._errored or self._just_evaluated:
            return self._evaluated_expression
        return pretty_expression(self._tokens)

    @property
    def display(self) -> str:
        if self._errored:
            return "Error"
        if self._entry:
            return self._entry
        if self._just_evaluated:
            return self._result
        return format_number(float(self.current_value()))

    # -- dispatch ---------------------------------------------------------------

    def press(self, key: str) -> None:
        """Port of `pressKey`: the single entry point for every key."""
        if len(key) == 1 and key.isdigit():
            self.press_digit(key)
        elif key == ".":
            self.press_decimal()
        elif key == "+":
            self.press_operator(PLUS_SIGN)
        elif key in ("-", MINUS_SIGN):
            self.press_operator(MINUS_SIGN)
        elif key in ("*", MULTIPLY_SIGN):
            self.press_operator(MULTIPLY_SIGN)
        elif key in ("/", DIVIDE_SIGN):
            self.press_operator(DIVIDE_SIGN)
        elif key == "=":
            self.press_equals()
        elif key == "%":
            self.press_percent()
        elif key == "sign":
            self.press_toggle_sign()
        elif key == "backspace":
            self.press_backspace()
        elif key == "clear":
            self.press_clear()
        else:
            return

    # -- key handlers -------------------------------------------------------

    def press_digit(self, digit: str) -> None:
        if self._errored:
            self.press_clear()
        if self._just_evaluated:
            # A digit after equals starts a new calculation rather than
            # appending to the result.
            self.press_clear()

        if self._entry == "0":
            self._entry = digit
            return
        if self._entry == "-0":
            self._entry = "-" + digit
            return

        # Fifteen significant digits is what the display format preserves;
        # letting the entry grow beyond that would silently round what was
        # typed. The zero in a leading "0." is not significant, so it does
        # not count.
        digits = sum(1 for character in self._entry if character.isdigit())
        if self._entry.startswith("0.") or self._entry.startswith("-0."):
            digits -= 1
        if digits < 15:
            self._entry += digit

    def press_decimal(self) -> None:
        if self._errored:
            self.press_clear()
        if self._just_evaluated:
            self.press_clear()

        if not self._entry:
            self._entry = "0."
        elif "." not in self._entry:
            self._entry += "."

    def press_operator(self, pretty: str) -> None:
        if self._errored:
            return

        if self._just_evaluated:
            # Chain from the exact result value, not its rounded display
            # text, so 1 ÷ 3 = × 3 comes back as 1. Seventeen significant
            # digits round-trip any double; the expression line re-rounds
            # them for presentation.
            self._tokens = [roundtrip(self._result_value)]
            self.clear_evaluation()

        if self._entry:
            self._tokens.append(seal_number(self._entry))
            self._tokens.append(pretty)
            self._entry = ""
        elif not self._tokens:
            self._tokens.append("0")
            self._tokens.append(pretty)
        elif _is_operator(self._tokens[-1]):
            self._tokens[-1] = pretty
        else:
            self._tokens.append(pretty)

    def press_equals(self) -> None:
        if self._errored or self._just_evaluated:
            return

        final_tokens = list(self._tokens)
        if self._entry:
            final_tokens.append(seal_number(self._entry))
        while final_tokens and _is_operator(final_tokens[-1]):
            final_tokens.pop()
        if not final_tokens:
            return

        self._evaluated_expression = pretty_expression(final_tokens)
        value, ok = evaluate_tokens(final_tokens)
        if not ok:
            self._errored = True
        else:
            self._result_value = value
            self._result = format_number(value)
            self._just_evaluated = True
        self._tokens = []
        self._entry = ""

    def press_percent(self) -> None:
        # iOS-style percent: with a pending + or −, x% means x percent of the
        # running total, so 200 + 10 % = gives 220. With × or ÷ (or on its
        # own) x% is simply x ÷ 100, so 200 × 10 % = gives 20.
        if self._errored:
            return

        if self._just_evaluated:
            percent = self._result_value / 100.0
            self.clear_evaluation()
            self._entry = format_number(percent)
            return

        try:
            value = float(self.current_value())
        except ValueError:
            return

        percent = value / 100.0
        if self._tokens and self._tokens[-1] in (PLUS_SIGN, MINUS_SIGN):
            left_side = self._tokens[:-1]
            base, base_ok = evaluate_tokens(left_side)
            if base_ok:
                percent = base * value / 100.0
        self._entry = format_number(percent)

    def press_toggle_sign(self) -> None:
        if self._errored:
            return
        if self._just_evaluated:
            self.begin_editing_after_result()

        # With nothing typed yet, start a fresh negative operand instead of
        # dredging up the previous one: 4 + ± 2 enters -2, not -42.
        if not self._entry:
            self._entry = "-0"
            return

        if self._entry.startswith("-"):
            self._entry = self._entry[1:]
        else:
            self._entry = "-" + self._entry

    def press_backspace(self) -> None:
        if self._errored:
            self.press_clear()
            return
        if self._just_evaluated:
            self.begin_editing_after_result()

        self._entry = self._entry[:-1]
        if self._entry == "-":
            self._entry = ""

    def press_clear(self) -> None:
        self._tokens = []
        self._entry = ""
        self.clear_evaluation()
        self._errored = False

    def paste_value(self, value: float) -> None:
        """Adopt an externally-parsed number (clipboard paste) as a fresh
        entry, the same way a pasted number behaves like any other typed
        entry in omacalc. Clipboard access itself belongs to `backend.py`;
        this only owns what happens once a value is in hand.
        """
        if self._errored or self._just_evaluated:
            self.press_clear()
        self._entry = format_number(value)

    # -- helpers --------------------------------------------------------------

    def current_value(self) -> str:
        """The number the calculator is "at" right now: the entry being
        typed, or the operand the last operator was applied to, or the
        fresh-start zero.
        """
        if self._entry:
            return seal_number(self._entry)
        for token in reversed(self._tokens):
            if not _is_operator(token):
                return token
        return "0"

    def begin_editing_after_result(self) -> None:
        # Editing after equals picks up from the result's displayed digits,
        # with the old expression cleared away so the new one grows from
        # "42" rather than "42 × 3 + 7".
        self._entry = self._result
        self._tokens = []
        self.clear_evaluation()

    def clear_evaluation(self) -> None:
        self._result = ""
        self._result_value = 0.0
        self._evaluated_expression = ""
        self._just_evaluated = False
