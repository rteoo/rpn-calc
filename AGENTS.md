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

## The interactive stack

The 50g's stack browser, opened with the up arrow. A cursor walks the levels and
the soft menu acts on whichever one it sits on. Behaviour was read off a recording
of the real calculator, not recalled:

- `▲` opens it on level 1; `▲`/`▼` move the cursor, `▼` off level 1 closes it.
- **PICK** copies the selected level to level 1 and leaves the cursor on the same
  level *number* — the objects shift up underneath it rather than the pointer
  chasing the one it acted on. This is the detail worth not regressing.
- **ROLL** moves the selected level to level 1; **ROLLD** sends level 1 back down.
- **ECHO** appends the selected value to the command line, stack untouched.
- **EDIT** lifts the level off the stack into the command line and closes the browser.
- `←` drops the selected level; emptying the stack closes the browser.
- While it is open it owns the keyboard: arithmetic and digits are ignored, so a
  mistyped key cannot rearrange a stack mid-reorganisation.
- **VIEW** is a full-screen object viewer, which tells you nothing about a plain
  number that its own line does not. Declared unimplemented and rendered dimmed.
- Algebraic mode has no stack to browse, so the arrows and menu do nothing there.

## Faceplate

Geometry comes from `HP 50g/50G.kml`; legends were transcribed from `HP 50g/50G.bmp`.
**Transcribe, never recall** — the shift planes are the easiest thing to get wrong. On the
50g the left shift is **white** and the right shift is **orange** (purple/green is the 48
series).

`tests/test_keymap.py::TestKeymapEngineContract` asserts every bound legend reaches a
command the engine implements. The keyboard and the engine were built separately; that is
the seam where a key looks live and does nothing.

Deliberate deviations, all forced by the reduced feature set:
- the `X` key carries the stack commands (SWAP / ROT / OVER) the 50g keeps in its STACK menu;
- left-shift `DEL` clears the command line rather than editing text;
- the navigation row (`STK ▲ ▼ ◀ ▶`) is flattened into one row; the 50g keeps these
  as a cluster beside APPS/MODE/TOOL, none of which are on this face. `STK` is ours;
- `◀`/`▶` jump the cursor to level 1 and to the deepest level. The 50g reserves them
  for editing wide objects, which this calculator does not have;
- the soft-menu labels are themselves the buttons, drawn at the bottom of the display.
  The 50g labels them on-screen with six unlabelled keys beneath; there is no room for
  another key row here. `F1`–`F6` press them from the keyboard.

Anything drawn rather than typeset (shift arrows, direction arrows, the backspace
icon, the stack cursor) is drawn because iA Writer Mono has no glyph for it. Check
before adding a symbol to a cap — the font is missing more than you would expect.

## Known gaps

No CAS, no soft menus (F1–F6), no ALPHA entry, no symbolic variables, no units, no complex
numbers, no matrices, no equation writer. `EVAL`, `'`, `SYMB`, and
`ALPHA` keep their real legends and are rendered dimmed rather than stubbed.

## Packaging

`tools/build_exe.py` drives PyInstaller through `packaging/rpncalc.spec`.
`pyside6-deploy` is not used: it goes through Nuitka, which needs a C compiler.

- **The entry point is `packaging/entry.py`, not `rpncalc/__main__.py`.**
  PyInstaller runs its entry script as a top-level module with no parent package,
  so the relative imports in `__main__.py` have nothing to be relative to.
- **Excluding a PySide6 module does not exclude the Qt library behind it.** The
  hook copies what it finds, so `packaging/rpncalc.spec` prunes `a.binaries` and
  `a.datas` by name. Without that the build carries `Qt6WebEngineCore.dll` — a
  whole Chromium, 194 MB — and weighs 159 MB instead of 53 MB.
- `__main__.py` resolves assets through `_resource_dir()`, which honours
  `sys._MEIPASS`; `Path(__file__).parent` is wrong in a frozen build.
- **Verifying a frozen build means walking the process tree.** One-file mode
  spawns a child process to run the app; the parent owns only a hidden bootloader
  window, so enumerating the parent's windows finds nothing and looks like a hang.
- `--debug` builds a console variant. A windowed build has nowhere to print a
  traceback, so a startup failure is silent.
- **An offscreen `grabWindow()` renders whether or not the window would really
  show.** It is not evidence the app opens; check a real window for that.

## Rules

- **`HP 50g/` is gitignored and stays that way.** It holds copyrighted HP ROM images and
  personal calculator state. It is layout reference only — never commit any of it.
- Do not hand-edit the vendored fonts or `LICENSE` attribution.
- QML component names must not collide with `QtQuick.Controls` types. `StackView` is taken,
  which is why the stack component is `RpnStackView`.
