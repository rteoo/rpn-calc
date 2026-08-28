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
.venv/bin/pip install -e ".[dev]"        # macOS / Linux; use .venv\Scripts on Windows
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
| `finance.py` | TVM and cash-flow math (12C closed forms + NPV/IRR). |
| `backend.py` | The **only** Qt-aware engine file; the QML context property `backend`. |
| `host.py` | Which OS this is (Windows / macOS / iOS / Linux). Stdlib only. |
| `systemtheme.py` | Dark mode (Qt `colorScheme`, Windows registry fallback) and text scale. |
| `launchkey.py` | The keyboard's calculator key, bound through the Windows registry. |
| `qml/` | `Main.qml`, `CalcButton.qml`, `RpnStackView.qml`, `SoftMenu.qml`, `StatusBar.qml`. |

`host.py` and `launchkey.py` are stdlib-only for the same reason `systemtheme.py`
is separate: the host integration is not the calculator, and it has to import
cleanly on Linux, macOS, and a future iOS interpreter.

Keep the engine layer free of Qt imports. That split is upstream's too — omacalc's
`tests.pro` compiles `backend.cpp` without `systemtheme.cpp` for the same reason.
It is also why an iOS port can keep `numeric.py` / `rpn_engine.py` / `qml/` and
only replace the host.

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
- `◀`/`▶` do **nothing** while browsing. With the browser closed they are stack
  commands instead: `▶` swaps levels 1 and 2, `◀` rotates the top three. The
  swap was read frame by frame off a recording of a real 50g - three presses,
  each toggling levels 1 and 2, with the ordinary HOME menu still showing.
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

The face is our own layout: a single **yellow** shift plane (no white left-shift, no
ALPHA), HP 12C-style finance keys on the body, and a wide ENTER. Geometry still borrows
spacing ideas from `HP 50g/50G.kml`, but the legends are not a 50g transcription.

`tests/test_keymap.py::TestKeymapEngineContract` asserts every bound legend reaches a
command the engine or backend implements. The keyboard and the engine were built
separately; that is the seam where a key looks live and does nothing.

