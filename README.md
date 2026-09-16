# rpn-calc

<p align="center">
  <img src="src/rpncalc/icons/rpncalc-1024.png" width="128" alt="rpn-calc app icon">
</p>

<p align="center">
  A desktop RPN calculator for Windows and macOS, with an interactive stack,
  scientific functions, and 12C-style finance.
</p>

<p align="center">
  <a href="https://github.com/rteoo/rpn-calc/actions/workflows/test.yml"><img src="https://github.com/rteoo/rpn-calc/actions/workflows/test.yml/badge.svg" alt="Test status"></a>
  <a href="https://github.com/rteoo/rpn-calc/tags"><img src="https://img.shields.io/github/v/tag/rteoo/rpn-calc?label=stable" alt="Stable tag"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license"></a>
</p>

rpn-calc combines a real RPN command line and unbounded stack with a custom QML
face. RPN is the default input method, with algebraic mode available behind a
toggle. The face adds one yellow shift plane, a wide ENTER key, direct finance
keys, and a dedicated FINANCE form.

## Highlights

- RPN-first entry with implicit ENTER, undo, and full stack control.
- Interactive stack browser with ECHO, EDIT, PICK, ROLL, and ROLLD.
- Scientific operations, statistics, configurable number formats, and angle modes.
- TVM and cash-flow keys plus a dedicated finance form.
- Full-precision calculations with half-away-from-zero display rounding.
- Windows calculator-key integration and native Windows/macOS desktop packages.
- Pure-Python calculation core kept independent from Qt.
- No telemetry, accounts, cloud services, or network-dependent calculations.

## Quick start

