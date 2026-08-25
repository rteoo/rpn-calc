# Apple platforms

macOS is a first-class desktop host, same as Windows. iOS is the next port:
the face and the engines are ready; the Qt-on-iPhone host is not.

## macOS

Run from source:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m rpncalc
```

Build a `.app` (must be run on a Mac; PyInstaller cannot cross-compile):

```sh
pip install -e ".[build]"
python tools/build_exe.py
```

Produces `dist/rpn-calc.app` and `dist/rpn-calc.app.zip`. The bundle id is
`io.github.rteoo.rpncalc`. Retina is on (`NSHighResolutionCapable`), Dark Mode
is followed (`NSRequiresAquaSystemAppearance` is false), and Command-key
shortcuts (`⌘C` `⌘V` `⌘Z` `⌘M` `⌘Q` `⌘,`) match the Windows Ctrl bindings.

The Dock icon is `src/rpncalc/icons/rpncalc.icns`. `tools/build_exe.py`
ad-hoc signs the bundle. Gatekeeper still quarantines downloads that are not
notarized; first-open is right-click → Open, and `xattr -cr dist/rpn-calc.app`
is the local escape. Notarization needs a Developer ID in the release
workflow secrets — without them a tagged `v*` still attaches the zip.

`python tools/smoke_macos.py --source` and `python tools/smoke_macos.py dist/rpn-calc.app`
open a real cocoa window (`--smoke` refuses `QT_QPA_PLATFORM=offscreen`) and
check the bundle id, icon, and signature. That is what CI runs on
`macos-latest`; an offscreen `start()` is not that check.

macOS has no equivalent of the Windows calculator-key binding
(`VK_LAUNCH_APP2`). The settings item stays visible and dimmed, the same
way keys this calculator cannot honour stay on the faceplate.

## iOS — why it is a port, not a rebuild

Three layers, three different lives on a phone:

| Layer | Files | iOS |
|---|---|---|
| Calculation core | `numeric.py` `stack.py` `rpn_engine.py` `alg_engine.py` `keymap.py` | Unchanged. No Qt, no host. |
| Face | `qml/*.qml` | Unchanged. `SafeArea` insets the notch; a long-press on the display opens the settings that a right-click opens on the desktop; `backend.isMobile` fills the screen and skips window-geometry restore. |
| Host | `backend.py` `systemtheme.py` `launchkey.py` `__main__.py` | This is the port. |

`backend.py` is the seam. QML talks to it through properties and slots, not
through Python imports. An iOS `Backend` that publishes the same names can
keep every QML file.

### The Backend contract

QML reads:

`expression` `display` `darkMode` `textScale` `themeBackground`
`themeForeground` `themeAccent` `themeSelection` `isMobile`
`hasPointerHover` `rpnMode` `stackLines` `commandLine` `entering`
`errorText` `cursorLevel` `menuLabels` `menuEnabled` `angleMode`
`numberFormatLabel` `shiftState` `keyRows` `calculatorKeySupported`
`calculatorKeyBound`

QML calls:

`pressKey` `pressKeyId` `pressCommand` `pressMenu` `copyResult`
`pasteNumber` `windowGeometry` `fitToScreen` `saveWindowGeometry`
`toggleEntryMode` `setAngleMode` `setNumberFormat` `setCalculatorKeyBound`

On iOS, `isMobile` is true, `calculatorKeySupported` is false,
`windowGeometry` reports invalid, and `saveWindowGeometry` is a no-op.
Clipboard goes through `QGuiApplication.clipboard()`, which Qt maps to
`UIPasteboard`. Dark mode comes from `QGuiApplication.styleHints().colorScheme()`,
already the path macOS uses. Dynamic Type is the one host signal that is
not wired yet: `SystemTheme.textScale()` returns 1.0 on Apple hosts because
Qt already maps Retina to logical pixels, and doubling that would blow the
face up. An iOS host that wants Dynamic Type publishes it there.

### Two ways in

**Qt for iOS, C++ Backend.** The documented Qt path. New
`backend.cpp` / `systemtheme.cpp` that wrap a CPython 3.13 iOS build of
the engines (PEP 730 — `sys.platform == "ios"`), *or* a C++ rewrite of
the engines if embedding Python is more trouble than it is worth. Same
`qml/` directory. Xcode project takes `packaging/ios/Info.plist` and
`packaging/ios/Assets.xcassets`.

**CPython 3.13 on iOS, same Python Backend.** Possible once someone
builds Qt Quick for that interpreter. `host.py` already recognises
`sys.platform == "ios"` and the older BeeWare `darwin`+`iPhone*` embedding.
No QML changes.

Do not start from a SwiftUI rewrite of the faceplate. The legends were
transcribed, the shift planes are data in `keymap.py`, and a second
keyboard will drift.

### What is deliberately not done yet

- No Xcode project. It would not compile without a Qt iOS kit, and an
  empty project that does not build is worse than a documented contract.
- No Python rewrite in Swift. The engines stay Python (or a faithful C++
  port of the same tests).
- No landscape layout on iPhone. The 50g face is portrait; `Info.plist`
  locks it. iPad may rotate — `uiScale` already fits whatever rectangle
  it is given.
- No iOS keyboard. The command line is `Text`, not `TextInput`, so the
  system keyboard stays down. The faceplate *is* the keyboard.
