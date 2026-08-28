# rpn-calc

An HP 50g-style RPN calculator wearing [omacalc](https://github.com/omacom-io/omacalc)'s face, implemented in Python.

RPN is the default input method: a real command line, `ENTER`, and an unbounded stack with
full stack control. Algebraic mode is kept behind a toggle, exactly as the real 50g keeps it
under `MODE`. The face is our own layout — one yellow shift, 12C-style finance keys, and a
wide ENTER — with the interactive stack and a 50g-style FINANCE form on top.

## Download

A Windows zip and a macOS `.app` zip ship with each
[release](https://github.com/rteoo/rpn-calc/releases/latest). No Python
installation needed.

On Windows, unzip `rpncalc-windows.zip` and run `rpncalc.exe` from inside the
folder it extracts — keep the folder together, since the executable loads Qt
from beside it. A macOS zip built without an Apple Developer ID is ad-hoc
signed, and Gatekeeper's first-open is then right-click → Open; a notarized
one opens with a double-click. To run from source on any desktop, install it.

## Install

```sh
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows
pip install -e ".[dev]"
```

PySide6 is the only runtime dependency. Python 3.10 or newer.

## Run

```sh
python -m rpncalc
```

## Using it

The stack shows level 1 at the bottom, just above the command line. Type a number and the
command line opens; `ENTER` pushes it. With nothing typed, `ENTER` duplicates level 1 and
`←` drops it.

```
5 ENTER 3 ENTER 2 + ×     →  25
5 ENTER x²                →  25
81 ENTER √x               →  9
200 ENTER 10 %            →  20
36 n  1 i  10000 PV  0 FV  PMT   →  about -332.14   (12C store / solve)
1 ENTER 0 ÷               →  "Infinite Result", both operands still on the stack
```

### Finance

Direct keys follow the 12C: enter a value and press `n` / `i` / `PV` / `PMT` /
`FV` to store; press the same key with no new entry to solve for it. Shifted
`NPV` / `IRR` / `CFo` / `CFj` / `Nj` handle cash flows. Shift-FINANCE opens the
50g TVM form; while it is open it owns the keyboard, and soft-menu EDIT / SOLVE
work the selected register (AMOR is declared unimplemented and dimmed).

### The interactive stack

With the browser closed, the horizontal arrows are stack commands: **`▶` swaps
levels 1 and 2**, and **`◀` rotates the top three** so level 3 comes down to
level 1. Neither opens the browser.

Press `▲` (or `MENU`) to open the 50g's stack browser. A cursor walks the levels and the
soft menu acts on the one it sits on — the fastest way to reorganise a deep stack.

| | |
|---|---|
| `▲` / `▼` | Move the cursor; `▼` off level 1 closes the browser |
| `ECHO` | Copy the selected value into the command line |
| `EDIT` | Lift the level off the stack and into the command line |
| `PICK` | Copy the selected level to level 1 |
| `ROLL` | Move the selected level to level 1 |
| `ROLLD` | Send level 1 down to the selected level |
| `←` | Drop the selected level |
| `Enter` | Close the browser |

The soft-menu labels are buttons; `F1`–`F6` press them from the keyboard. While the
browser is open it owns the keyboard, so a stray digit cannot disturb the stack.

### Shift

One yellow shift plane. It arms for exactly one key; pressing it twice cancels.
Armed legends brighten on the face so you can read the next key rather than
remember it.

### Keyboard

| Key | Does |
|---|---|
| `0`–`9` `.` | Enter digits |
| `Enter` / `=` | ENTER |
| `Backspace` | Delete a character, or DROP when nothing is being typed |
| `Space` | Separate two numbers on one command line |
| `+ - * /` `^` `%` | Arithmetic, power, percent |
| `s` / `e` | Change sign / exponent (EEX) |
| `x` / `r` / `d` | SWAP / ROT / DROP |
| `Esc` / `Del` | Clear the stack / cancel the entry |
| `↑` | Open the interactive stack |
| `←` `→` | Rotate the top three / swap levels 1 and 2 |
| `F1`–`F6` | Interactive stack soft menu |
| `Alt+s` `Alt+q` `Alt+l` `Alt+e` `Alt+g` `Alt+i` `Alt+p` `Alt+a` | √, x², LN, e^x, LOG, 1/x, π, ABS |
| `Ctrl+Z` / `⌘Z` | Undo |
| `Ctrl+M` / `⌘M` | Toggle RPN / ALG |
| `Ctrl+C` / `⌘C`, `Ctrl+V` / `⌘V` | Copy / paste a number |
| `Ctrl+,` / `⌘,` | Settings (right-click the display, or press and hold on a touch screen) |

## Building a desktop app

```sh
pip install -e ".[build]"
python tools/build_exe.py
```

| Host | Output |
|---|---|
| Windows | `dist/rpncalc/` and `dist/rpncalc-windows.zip` — about 56 MB zipped |
| macOS | `dist/rpn-calc.app` and `dist/rpn-calc.app.zip` — ad-hoc signed |

Set `RPNCALC_CODESIGN_IDENTITY` to a Developer ID to sign the bundle with
Hardened Runtime instead, then notarize and staple it:

```sh
RPNCALC_CODESIGN_IDENTITY="Developer ID Application: … (TEAMID)" python tools/build_exe.py
APPLE_ID=… APPLE_TEAM_ID=… APPLE_APP_PASSWORD=… python tools/notarize_macos.py dist/rpn-calc.app
```

`APPLE_APP_PASSWORD` is an app-specific password, not the account password.
Stapling rewrites `dist/rpn-calc.app.zip`, because the zip Apple received does
not carry the ticket.

`--onefile` builds a single `.exe` instead, convenient to hand to someone but
about 3.5 s to a window against 0.7 s for the folder: the bootloader unpacks
its whole payload to a new temporary directory on every launch, so it never
warms up. macOS ignores the flag - a folder is what goes inside the `.app`.
`--debug` produces a console build that prints why it failed to start, which a
windowed build cannot.

On a Mac, `python tools/smoke_macos.py --source` opens the real cocoa window
and quits; `python tools/smoke_macos.py dist/rpn-calc.app` does the same for
the frozen bundle. Offscreen is refused — that is not a window.

A tagged `v*` release attaches `rpncalc-windows.zip` and `rpn-calc-macos.zip`. It
notarizes the macOS bundle when the Apple secrets are configured on the
repository, and falls back to an ad-hoc signature when they are not — in which
case first-open is right-click → Open, and `xattr -cr dist/rpn-calc.app` is
the local escape.

The icon is committed at `src/rpncalc/icons/` — inside the package, because the
app sets it as its own window icon at startup, not only as the executable's
resource. `rpncalc.ico` covers Windows; `rpncalc.icns` covers the Dock;
`rpncalc.png` is the 256px form a Linux `.desktop` entry wants;
`rpncalc-1024.png` is the opaque App Store icon. Regenerate all of them with
`python tools/make_icon.py` only if the icon should change.

An un-notarized macOS `.app` is quarantined by Gatekeeper. On the machine that
built it, `xattr -cr dist/rpn-calc.app` clears that. The release workflow
notarizes when `MACOS_CERTIFICATE`, `MACOS_CERTIFICATE_PASSWORD`, `APPLE_ID`,
`APPLE_TEAM_ID` and `APPLE_APP_PASSWORD` are set as repository secrets, and
ad-hoc signs when they are not.

## iOS

The calculation core is pure Python and the face is QML, so an iOS app is a host
port, not a rewrite. `SafeArea`, a long-press for settings, and `backend.isMobile`
are already in the face. There is no PySide6 iOS wheel yet; the contract and the
Xcode seed (bundle id, portrait lock, App Icon) live in
[`docs/plans/apple-platforms.md`](docs/plans/apple-platforms.md) and
[`packaging/ios/`](packaging/ios/).

## Test

```sh
pytest                                          # the whole suite, headless
python tools/verify_core.py                     # + a 100% gate on the core
```

1783 tests, no display needed. The calculation core — number formatting, the
stack, both engines, the keymap, and finance — is held at **100% statement and
branch coverage**, and its answers are checked against an independent 50-digit
decimal implementation rather than against the same `math` functions it calls.

## What it does not do

No CAS, ALPHA entry, symbolic variables, units, complex numbers, or matrices.
Soft-menu AMOR on the FINANCE screen is unimplemented and dimmed. Trig lives in
the engine but is off the faceplate. If you need a full 50g, the real emulator
is still the answer.

## Changelog

Release history is in [CHANGELOG.md](CHANGELOG.md).

## Credits

- UI, theming, and the algebraic engine derive from **omacalc** by David Heinemeier Hansson (MIT).
- TVM / cash-flow closed forms were cross-checked against **finanx-12c** by Fabio Lima (MIT).
- **iA Writer Mono S** is bundled under the SIL Open Font License 1.1 (`src/rpncalc/fonts/OFL.txt`).
- Face spacing still borrows ideas from an Emu48 HP 50g layout; the legends are our own.
  No HP ROM images are distributed with this project.
