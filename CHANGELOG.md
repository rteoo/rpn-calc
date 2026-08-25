# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - 2026-08-24

### Fixed

- A leftover windowed frame the size of the work area no longer opens the
  calculator ~1920 pixels wide. 0.1.1 stopped restoring maximized, but a
  screen-filling saved size still fitted and was left as-is. Saved size is
  restored only when it is no larger than the design face (~420×820).

## [0.1.1] - 2026-08-24

### Fixed

- A stale `window/maximized` flag no longer reopens the calculator filling the
  screen. The faceplate is a fixed proportion, so maximized is never restored;
  the window opens at the fitted size instead.
- The settings menu label, **Launch on the calculator key**, is no longer
  clipped to `Launch on th…`. The popup is sized from the painted font and the
  check indicator.

## [0.1.0] - 2026-08-24

First release. An HP 50g-style RPN calculator wearing omacalc's face.

### Added

- **RPN engine.** An unbounded stack, a real command line, and the full set of
  scientific functions. The command-line-open vs command-line-empty distinction
  is honoured throughout: `ENTER` pushes or duplicates, `←` deletes a character
  or drops level 1, and an operator forces an implicit `ENTER` first.
- **Algebraic mode**, ported from omacalc's infix token machinery and kept
  behind `Ctrl+M`, exactly as the real 50g keeps it under `MODE`.
- **The 50g faceplate** — the lower keyboard block with both shift planes, key
  geometry read off an Emu48 layout and legends transcribed rather than
  recalled. The armed shift plane brightens on the face.
- **The interactive stack**, the 50g's stack browser: a cursor walks the levels
  and `ECHO`, `EDIT`, `PICK`, `ROLL`, and `ROLLD` act on the one it sits on.
  With the browser closed, `▶` swaps levels 1 and 2 and `◀` rotates the top
  three.
- **Display modes** STD, FIX, SCI, and ENG, with display rounding half away
  from zero — a calculator shows 2.5 as 3. Full precision stays on the stack;
  formatting happens only at the display boundary.
- **A Windows executable** built through PyInstaller: one self-contained file,
  about 53 MB, no Python needed on the target machine. `--onedir` trades shape
  for a ~1 s startup.
- **Its own icon**, shipped inside the package so the window, taskbar, and
  Explorer all agree, with an AppUserModelID claimed so the taskbar stops
  showing the Python icon.
- **The keyboard's calculator key** can be bound to the app, toggled from a
  context menu on the display (right-click, or `Ctrl+,`). Releasing it hands
  the key back to Windows.
- **System theme following** — Windows dark mode and text scale, plus an
  Omarchy `colors.toml` reader carried over from upstream.

### Notes

- No CAS, soft menus beyond the stack browser, ALPHA entry, symbolic variables,
  units, complex numbers, or matrices. Keys with no meaning here keep their real
  legend and render dimmed rather than lying about being live.
- Errors never mutate the stack: `1 ENTER 0 ÷` reports `Infinite Result` with
  both operands still present.

[0.1.2]: https://github.com/rteoo/rpn-calc/releases/tag/v0.1.2
[0.1.1]: https://github.com/rteoo/rpn-calc/releases/tag/v0.1.1
[0.1.0]: https://github.com/rteoo/rpn-calc/releases/tag/v0.1.0
