# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-08-25

### Added

- **Developer ID signing and notarization for the macOS bundle.**
  `RPNCALC_CODESIGN_IDENTITY` switches `tools/build_exe.py` from an ad-hoc
  signature to a Developer ID one with Hardened Runtime and the entitlements
  PyInstaller's CPython needs under it. `tools/notarize_macos.py` submits the
  zip with `notarytool --wait`, staples the ticket to the `.app`, and re-zips —
  Apple notarizes the archive, but Gatekeeper reads the ticket off the bundle.
  A tagged `v*` release runs both when the Apple secrets are configured and
  skips both when they are not, so the ad-hoc zip still ships either way.
  Closes #17.

## [0.2.1] - 2026-08-25

### Changed

- **`--smoke` judges what it measured.** The window reading is a
  `SmokeReading` dataclass and the verdict is two pure functions
  (`platform_verdict`, `window_verdict`), so every branch of the release gate
  is tested off a Mac instead of only on the release runner.
- **macOS signing is inside out** - nested `.dylib`/`.so` first, frameworks as
  whole units, then the bundle. `--deep` is deprecated for signing and a
  notarized build cannot use it.
- **A tagged release publishes from one job.** The macOS and Windows builds run
  in parallel and upload artifacts; a single `publish` job attaches both. Two
  jobs calling `action-gh-release` on the same tag raced to create the release.
  Both build jobs now run the test suite, so a tag cannot ship a red suite.

### Fixed

- **`Meta+` shortcut duplicates removed.** Qt already maps `Ctrl` in a key
  sequence to ⌘ on macOS, so `⌘Q` was never missing; the `Meta+` spelling
  bound the physical Control key on a Mac and claimed Super+Q, Super+M and
  Super+Z on Linux, where the window manager owns them.
- **`--smoke` checks `isExposed()` rather than `visible` and `winId()`.**
  `visible` is a literal in `Main.qml` and `winId()` creates the handle it was
  asked to test, so neither check could ever fail.
- **`quitOnLastWindowClosed` is no longer set as an Apple special case.** It is
  Qt's default on every host; `_apply_apple_presentation` set it to the value
  it already had. The invariant is pinned by a test and by `--smoke` instead.
- A `--debug` build on macOS writes `dist/rpn-calc-debug.app` instead of
  overwriting the release bundle beside it.

## [0.2.0] - 2026-08-25

### Added

- **macOS as a desktop host.** Run from source with the same venv as Linux;
  `python tools/build_exe.py` on a Mac writes `dist/rpn-calc.app` with bundle
  id `io.github.rteoo.rpncalc`, a Retina `.icns`, and Dark Mode following
  the system. Command-key shortcuts (`⌘C` `⌘V` `⌘Z` `⌘M` `⌘Q` `⌘,`) work,
  which the existing Ctrl bindings already provide - Qt maps `Ctrl` in a key
  sequence to ⌘ on macOS. Option+letter scientific shortcuts match the
  physical key, so a German layout's ß does not swallow `√`.
- **iOS-ready face and host seam.** `SafeArea` insets the notch; a long-press
  on the display opens the settings a right-click opens on the desktop;
  `backend.isMobile` fills the screen and skips window-geometry restore.
  `host.py` recognises PEP 730 `sys.platform == "ios"` and the older BeeWare
  embedding. The Backend contract, a portrait `Info.plist`, and a 1024px App
  Store icon live in `docs/plans/apple-platforms.md` and `packaging/ios/`.
- **CI** on Ubuntu, Windows, and macOS, including a cocoa smoke of
  `python -m rpncalc` and a PyInstaller `.app` artifact on `macos-latest`.
  Tagged `v*` releases attach `rpncalc.exe` and `rpn-calc-macos.zip`.

### Changed

- Text scale on Apple hosts stays at 1.0. Qt already maps a Retina backing
  store to logical pixels; multiplying by `devicePixelRatio` would reopen the
  "it opened maximized" bug on a MacBook.

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

[0.3.0]: https://github.com/rteoo/rpn-calc/releases/tag/v0.3.0
[0.2.1]: https://github.com/rteoo/rpn-calc/releases/tag/v0.2.1
[0.2.0]: https://github.com/rteoo/rpn-calc/releases/tag/v0.2.0
[0.1.2]: https://github.com/rteoo/rpn-calc/releases/tag/v0.1.2
[0.1.1]: https://github.com/rteoo/rpn-calc/releases/tag/v0.1.1
[0.1.0]: https://github.com/rteoo/rpn-calc/releases/tag/v0.1.0
