# iOS port

This directory is the seed of an iOS app, not a running one. PySide6 does not
ship iOS wheels, so there is nothing here to `open` in Xcode yet. What *is*
here is everything the port will need the day it starts:

| Path | Role |
|---|---|
| `Info.plist` | Bundle id `io.github.rteoo.rpncalc`, portrait on iPhone |
| `Assets.xcassets/AppIcon.appiconset/` | Single 1024×1024 App Store icon (Xcode 14+) |

The face is already QML. The calculation core is already pure Python. The
missing piece is a `Backend` that Qt for iOS can construct — either a C++
`QObject` that speaks the same properties and slots, or CPython 3.13 on iOS
importing `rpncalc.backend` once a Qt Quick build exists for that interpreter.

See `docs/plans/apple-platforms.md` for the contract and the recommended order
of work.
