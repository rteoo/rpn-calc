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
| `Alt+s` `Alt+q` `Alt+l` `Alt+e` `Alt+g` `Alt+i` `Alt+p` `Alt+a` | √, x², LN, e^x, LOG, 1/x, π, ABS |
| `Ctrl+Z` | Undo |
| `Ctrl+M` | Toggle RPN / ALG |
| `Ctrl+C` / `Ctrl+V` | Copy / paste a number |

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
