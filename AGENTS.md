# rpn-calc — project contract

An HP 50g-style RPN calculator with an omacalc-derived QML face.
Python 3.10+ and PySide6 (Qt Quick); RPN is the default, with an algebraic toggle.
This is a port of omacalc, with no upstream merge workflow.

## Commands and verification

Use an activated environment containing the declared `dev` extra:

```sh
python -m pytest
python tools/verify_core.py
python tools/smoke_macos.py --source  # macOS with a real cocoa session
```

The suite redirects QSettings to temporary storage and uses offscreen Qt.
The core gate requires 100% statement and branch coverage in `numeric.py`,
`stack.py`, `rpn_engine.py`, `alg_engine.py`, `keymap.py`, and `finance.py`.
Qt coverage is reported without that threshold.

[README.md](README.md) documents installation and packaging commands.
[The verification record](docs/verification/2026-09-07.md) identifies the host,
executed checks, and unverified platform operations. Keep counts and benchmark
measurements there, rather than presenting historical measurements as current
requirements. Earlier debugging and packaging evidence is preserved in
[the historical engineering notes](docs/history/2026-09-07-engineering-notes.md).

## Layout and boundaries

Paths below are relative to `src/rpncalc/`.

| Path | Responsibility |
|---|---|
| `numeric.py` | Parsing and STD/FIX/SCI/ENG display formatting |
| `stack.py` | Unbounded RPN stack; index 0 is level 1 |
| `rpn_engine.py`, `alg_engine.py` | Command-line scientific engine and infix engine |
| `keymap.py` | Faceplate data and single yellow shift state |
| `finance.py` | TVM and cash-flow calculations |
| `backend.py` | Only Qt-aware engine file; QML context property `backend` |
| `host.py`, `launchkey.py` | Stdlib-only host detection and Windows calculator key |
| `systemtheme.py` | Qt theme/text scale with Windows registry fallback |
| `qml/` | Face, stack, soft menu, status, forms, and key captions |
| `fonts/`, `icons/` | Runtime resources; retain vendored attribution |

Keep calculation modules independent of Qt. QML/fonts load from filesystem
resources, without qmake, a compiler, or a `.qrc`. Frozen builds must resolve
resources through `_resource_dir()`, including `sys._MEIPASS`.

## Calculation and input invariants

| Input | Open command line | Empty command line |
|---|---|---|
| Digit, decimal point, EEX | Append | Open a new line |
| ENTER | Parse and push each space-separated value | Duplicate level 1 |
| Operator/function | Implicit ENTER, then apply | Apply to stack |
| Backspace | Delete a character | Drop level 1 |
| Sign | Flip mantissa or active exponent sign | Negate level 1 |

- Errors preserve the stack; division by zero must leave both operands intact.
- Keep full precision until display. Percent is binary: `200 ENTER 10 %` leaves
  20 at depth 1. Apply angle mode only at the trig boundary.
- `y√x` deliberately uses the index from level 2 and radicand from level 1.
- ON cancels entry; shifted backspace clears the stack. Keyboard Space separates
  values even though the face has no SPC key.
- Direct finance keys store a fresh entry and solve with no new entry.
  `rate()` returns its converged midpoint and rejects flat or unsolvable cases,
  including all-zero cash flows and a single Begin-mode period without a balloon.
- Statistics retain every (x, y) point. Σ+ reads x from level 1 and y from level 2,
  leaves y unconsumed, and returns n. Σ− rejects a pair never accumulated.
  Shifted operators expose Σ/MEAN/MED/STD; Shift-ON clears statistics.
  Readbacks return x at level 1 and y at level 2. STD uses n−1 and needs two points.
- Use corrected two-pass variance and halve middle values before adding for the
  median. Route statistical readbacks through `_evaluate` so overflow becomes an
  error on the display. No summary-register substitution can preserve median.
- Display rounding is half away from zero in `numeric._quantise`.

## Face and keyboard ownership

- The face has one yellow shift plane, a wide ENTER, and 12C-style finance keys.
  `TestKeymapEngineContract` must keep every live legend connected to an action.
- Up opens the stack browser at level 1; up/down move the cursor; down off level 1
  closes it. Outside the browser, right swaps levels 1/2 and left rotates three.
  Inside it, horizontal arrows do nothing.
- PICK copies the selected value and leaves the cursor at the same level number.
  ROLL moves that level to the top; ROLLD sends the top to that level.
  ECHO appends without consuming; EDIT removes the level into entry and closes.
  Backspace drops the selection and closes the browser if it empties the stack.
- The browser owns the keyboard and ignores digits/arithmetic. ENTER closes it.
  Algebraic mode has no stack browser. VIEW remains unimplemented and dimmed.
- Shift-FINANCE opens TVM (N, I%YR, PV, PMT, FV, P/YR, Begin/End). Its form owns
  the keyboard, including entry, arrows, ENTER, and ON. ENTER stores or toggles
  Begin/End; CLEAR preserves P/YR and Begin/End. AMOR remains dimmed.
