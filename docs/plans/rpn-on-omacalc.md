# rpn-calc — HP 50g-style RPN calculator on the omacalc face

## Context

A daily-driver RPN calculator for Windows. Full HP 50g emulators do the job but
carry a CAS this project does not need, and they present a 1990s Win32 bitmap UI.
[omacalc](https://github.com/omacom-io/omacalc) is the opposite: a clean, modern
Qt Quick face with a ~500-line algebraic engine — and no RPN.

This project takes omacalc's UI and architecture as the base and puts a real
HP 50g RPN engine underneath it: **the command line, ENTER, the stack, and stack
control** are the point. Scientific functions come along because they are cheap
once the engine is right. ALG mode survives as a mode toggle, exactly as it does
on the real 50g under `MODE`.

### Why a port instead of a fork

omacalc is Qt 6 / C++ targeting Omarchy: xdg-desktop-portal over D-Bus, a theme
reader for `~/.local/state/omarchy/current/theme/colors.toml`, qmake + make.
This repo is a **PySide6 port**, not a fork: there is no merging from upstream
omacalc afterwards.

`Main.qml` and `CalcButton.qml` carry over essentially verbatim — the
QML↔backend contract is context properties, `Q_PROPERTY`, and `Q_INVOKABLE`,
all of which PySide6 mirrors 1:1 as `Property`, `Signal`, `Slot`. The C++
`Backend` is pure string/double manipulation and ports directly.

### Confirmed scope

| Decision | Choice |
|---|---|
| Stack | PySide6 + QML (Python 3.10+, PySide6 ≥ 6.11) |
| Keypad | HP 50g-shaped lower block, 5 columns, left/right shift planes |
| Math | Scientific core: √ x² 1/x y^x LN e^x LOG 10^x SIN COS TAN + inverses, π, EEX, DEG/RAD, STD/FIX/SCI/ENG |
| Modes | RPN default; ALG retained behind a MODE toggle |

---

## Source material

**Read before writing code:**

- omacalc sources — fetch verbatim from `raw.githubusercontent.com/omacom-io/omacalc/master/`:
  `src/backend.h`, `src/backend.cpp`, `src/main.cpp`, `src/Main.qml`, `src/CalcButton.qml`,
  `src/systemtheme.h`, `tests/tst_omacalc.cpp`. All are small; `backend.cpp` is the big one at 16 KB.
- An HP 50g faceplate layout descriptor and bitmap (local reference only, not in this
  repo). Authoritative for the physical grid:
  rows at y = 347 (HIST/EVAL/'/SYMB/←), 385 (Y^x/√x/SIN/COS/TAN), 422 (EEX/±/X/1÷X/÷),
  459 (ALPHA/7/8/9/×), 500 (←shift/4/5/6/−), 541 (→shift/1/2/3/+), 582 (ON/0/./SPC/ENTER).
- **Transcribe shift-plane legends from the faceplate image and a running 50g,
  not from memory.** Recalled 50g legends are the single thing an implementer
  will get wrong.

---

## Target layout

```
rpn-calc/
  AGENTS.md              # repo contract; CLAUDE.md is a single @AGENTS.md line
  README.md              # install/run + attribution (omacalc MIT, iA Writer OFL)
  LICENSE                # MIT, retaining omacalc copyright line
  pyproject.toml         # PySide6 dependency, pytest dev extra
  src/rpncalc/
    __main__.py          # port of main.cpp
    backend.py           # QObject facade exposed to QML as `backend`
    numeric.py           # format_number / seal_number / parse_number  (pure)
    stack.py             # RpnStack                                    (pure)
    rpn_engine.py        # command line + stack + modes                (pure)
    alg_engine.py        # port of omacalc's infix engine              (pure)
    keymap.py            # 50g key grid as data + shift state machine  (pure)
    systemtheme.py       # Windows dark mode + text scale; Omarchy reader kept
    qml/  Main.qml  CalcButton.qml  StackView.qml  StatusBar.qml
    fonts/ iAWriterMonoS-*.ttf  OFL.txt
  tests/                 # pytest; mirrors the pure modules
```

Everything in the engine layer is plain Python with no Qt import. `backend.py` is the only
file that knows about Qt. That is what keeps the test suite fast and headless, and it mirrors
omacalc's own split — note that upstream `tests/tests.pro` compiles `backend.cpp` **without**
`systemtheme.cpp` for exactly this reason.

**Load QML and fonts from the filesystem** relative to `__file__`. Do not port `resources.qrc`
— `pyside6-rcc` would add a build step for no gain.

---

## Checkpoints

Each is one commit, independently verifiable.

### CP0 — Skeleton and vendoring
- `git init`; branch `feat/rpn-engine`. `.gitignore` must exclude local 50g emulator
  reference files, `build/`, `__pycache__/`, `.venv/`.
- `pyproject.toml`: `pyside6>=6.11`, dev extra `pytest`.
- Vendor from omacalc: `fonts/` (4 TTFs + `OFL.txt`), `Main.qml`, `CalcButton.qml` **byte-identical**, `LICENSE`.
- **Verify:** `python -m venv .venv && .venv\Scripts\pip install -e .[dev]` succeeds; `python -c "import PySide6; print(PySide6.__version__)"`.

### CP1 — Faithful PySide6 port, zero behavior change
This is the baseline. Nothing new is invented here; if CP1 is green, the port is sound.

- `numeric.py` — `format_number(v)` ports `Backend::formatNumber`: `f"{v:.15g}"` with negative-zero
  collapsed. `seal_number(entry)` ports the anonymous-namespace helper (chop trailing `.`, bare `-` → `0`).
- `alg_engine.py` — direct port of the `Backend` token machinery: `m_tokens`/`m_entry`/`m_result`/
  `m_result_value`/`m_just_evaluated`/`m_errored`, plus `press_digit`, `press_decimal`, `press_operator`,
  `press_equals`, `press_percent`, `press_toggle_sign`, `press_backspace`, `press_clear`,
  `evaluate_tokens`, `pretty_expression`, `current_value`. Keep the typographic operators
  `+ − × ÷` (U+2212, U+00D7, U+00F7) as token values — the QML labels already use them.
  Keep the 15-significant-digit entry cap and the 17-digit chain-from-result precision trick.
- `backend.py` — `Backend(QObject)`: `expression`/`display` as `Property(str, notify=calculationChanged)`,
  `@Slot(str) pressKey`, `copyResult`/`pasteNumber` via `QGuiApplication.clipboard()`,
  `windowGeometry`/`saveWindowGeometry` via `QSettings`, and the four `theme*` properties.
- `systemtheme.py` — replace the D-Bus portal. Prefer `QGuiApplication.styleHints().colorScheme()`
  (Qt 6.5+, works on Windows); fall back to `HKCU\...\Themes\Personalize\AppsUseLightTheme`.
  Text scale from `HKCU\Control Panel\Desktop\LogPixels` / 96. **Keep** the Omarchy `colors.toml`
  reader — it already degrades gracefully to hardcoded defaults when the file is absent, so it
  costs nothing on Windows and keeps the app usable on Linux.
- `__main__.py` — port of `main.cpp`: register fonts, `QQuickStyle.setStyle("Material")`,
  `setContextProperty("backend", backend)`, load `qml/Main.qml`.
- `tests/test_alg_engine.py`, `tests/test_numeric.py` — **all 18 cases from `tst_omacalc.cpp` ported 1:1**,
  keeping the `press(calc, "4 2 × 3 + 7 =")` space-separated-keys helper. Skip only `loadsCurrentOmarchyTheme`.
- **Verify:** `pytest` green. `python -m rpncalc` opens a window matching omacalc's screenshot;
  `42 × 3 + 7 =` → `133` with `42 × 3 + 7` on the expression line.

### CP2 — RPN stack core (pure, no UI)
- `stack.py` — `RpnStack` over a list where index 0 is **level 1**. Unbounded, like the 50g.
  Commands: `push` `pop` `peek(level)` `depth` `drop` `dropn` `swap` `dup` `dupn` `over` `rot`
  `unrot` `roll(n)` `rolld(n)` `pick(n)` `clear` `to_list`.
- `last_args` — the arguments the previous command consumed, restorable (50g's `→HIST` UNDO).
- **Underflow must raise without mutating the stack.** The 50g never eats your arguments on error.
- `tests/test_stack.py` — every command; LIFO ordering; level indexing off-by-ones;
  `roll`/`rolld` inverse; underflow leaves depth and contents untouched; LAST ARG restore.
- **Verify:** `pytest tests/test_stack.py` green. No UI change.

### CP3 — RPN engine: the command line
The heart of the project. Get this exactly right.

`rpn_engine.py` — `RpnEngine` holding an `RpnStack`, a command-line string, and modes.
Single entry point `press(key_id)`. Semantics, in HP 50g order of importance:

| Input | Command line open | Command line empty |
|---|---|---|
| digit / `.` / `EEX` | append | open a new command line |
| `ENTER` | parse and push (SPC-separated → push each, left to right) | **DUP level 1** |
| any operator/function | **implicit ENTER first**, then apply | apply to the stack |
| `←` (backspace) | delete last character | **DROP level 1** |
| `+/−` (CHS) | toggle sign of the mantissa, or of the exponent after `EEX` | NEG level 1 |
| `SPC` | insert a separator | no-op |

Errors set a message, leave the stack untouched, and clear on the next keypress:
`Too Few Arguments` (depth < arity), `Infinite Result` (x/0), `Undefined Result` (0/0).

- `tests/test_rpn_engine.py` — the canonical sequences:
  `3 ENTER 4 +` → `7`; `3 SPC 4 ENTER` → depth 2, level 1 = 4;
  `2 ENTER ENTER` → depth 2, both 2; `5 ← ←` → command line then DROP;
  `1 ENTER 0 ÷` → `Infinite Result` **and depth still 2 with 1 and 0 intact**;
  `1 ENTER 3 ÷ 3 ×` → exactly `1` (full-precision chaining, same guarantee omacalc makes);
  `SWAP`/`ROT`/`ROLL` against known stacks.
- **Verify:** `pytest tests/test_rpn_engine.py` green. Still no UI.

### CP4 — Scientific functions and modes
- Unary: `√` `x²` `1/x` `LN` `e^x` `LOG` `10^x` `SIN` `COS` `TAN` `ASIN` `ACOS` `ATAN` `ABS` `NEG`.
  Binary: `y^x` `%` `MOD`. Constant: `π`.
- Angle mode DEG/RAD applied **only at the trig boundary** — the stack always holds plain numbers.
- Display formats in `numeric.py`: `STD` (current `%.15g`), `FIX n`, `SCI n`, `ENG n`.
- **Verify:** trig correct in both angle modes; domain errors (`√-1`, `LN 0`, `ASIN 2`) raise and
  leave the stack untouched; `FIX 2` of `1/3` → `0.33` while the stack still holds full precision.

### CP5 — Keymap and shift planes
- `keymap.py` — the 50g lower block as data: `(row, col) → {unshifted, left, right, label, label_left, label_right}`.
  Grid and legends transcribed from a 50g faceplate layout, not recalled.
- Shift state machine, matching the real 50g: pressing a shift **arms** it for exactly one key;
  the next keypress consumes it; pressing the same shift twice cancels; pressing the opposite
  shift switches planes.
- `ALPHA` (row 7 col 1) and `X` (row 6 col 3) have no meaning without symbolic objects.
  **Render them disabled** rather than stubbed, and record the gap in `AGENTS.md`.
- `tests/test_keymap.py` — arm / consume / cancel / switch; every grid cell resolves in all planes.
- **Verify:** `pytest tests/test_keymap.py` green.

### CP6 — QML: stack display and status bar
- `StackView.qml` — right-aligned rows labelled `4:` `3:` `2:` `1:` bottom-up, **level 1 at the bottom**,
  monospace, `elide: Text.ElideLeft`, level count auto-fitted to available height.
- Command line rendered below level 1 when open, with a cursor.
- `StatusBar.qml` — `RAD`/`DEG` · `STD`/`FIX n` · `RPN`/`ALG`, plus an error-message slot.
  Mirrors the 50g's `RAD XYZ HEX R= 'X'   ALG` header.
- `Main.qml` — display area becomes StatusBar + StackView + command line in RPN mode, and falls
  back to omacalc's expression/display pair in ALG mode. **Keep `mixColors`, `uiScale`, `scaledSize`,
  the theme properties, and the window-geometry persistence block untouched.**
- **Verify:** run it; type `3 Enter 4 +` on the physical keyboard; `7` appears on level 1.

### CP7 — HP keypad in QML
- `CalcButton.qml` — add `labelLeft`/`labelRight` legends rendered above the cap in the 50g's
  purple/orange, dimmed unless that shift plane is armed. Keep the existing resting/hover/pressed
  lift model and the `Accessible` block.
- `Main.qml` keypad — 5-column grid driven by the `keymap.py` model, matching the 50g row order.
  Shift keys carry their signature colors and show an armed state.
- **Verify:** click `4 ENTER 5 ×` → `20`; press `←shift` then `√x` → legends light up and √ applies;
  press `←shift` twice → arming clears.

### CP8 — MODE toggle, persistence, PC keyboard map
- RPN/ALG toggle; angle mode and number format persisted in `QSettings` next to the window geometry.
- Physical-keyboard map in `Main.qml`: digits, `+ - * /`, `Enter`→ENTER, `Backspace`→←,
  `Space`→SPC, `s`→CHS, `Esc`→CLEAR, `Ctrl+Z`→UNDO, and a modifier for the shift planes.
  Keep omacalc's existing `Ctrl+C`/`Ctrl+V`/`Ctrl+Q` shortcuts.
- `tests/test_backend_keys.py` — end-to-end through `Backend.pressKey` in both modes.
- **Verify:** `pytest` green; restart the app and confirm mode, angle, and format survive.

### CP9 — Docs and packaging
- `README.md`: install, run, RPN cheat sheet, attribution (omacalc MIT, iA Writer OFL 1.1).
- `AGENTS.md` + one-line `CLAUDE.md` pointer: stack, layout, commands, the RPN semantics decisions
  above, and the known gaps (ALPHA, X, symbolic objects, units, complex, matrices, soft menus, CAS).
- Optional: `pyside6-deploy` or PyInstaller one-file `.exe`.
- **Verify:** fresh venv → `pip install -e .` → `python -m rpncalc` runs.

---

## Delegation

CP1 must land alone — it establishes `numeric.py` and the repo, which everything imports.
After CP1, two tracks are genuinely independent once the `Backend` property names and the
`keymap.py` schema are fixed up front:

- **Engine track** (CP2 → CP3 → CP4): pure Python, no Qt, fully test-driven. Good delegation target.
- **UI track** (CP6 → CP7): QML only, against a stubbed backend exposing the agreed properties.

CP5 and CP8 are integration points — keep them in the main session.

---

## Risks and edge cases

- **HP emulator files stay out of git.** Layout reference (faceplate descriptor and bitmap)
  is local only. Copyrighted HP ROM images and personal calculator state must never be
  committed.
- **PySide6 is the only new runtime dependency.**
- **Shift-plane legends are the fidelity trap.** Transcribe from the faceplate, not from memory.
- **Float formatting parity:** Python's `f"{v:.15g}"` must reproduce Qt's `QString::number(v,'g',15)`.
  The ported tests already pin the interesting cases — `0.1+0.2` → `0.3`, `-0.0` → `0`, `1e15` → `1e+15`.
- **Typographic minus:** omacalc uses U+2212 in tokens and `-` from the keyboard. `pasteNumber`
  already normalizes it. Preserve that on both engines.

## Definition of done

`pytest` green across `test_numeric`, `test_alg_engine`, `test_stack`, `test_rpn_engine`,
`test_keymap`, `test_backend_keys` — including all 18 behaviors ported from omacalc's suite.

`python -m rpncalc` opens on Windows in RPN mode, honoring system dark/light, and this sequence
works end to end from both the on-screen keypad and the physical keyboard:

```
5 ENTER 3 ENTER 2 + ×        → 25
←shift √x                     → 5
1 ENTER 3 ÷ 3 ×               → 1        (exactly)
SWAP  ROT  ←(on empty line)   → stack reorders and drops as on a 50g
1 ENTER 0 ÷                   → "Infinite Result", stack intact
```

Mode, angle mode, number format, and window geometry survive a restart. `AGENTS.md` records
the known gaps. No ROM images in git.
