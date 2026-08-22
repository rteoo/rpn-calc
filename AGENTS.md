# rpn-calc — agent contract

An HP 50g-style RPN calculator wearing [omacalc](https://github.com/omacom-io/omacalc)'s
face. RPN is the default input method; algebraic mode is retained behind a toggle, as on
the real 50g under `MODE`.

## Stack

Python 3.10+ with PySide6 (Qt 6 Quick). No compiler, no qmake, no `.qrc` — QML and fonts
load from the filesystem relative to `src/rpncalc/__file__`.

This is a **port** of omacalc, not a fork: upstream is Qt 6 / C++ targeting Omarchy, and
there is no merging back. The QML face and the algebraic engine's behaviour came across;
the C++ did not.

## Commands

```sh
.venv/Scripts/pip install -e ".[dev]"   # Windows; use .venv/bin on Linux
python -m rpncalc                        # run
pytest                                   # full suite, headless
```

`pytest` needs no display: everything below `backend.py` is pure Python, and
`tests/test_backend_keys.py` forces `QT_QPA_PLATFORM=offscreen` and redirects `QSettings`
to a temp directory.

## Layout

| File | Role |
|---|---|
| `numeric.py` | Number formatting/parsing. STD is omacalc's `%.15g`; FIX/SCI/ENG are the 50g's. |
| `stack.py` | `RpnStack` — index 0 is level 1, unbounded. |
| `rpn_engine.py` | The command line, dispatch, and the scientific functions. |
| `alg_engine.py` | Port of omacalc's infix token machinery. |
| `keymap.py` | The faceplate as data, plus the shift state machine. |
| `backend.py` | The **only** Qt-aware engine file; the QML context property `backend`. |
| `systemtheme.py` | Windows dark mode / text scale; Omarchy `colors.toml` reader kept. |
| `qml/` | `Main.qml`, `CalcButton.qml`, `RpnStackView.qml`, `StatusBar.qml`. |

Keep the engine layer free of Qt imports. That split is upstream's too — omacalc's
`tests.pro` compiles `backend.cpp` without `systemtheme.cpp` for the same reason.

## RPN semantics that must not regress

The command-line-open vs command-line-empty distinction is the whole design:

| Input | Line open | Line empty |
|---|---|---|
| digit / `.` / `EEX` | append | open a new line |
| `ENTER` | parse and push (space-separated pushes each) | **DUP level 1** |
| operator or function | **implicit ENTER first**, then apply | apply to the stack |
| `←` | delete a character | **DROP level 1** |
| `+/−` | flip the mantissa's sign (or the exponent's, after `EEX`) | NEG level 1 |

- **Errors never mutate the stack.** `1 ENTER 0 ÷` reports `Infinite Result` with both
  operands still present. An HP calculator does not eat your arguments.
- Full precision lives on the stack; formatting happens only at the display boundary, so
  `1 ENTER 3 ÷ 3 ×` is exactly `1`.
- `%` is an ordinary binary function: `200 ENTER 10 %` is `20`, depth 1.
- Angle mode is applied only at the trig boundary.

## Faceplate

Geometry comes from `HP 50g/50G.kml`; legends were transcribed from `HP 50g/50G.bmp`.
**Transcribe, never recall** — the shift planes are the easiest thing to get wrong. On the
50g the left shift is **white** and the right shift is **orange** (purple/green is the 48
series).

`tests/test_keymap.py::TestKeymapEngineContract` asserts every bound legend reaches a
command the engine implements. The keyboard and the engine were built separately; that is
the seam where a key looks live and does nothing.

Two deliberate deviations, both forced by having no soft menus:
- the `X` key carries the stack commands (SWAP / ROT / OVER) the 50g keeps in its STACK menu;
- left-shift `DEL` clears the command line rather than editing text.

## Known gaps

No CAS, no soft menus (F1–F6), no ALPHA entry, no symbolic variables, no units, no complex
numbers, no matrices, no interactive stack, no equation writer. `EVAL`, `'`, `SYMB`, and
`ALPHA` keep their real legends and are rendered dimmed rather than stubbed.

## Rules

- **`HP 50g/` is gitignored and stays that way.** It holds copyrighted HP ROM images and
  personal calculator state. It is layout reference only — never commit any of it.
- Do not hand-edit the vendored fonts or `LICENSE` attribution.
- QML component names must not collide with `QtQuick.Controls` types. `StackView` is taken,
  which is why the stack component is `RpnStackView`.
