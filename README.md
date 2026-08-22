# rpn-calc

An HP 50g-style RPN calculator wearing [omacalc](https://github.com/omacom-io/omacalc)'s face.

RPN is the default input method: a real command line, `ENTER`, and an unbounded stack with
full stack control. Algebraic mode is kept behind a toggle, exactly as the real 50g keeps it
under `MODE`. The keyboard is the 50g's lower block, shift planes and all.

## Install

```sh
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
```

On Linux use `.venv/bin/pip`. PySide6 is the only runtime dependency.

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
16 ENTER  ←shift √x       →  256      (left shift on the root key is x squared)
81 ENTER √x               →  9
200 ENTER 10 %            →  20
1 ENTER 0 ÷               →  "Infinite Result", both operands still on the stack
```

### The interactive stack

Press `▲` (or `STK`) to open the 50g's stack browser. A cursor walks the levels and the
soft menu acts on the one it sits on — the fastest way to reorganise a deep stack.

| | |
|---|---|
| `▲` / `▼` | Move the cursor; `▼` off level 1 closes the browser |
| `◀` / `▶` | Jump to level 1 / the deepest level |
| `ECHO` | Copy the selected value into the command line |
| `EDIT` | Lift the level off the stack and into the command line |
| `PICK` | Copy the selected level to level 1 |
| `ROLL` | Move the selected level to level 1 |
| `ROLLD` | Send level 1 down to the selected level |
| `←` | Drop the selected level |
| `Enter` | Close the browser |

The soft-menu labels are buttons; `F1`–`F6` press them from the keyboard. While the
browser is open it owns the keyboard, so a stray digit cannot disturb the stack.

### Shift planes

The left shift is white, the right shift is orange, same as the faceplate. A shift arms for
exactly one key; pressing it twice cancels, pressing the other one switches. The armed plane
brightens on the face so you can read the next key rather than remember it.

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
| `↑` `↓` `←` `→` | Interactive stack: open and navigate |
| `F1`–`F6` | Interactive stack soft menu |
| `Alt+s` `Alt+q` `Alt+l` `Alt+e` `Alt+g` `Alt+i` `Alt+p` `Alt+a` | √, x², LN, e^x, LOG, 1/x, π, ABS |
| `Ctrl+Z` | Undo |
| `Ctrl+M` | Toggle RPN / ALG |
| `Ctrl+C` / `Ctrl+V` | Copy / paste a number |

## Building a Windows executable

```sh
.venv/Scripts/pip install -e ".[build]"
.venv/Scripts/python.exe tools/build_exe.py
```

Produces `dist/rpncalc.exe` — one self-contained file, about 53 MB, no Python
installation needed on the target machine.

| | Startup | Shape |
|---|---|---|
| `tools/build_exe.py` | ~3.3 s | a single `.exe` |
| `tools/build_exe.py --onedir` | ~1.0 s | a `dist/rpncalc/` folder |

One file unpacks its whole payload to a temporary directory on **every** launch,
so it never gets faster. If you launch the calculator often, the folder build is
worth the extra shape. `--debug` produces a console build that prints why it
failed to start, which a windowed build cannot.

The icon is committed at `packaging/rpncalc.ico`; regenerate it with
`python tools/make_icon.py` only if it should change.

## Test

```sh
pytest
```

Runs headless — no display needed.

## What it does not do

No CAS, soft menus, ALPHA entry, symbolic variables, units, complex numbers, or matrices.
Keys with no meaning here keep their real legend and render dimmed rather than lying about
being live. If you need those, the real 50g emulator is still the answer.

## Credits

- UI, theming, and the algebraic engine derive from **omacalc** by David Heinemeier Hansson (MIT).
- **iA Writer Mono S** is bundled under the SIL Open Font License 1.1 (`src/rpncalc/fonts/OFL.txt`).
- Key geometry and legends were read off an Emu48 HP 50g faceplate. No HP ROM images are
  distributed with this project.