Download the package for your platform from the
[latest release](https://github.com/rteoo/rpn-calc/releases/latest). No Python
installation is required for a packaged build.

| Platform | Package |
| --- | --- |
| Windows | `rpncalc-windows.zip` containing the app and its required Qt files |
| macOS | `rpn-calc-macos.zip` containing the `.app` bundle |

On Windows, extract the complete ZIP and run `rpncalc.exe` inside the resulting
folder. Keep the folder together because the executable loads Qt from beside it.

The macOS package may be ad-hoc signed when a notarized release is unavailable.
In that case, use **right-click → Open** on first launch to confirm Gatekeeper's
prompt.

To run from source with Python 3.10 or newer:

```powershell
git clone https://github.com/rteoo/rpn-calc.git
cd rpn-calc
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m rpncalc
```

PySide6 is the only runtime dependency.

## First use

The stack shows level 1 at the bottom, immediately above the command line.
Type a number and press `ENTER` to push it. With an empty command line, `ENTER`
duplicates level 1 and Backspace drops it.

```text
5 ENTER 3 ENTER 2 + ×             → 25
5 ENTER x²                        → 25
81 ENTER √x                       → 9
200 ENTER 10 %                    → 20
36 n  1 i  10000 PV  0 FV  PMT   → about -332.14
1 ENTER 0 ÷                       → "Infinite Result"; operands are preserved
```

Press `▲` to open the interactive stack browser. Use the arrows to select a
level and the soft menu to copy, edit, or move it. Press `MENU` to open SETTINGS
for display locale, number format, and the Windows calculator-key toggle.

## Stack and input

With the browser closed, `▶` swaps levels 1 and 2 and `◀` rotates the top three
so level 3 moves to level 1. Neither arrow opens the browser.

Inside the browser, the cursor selects a stack level:

| Control | Behavior |
| --- | --- |
| `▲` / `▼` | Move the cursor; `▼` below level 1 closes the browser |
| `ECHO` | Append the selected value to the command line |
| `EDIT` | Remove the selected level and place it on the command line |
| `PICK` | Copy the selected level to level 1 |
| `ROLL` | Move the selected level to level 1 |
| `ROLLD` | Send level 1 down to the selected level |
| Backspace | Drop the selected level |
| `Enter` | Close the browser |

The soft-menu labels are clickable, and `F1`–`F6` activate them from the
keyboard. The browser owns keyboard input while open, preventing a stray digit
or operator from changing the stack.

### Shift

The calculator has one yellow shift plane. It arms for one keypress; pressing
Shift again cancels it. Shifted legends brighten on the face while armed.

### Keyboard shortcuts

| Key | Behavior |
| --- | --- |
| `0`–`9` `.` | Enter digits |
| `Enter` / `=` | ENTER |
| `Backspace` | Delete a character, or DROP with an empty command line |
| `Space` | Separate values on one command line |
| `+ - * /` `^` `%` | Arithmetic, power, and percent |
| `s` / `e` | Change sign / enter an exponent (EEX) |
| `x` / `r` / `d` | SWAP / ROT / DROP |
| `Del` | CLEAR the stack |
| `Esc` | ON: cancel the command line |
| `↑` | Open the interactive stack |
| `←` / `→` | Rotate the top three / swap levels 1 and 2 |
| `F1`–`F6` | Activate the current soft-menu keys |
| `Alt+s` `Alt+q` `Alt+l` `Alt+e` | √, x², LN, e^x |
| `Alt+g` `Alt+i` `Alt+p` `Alt+a` | LOG, 1/x, π, ABS |
| `Ctrl+Z` / `⌘Z` | Undo |
| `Ctrl+X` / `⌘X` | Cut level 1, then DROP |
| `Ctrl+C` / `⌘C` | Copy level 1 |
| `Ctrl+V` / `⌘V` | Paste a number |
| `Ctrl+M` / `⌘M` | Toggle RPN / ALG |
| `Ctrl+,` / `⌘,` | Open SETTINGS |

## Finance

Direct finance keys use the familiar store-and-solve convention: enter a value and press `n`, `i`,
`PV`, `PMT`, or `FV` to store it; press the same key with no new entry to solve
for it. Shifted `NPV`, `IRR`, `CFo`, `CFj`, and `Nj` handle cash flows.

Shift-FINANCE opens the TVM form for N, I%YR, PV, PMT, FV, P/YR, and Begin/End.
While open, the form owns the keyboard; ENTER stores the selected value and the
EDIT / SOLVE soft keys operate on the selected register. AMOR is not implemented
and remains dimmed.

## Data safety and privacy

rpn-calc performs calculations locally and does not require an account, send
telemetry, or upload calculator data. Desktop settings use the platform's local
Qt settings storage.

On Windows, calculator-key registration changes only the current user's
Explorer AppKey 18 binding after the user enables it in SETTINGS. Each build
releases only a binding that still belongs to that build.

## Platform status and limitations

rpn-calc packages Windows and macOS desktop builds. The portable calculation
core and offscreen Qt behavior are covered by automated tests, but platform
integration still requires verification on the matching physical host.

- **Windows:** supports the dedicated calculator key through the current user's
  registry. A real launch-key test must synthesize `VK_LAUNCH_APP2` and observe
  which window opens.
- **macOS:** uses native Qt scaling and color-scheme behavior. Ad-hoc-signed
  packages require manual first-open confirmation; notarized packages do not.
- **Linux:** source execution is supported by Qt, but no Linux desktop package
  is currently published.
- **iOS:** the QML face and pure-Python core have portability groundwork, but
  PySide6 does not currently provide the required iOS wheel. The host plan and
  Xcode seed live in [the Apple platform plan](docs/plans/apple-platforms.md)
  and [`packaging/ios/`](packaging/ios/).

The calculator does not implement CAS, ALPHA entry, symbolic variables, units,
complex numbers, matrices, the equation writer, or linear regression. Trig is
available in the engine but has no faceplate or keyboard binding.

## Develop and build

Install the `dev` extra and run the complete verification gates:

```powershell
python -m pytest
python tools/verify_core.py
```

The suite runs with offscreen Qt. `verify_core.py` enforces 100% statement and
branch coverage for number formatting, the stack, both engines, the keymap, and
finance. Calculation results are also checked against an independent 50-digit
Decimal oracle. Current host evidence and explicit verification limits are
recorded in [the dated verification record](docs/verification/2026-09-07.md).

Build a desktop package with the `build` extra:

```powershell
python -m pip install -e ".[build]"
python tools/build_exe.py
```

| Host | Output |
| --- | --- |
| Windows | `dist/rpncalc/` and `dist/rpncalc-windows.zip` |
| macOS | `dist/rpn-calc.app` and `dist/rpn-calc.app.zip` |

Windows folder builds are the default; pass `--onefile` for a single executable
that extracts its runtime to a temporary directory on each launch. Pass
`--debug` to produce a console build with startup diagnostics. macOS always
builds an `.app` bundle.

On a Mac, `python tools/smoke_macos.py --source` verifies the mapped source
window, while `python tools/smoke_macos.py dist/rpn-calc.app` checks the packaged
bundle. The smoke test requires a real Cocoa session and refuses offscreen mode.

Developer ID signing and notarization are opt-in. Configure
`RPNCALC_CODESIGN_IDENTITY` for a Hardened Runtime build, then notarize and
staple the completed app:

```sh
RPNCALC_CODESIGN_IDENTITY="Developer ID Application: … (TEAMID)" python tools/build_exe.py
APPLE_ID=… APPLE_TEAM_ID=… APPLE_APP_PASSWORD=… python tools/notarize_macos.py dist/rpn-calc.app
```

`APPLE_APP_PASSWORD` must be an app-specific password. Stapling regenerates the
ZIP so the released archive contains the ticket. A tagged `v*` release builds
both platforms and publishes their artifacts; absent Apple credentials, it
falls back to an ad-hoc signature.

Release history is documented in [CHANGELOG.md](CHANGELOG.md). Historical size
and startup measurements remain in the
[engineering notes](docs/history/2026-09-07-engineering-notes.md#packaging) and
are not current release guarantees.

## Release dependencies

Release dependencies are recorded in `requirements-release.lock` with package
hashes. Release CI installs that lock before installing the local project with
`--no-deps --no-build-isolation`. Regenerate deliberately with
`uv pip compile pyproject.toml --extra dev --extra build --universal --python-version 3.12 --generate-hashes -o requirements-release.lock`.
Action commits are pinned; dependency updates still require review and tests.

## License

rpn-calc is released under the [MIT License](LICENSE).

The interface, theming, and algebraic engine derive from **omacalc** by David
Heinemeier Hansson (MIT). TVM and cash-flow closed forms were cross-checked
against **finanx-12c** by Fabio Lima (MIT). Bundled **iA Writer Mono S** uses the
SIL Open Font License 1.1 in [`src/rpncalc/fonts/OFL.txt`](src/rpncalc/fonts/OFL.txt).