- MENU and Ctrl+, open SETTINGS, which also owns the keyboard. Decimal digits
  cycle STD then FIX 0–11; ENTER advances, horizontal arrows step either way.
  SCI/ENG remain engine features outside that ladder. Use `numberFormatLabel`
  in both the panel and status bar.
- TVM and SETTINGS are clipped forms. Preserve rendered layout tests for all
  rows, labels, entry/hint space, and long values; engine tests cannot prove fit.
- Soft-menu labels are clickable; F1–F6 activate them. Trig remains in the
  engine with no face or keyboard bindings.
- Do not name QML components after QtQuick.Controls types such as StackView.

## Rendering constraints

iA Writer Mono lacks Greek letters other than π, arrows, and superscripts.
Check glyph support before adding a caption. `CapText.qml` chooses exactly one
path: Canvas-drawn Σ/Δ, rich text using existing glyphs for superscripts, or plain
text. Measure rich text without tags and never request rich-text elision.
Keep the live keycap-glyph tests; deferred Canvas drawing needs event pumping
(the fixture pumps eight times). An offscreen screenshot proves rendering only.

## Host integration

- Windows resolves the dedicated calculator key through the per-user Explorer
  AppKey 18 ShellExecute value. Source registration uses pythonw with arguments.
  Each build recognizes its own binding; releasing it preserves another app's.
- Registry tests use a scratch subkey, never the live calculator-key setting.
  Actual Windows verification must synthesize VK_LAUNCH_APP2 and observe which
  window opens; unit tests and registry inspection alone do not prove this.
- Keep calculator-key controls dimmed on hosts without the Windows registry.
- macOS uses Qt logical pixels and colorScheme. Do not scale geometry again for
  Retina. Qt maps Ctrl shortcuts to Command; adding Meta variants binds the
  wrong physical keys on macOS/Linux.
- A startup smoke must verify `isExposed()`, icon, and window dimensions.
  `visible` or offscreen loading does not prove the compositor mapped a window.
  On macOS require cocoa; preserve unit tests of SmokeReading and both verdicts.
- iOS remains a future host port; preserve the backend properties/slots, SafeArea,
  long-press settings, and `isMobile`. See
  [the Apple plan](docs/plans/apple-platforms.md) and `packaging/ios/`.
  Desktop checks do not verify iOS support.

## Test strategy

Keep deterministic regression cases alongside property tests: chance coverage
from Hypothesis is insufficient for the core gate. Do not remove independent
oracles or boundary cases merely to reduce the suite.

`tests/oracle.py` uses 50-digit Decimal and independent trig series. Validate
the oracle before blaming the engine when they disagree. Cross-engine tests
compare RPN, algebraic, and Python evaluation. Convert real float inputs using
`Decimal(value)`, not `Decimal(repr(value))`. Keep tight-cluster statistics,
denormals, tie rounding, and overflow examples pinned.

## Packaging and release mechanics

- `tools/build_exe.py` drives PyInstaller through `packaging/rpncalc.spec`.
  Use `packaging/entry.py`; package-relative imports fail if __main__.py is
  treated as the top-level entry. Do not substitute Nuitka/pyside6-deploy.
- Prune both binary and data collections for excluded Qt modules.
  A folder build is default; Windows one-file is opt-in with `--onefile` or
  `RPNCALC_BUILD_ONEFILE=1`. macOS always uses an .app built on a Mac.
- One-file verification follows the child process that owns the real window.
  Use `--debug` for console diagnostics.
- Icons live in the package for source and frozen runtime use. Keep Windows
  AppUserModelID setup guarded by `host.is_windows()`.
- macOS bundle ID is `io.github.rteoo.rpncalc`. `tools/smoke_macos.py` checks
  Info.plist, executable, icon, and signature before launching a bundle.
- Ad-hoc signing remains default. Developer ID/Hardened Runtime requires the
  configured identity and entitlements. Sign nested libraries/frameworks before
  the bundle; do not use --deep signing.
- Notarization is a separate opt-in operation: reject ad-hoc input, submit,
  staple, and re-zip. A pre-stapling zip does not contain the ticket.
- The v* release runs tests/builds on both hosts and publishes artifacts from
  one job. Apple secrets enable signing/notarization; absence retains ad-hoc.
  Preserve temporary-keychain search-list inclusion and key partition access.
  Workflow step conditions use env values, not secrets expressions.
- Platform-specific release behavior needs evidence on that platform.

## Git and protected reference material

Use merge commits when landing PRs; do not squash or rebase merge.
`HP 50g/` stays ignored: it contains copyrighted ROMs and personal state.
Do not hand-edit vendored fonts or LICENSE attribution.

No CAS, ALPHA, symbolic variables, units, complex numbers, matrices, equation
writer, or linear regression is implemented.
