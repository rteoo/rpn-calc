# rpn-calc

An HP 50g-style RPN calculator wearing [omacalc](https://github.com/omacom-io/omacalc)'s face.

RPN is the default input method: a command line, `ENTER`, and a real unbounded stack with
full stack control. Algebraic mode is retained behind a mode toggle, as on the real 50g.

> Work in progress. See [docs/plans/rpn-on-omacalc.md](docs/plans/rpn-on-omacalc.md).

## Install

```sh
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"    # Windows
```

## Run

```sh
python -m rpncalc
```

## Test

```sh
pytest
```

## Credits

- UI, theming, and the algebraic engine derive from **omacalc** by David Heinemeier Hansson (MIT).
- **iA Writer Mono S** is bundled under the SIL Open Font License 1.1 (`src/rpncalc/fonts/OFL.txt`).
- Key geometry referenced from an Emu48 HP 50g faceplate. No HP ROM images are distributed here.