Finance shows up in two places:
- **Direct keys** (`n`, `i`, `PV`, `PMT`, `FV`, plus shifted `Nj` / `IRR` / `NPV` /
  `CFo` / `CFj`) follow 12C store-vs-solve: a fresh entry stores into the register;
  pressing the key with no new entry solves for it. Math lives in `finance.py`, read
  against [finanx-12c](https://github.com/fabiolimace/finanx-12c) and the HP-12C guide.
  **`rate()` bisects, so it has to return the mid it converged on, not a bound,
  and it has to refuse a problem it cannot solve.** A single Begin-mode period
  with no balloon pays back exactly the principal whatever the interest — the
  annuity-due factor cancels the discount — so no rate can be recovered; the
  all-zero problem is flat for the same reason. Both used to "converge" on the
  99999 upper bound and report it as an interest rate, silently. `rate()` now
  probes two rates for a flat payment first and raises instead.
- **Shift-FINANCE** opens a 50g-style TVM form (N, I%YR, PV, PMT, FV, P/YR, Begin/End)
  with soft keys EDIT / AMOR / SOLVE. AMOR is declared unimplemented and dimmed.
  **The form owns the keyboard while it is showing**, the way the interactive
  stack browser does, and for the same reason: it hides the stack view, so a key
  it let through would rearrange a stack nobody can see. It answers the arrows,
  the entry keys, ENTER and ON, and swallows everything else. Entry reuses the
  ordinary command line — the form draws it, because the stack view that would
  normally show it is hidden — and ENTER stores it into the selected register.
  On the Begin/End row there is nothing to type, so ENTER toggles it.

Other deliberate deviations:
- `MENU` opens the interactive stack browser (same as `▲`);
- `ON` cancels the command line; shift-`←` is CLEAR (empty the stack);
- ENTER spans two columns; there is no SPC key on the face (keyboard Space still works);
- trig is off the face and has no keyboard binding either; the engine keeps it
  for the tests and the oracle;
- `Σ+` accumulates a (y, x) pair 12C-style — x from level 1, y read from level 2
  but *not* consumed — and leaves n in level 1. **An accumulator needs its
  readbacks on the face or it is write-only state**: shift-`+` is Σ (Σx into
  level 1, Σy into level 2, the 12C's `RCL Σ+`), shift-`Σ+` is MEAN (the same
  two divided by n), and shift-`ON` is CLΣ. Σ is the primary one — MEAN is Σ
  over n, not the reverse — and shipping MEAN without it left "what do these
  add up to" unanswerable. `x!` sits on shift-`1/X` because those three took
  the slots. Only n, Σx and Σy are accumulated, so there is no standard
  deviation and no linear regression; the 12C has both. The accumulator rides
  in the UNDO snapshot, so one UNDO takes a Σ+ back whole;
- the soft-menu labels are themselves the buttons; `F1`–`F6` press them from the keyboard.

Anything drawn rather than typeset (shift arrow, direction arrows, the backspace
icon, the stack cursor) is drawn because iA Writer Mono has no glyph for it. Check
before adding a symbol to a cap — the font is missing more than you would expect.

## The keyboard's calculator key

A keyboard's dedicated calculator key cannot be grabbed as a hotkey. Windows hands
it to Explorer as `VK_LAUNCH_APP2`, which Explorer resolves through
`HKCU\...\Explorer\AppKey\18`; a `ShellExecute` value there beats the built-in
mapping to the Calculator app, and deleting the value hands the key straight back.
HKLM carries the same subkey with **empty** values, so the per-user override has
nothing to outrank.

- **`ShellExecute` honours arguments.** A source checkout can therefore register
  `"...\pythonw.exe" -m rpncalc` with no launcher script - and `pythonw`, not
  `python`, or the key flashes a console every press.
- The binding names the build that wrote it, so a checkout and an installed exe
  each recognise only their own. Toggling it on from either re-points the key.
- **Verifying means synthesizing the key**, not reasoning about it:
  `ctypes.windll.user32.keybd_event(0xB7, 0, 0, 0)` makes Explorer do the real
  resolution. Nothing short of that proves which calculator opens.
- `tests/test_launchkey.py` drives the real registry, redirected at a scratch
  subkey. The live `AppKey\18` is the user's actual desktop setting - a test run
  that writes it has broken something outside the repo.
- Releasing the key leaves a value pointing at *another* application alone.
- The toggle lives in a context menu on the display (right-click, `Ctrl+,` /
  `⌘,`, or a long-press on a touch screen).
  The faceplate is a fixed 50g replica with no room for a settings key, and
  inventing one would be a deviation the Faceplate section would have to defend.

## Apple platforms

macOS is a desktop host, same as Windows: `python -m rpncalc` from a venv, or
`python tools/build_exe.py` for `dist/rpn-calc.app`. Dark mode follows
`QGuiApplication.styleHints().colorScheme()`. Retina is Qt's logical pixels;
do not multiply the window by `devicePixelRatio`. **Command-key shortcuts need
no binding of their own**: Qt maps `Ctrl` in a `QKeySequence` to ⌘ on macOS, so
one `"Ctrl+Q"` is ⌘Q there and Ctrl+Q elsewhere. Adding the `Meta+` spelling
binds the *physical* Control key on a Mac and Super on Linux, where the window
manager already owns Super+Q. The calculator-key toggle stays dimmed — there
is no `AppKey\18` on a Mac.

`python -m rpncalc --smoke` (and `tools/smoke_macos.py`) must run on cocoa,
not offscreen. What it checks is **`isExposed()`, not `visible`** - `visible`
is a literal in `Main.qml` and reads true for a window the compositor never
mapped. The judging is split out of the measuring (`platform_verdict`,
`window_verdict`, `SmokeReading`) so every branch of the gate is unit-tested
off a Mac; a release gate that only ever runs on the release runner is not
tested at all.

The `macos-app` CI job builds, ad-hoc signs, smokes, and uploads
`rpn-calc.app.zip`. A tagged `v*` release runs the suite on both hosts, builds
in parallel, and attaches both artifacts from **one** publishing job - two jobs
calling `action-gh-release` on the same tag race to create the release.
Signing is inside out: nested `.dylib`/`.so`, frameworks as whole units, then
the bundle. `--deep` is deprecated for signing and notarization will not take
it.

**Signing and notarization are opt-in, and the ad-hoc path must stay the
default.** `RPNCALC_CODESIGN_IDENTITY` switches `tools/build_exe.py` from an
ad-hoc signature to a Developer ID one, which is also what turns on Hardened
Runtime and `packaging/macos/rpncalc.entitlements` - a hardened *ad-hoc* build
only buys the library-validation crashes the entitlements exist to prevent.
`tools/notarize_macos.py` is the step after: it refuses an ad-hoc bundle before
spending the upload, submits with `notarytool --wait`, staples, and **re-zips**,
because Apple notarizes the archive but Gatekeeper reads the ticket off the
bundle. The zip built before submission never carries one.

The release workflow reads five secrets - `MACOS_CERTIFICATE`,
`MACOS_CERTIFICATE_PASSWORD`, `APPLE_ID`, `APPLE_TEAM_ID`,
`APPLE_APP_PASSWORD` - and skips both steps when they are absent, so a tag
still ships an ad-hoc zip whose first-open is right-click → Open. The identity
string is read back out of the keychain with `security find-identity` rather
than kept as a sixth secret. Two shell details are load-bearing:
`set-key-partition-list` is what lets `codesign` reach the private key without
a prompt, and `security list-keychains -s` must *add* the temporary keychain to
the search list, since `codesign` searches the list and not the file. Guard the
steps on `env.MACOS_CERTIFICATE`, not `secrets.*` - `secrets` is not readable
from a step `if`.

iOS is a host port, not a rewrite. The engines stay Python; the face stays
QML (`SafeArea`, long-press, `backend.isMobile`). PySide6 has no iOS wheel,
so the next step is a Qt-for-iOS `Backend` that publishes the same properties
and slots. The contract, the portrait `Info.plist`, and the 1024px App Icon
are in `docs/plans/apple-platforms.md` and `packaging/ios/`. `host.py`
already recognises `sys.platform == "ios"` (PEP 730) and the older BeeWare
`darwin`+`iPhone*` embedding.

## Known gaps

No CAS, no ALPHA entry, no symbolic variables, no units, no complex numbers, no matrices,
no equation writer. Soft-menu AMOR on the FINANCE screen is declared unimplemented and
dimmed. Trig lives in the engine but is off the faceplate.

## Validating the calculation core

```sh
python tools/verify_core.py
```

Runs the suite under branch coverage and **fails if `numeric.py`, `stack.py`,
`rpn_engine.py`, `alg_engine.py`, `keymap.py` or `finance.py` drops below 100% of
statements and branches.** The Qt layer is reported but not gated.

**A branch covered only because a property test happened to generate the right
sequence is not covered.** Hypothesis explores differently each run, so any
branch it reaches by chance needs a deterministic test pinning it too -
otherwise the gate passes or fails on a random seed. This has already happened
once, to the second-EEX branch in `rpn_engine`.

`rpncalc.__main__.start` does everything `main` does except enter the event
loop, so the startup path is testable. That split exists because `main` blocks,
and startup is where the one crash that reached a real desktop lived.

Coverage is the floor, not the evidence. Three things carry the actual weight:

- **`tests/oracle.py`** recomputes every result in 50-digit `decimal`, with the
  trigonometric functions built from Taylor series rather than a library call.
  Checking `math` against `math` would only prove the engine calls the function
  it says it calls. The oracle itself is validated against `math` first - if it
  ever disagrees by more than ~1e-16, fix the oracle before suspecting the engine.
- **`tests/test_core_properties.py::TestCrossEngine`** feeds the same expression
  to the RPN engine and the algebraic engine and to Python's own evaluator. They
  share only `numeric.py`, so agreement is three independent paths landing
  together.
- **Property tests** over generated input, which is what found the denormal
  formatting crash and the tie-breaking inconsistency. Nobody writes `5e-324`
  into an example table.

Two rules for this area:

- **Convert floats to `Decimal(value)`, never `Decimal(repr(value))`.** The first
  is the number the engine actually held; the second is its shortest printed
  form. Asking what the engine should have returned for a number it never had
  produces failures that are the test's fault.
- **Display rounding is half away from zero**, explicitly, in `numeric._quantise`.
  Python and IEEE round half to even, which is right for sums and wrong for a
  display - a calculator shows 2.5 as 3. The three formats disagreed about this
  until it became a decision.

## Packaging

`tools/build_exe.py` drives PyInstaller through `packaging/rpncalc.spec`.
`pyside6-deploy` is not used: it goes through Nuitka, which needs a C compiler.

- **The entry point is `packaging/entry.py`, not `rpncalc/__main__.py`.**
  PyInstaller runs its entry script as a top-level module with no parent package,
  so the relative imports in `__main__.py` have nothing to be relative to.
- **Excluding a PySide6 module does not exclude the Qt library behind it.** The
  hook copies what it finds, so `packaging/rpncalc.spec` prunes `a.binaries` and
  `a.datas` by name. Without that the build carries `Qt6WebEngineCore.dll` — a
  whole Chromium, 194 MB — and weighs 159 MB instead of 53 MB packed (the
  numbers are one-file `.exe` sizes, the shape that made them easy to compare).
- `__main__.py` resolves assets through `_resource_dir()`, which honours
  `sys._MEIPASS`; `Path(__file__).parent` is wrong in a frozen build.
- **A folder build is the default on every host; one file is opt-in.** Measured
  on Windows, median launch to a mapped window: **3544 ms one-file against
  727 ms for the folder.** The bootloader unpacks the whole payload to a *new*
  temporary directory on every launch, so it pays the same cost forever — and
  because `sys._MEIPASS` is a different path each time, Qt's compiled-QML cache
  never hits either, making every launch reparse the QML on top of the unpack.
  `--onefile` (`RPNCALC_BUILD_ONEFILE=1`) still builds the single `.exe`; macOS
  ignores it, because a folder is what goes inside the `.app`.
- **Windows ships `dist/rpncalc-windows.zip`, the way macOS already shipped
  `rpn-calc.app.zip`.** The zip is 56 MB against the old 56 MB one-file `.exe`,
  so the download did not grow — only the unpacked folder is larger, and that
  is what buys the startup back.
- **Startup time is not the QML's fault, so do not go optimising the face.**
  Loading `Main.qml` into a *warm* engine is ~50 ms, and the 40 `CalcButton`s
  cost ~16 ms of it. The ~500 ms in a cold `engine.load` is one-time Qt module
  registration — `QtQuick.Controls` alone is ~145 ms. Hidden `Canvas` items are
  not the problem either: Qt defers the backing store, so the 120 that never
  show measure the same as not having them. Forcing `QT_QUICK_BACKEND=software`
  buys ~77 ms in a frozen build and costs GPU rendering; it was measured and
  rejected.
- **Verifying a frozen build means walking the process tree.** One-file mode
  spawns a child process to run the app; the parent owns only a hidden bootloader
  window, so enumerating the parent's windows finds nothing and looks like a hang.
  A folder build does not spawn that child, so its own pid owns the window.
- `--debug` builds a console variant. A windowed build has nowhere to print a
  traceback, so a startup failure is silent.
- **The icon lives in the package, at `src/rpncalc/icons/`, not in `packaging/`.**
  `setWindowIcon` needs it at runtime, so it has to ship with the source too, not
  only be baked into the `.exe` / `.app` resource. Windows reads the `.ico`;
  the Dock reads the `.icns`; iOS takes the opaque 1024px PNG in
  `packaging/ios/Assets.xcassets`. `python tools/make_icon.py` writes all of
  them from one drawing function.
- **Setting the window icon is not enough on Windows.** The taskbar groups
  buttons by AppUserModelID and a process launched by the interpreter inherits
  the interpreter's, so `python -m rpncalc` shows the *Python* icon in the
  taskbar however the window icon is set. `_claim_taskbar_identity` claims an ID
  of our own; it must stay guarded by `host.is_windows()`, as `ctypes.windll`
  does not exist anywhere else.
- **macOS always produces an `.app` bundle** (a folder build inside). One-file
  on a Mac is what Gatekeeper fights. The bundle id is `io.github.rteoo.rpncalc`.
  Cross-compiling from Linux or Windows is not possible; run the build on a Mac.
  `tools/build_exe.py` signs and zips it - ad-hoc unless
  `RPNCALC_CODESIGN_IDENTITY` names a Developer ID. A tagged `v*` release
  uploads that zip, notarized when the Apple secrets are set.
- **`--smoke` refuses the offscreen plugin.** `start()` under
  `QT_QPA_PLATFORM=offscreen` is not evidence the app opens. On a Mac the
  platform must be cocoa. `tools/smoke_macos.py` inspects Info.plist, the
  `.icns`, and `codesign -dv` before launching the binary.
- **An offscreen `grabWindow()` renders whether or not the window would really
  show.** It is not evidence the app opens; check a real window for that.

## Git

Land pull requests with a merge commit (`gh pr merge --merge`). Never squash-merge or
rebase-merge. Squash is what put `cursoragent` on the GitHub contributors sidebar via
`refs/pull/13/head` while keeping `main` clean — the attribution still leaked.

Never author, commit, or add a trailer as Cursor, `cursoragent`, Composer, or any other
agent identity. Commits use the operator's git identity. The commit is the user's.

## Rules

- **`HP 50g/` is gitignored and stays that way.** It holds copyrighted HP ROM images and
  personal calculator state. It is layout reference only — never commit any of it.
- Do not hand-edit the vendored fonts or `LICENSE` attribution.
- QML component names must not collide with `QtQuick.Controls` types. `StackView` is taken,
  which is why the stack component is `RpnStackView`.
