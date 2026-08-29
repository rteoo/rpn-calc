import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: win
    width: 420
    height: 820
    minimumWidth: 330
    minimumHeight: 640
    visible: true
    title: "rpn-calc"

    readonly property bool darkMode: backend.darkMode
    readonly property color pageColor: backend.themeBackground
    readonly property color inkColor: backend.themeForeground
    // Every hardcoded size is expressed at the 420 x 820 design size; resizing
    // the window scales the whole face with it. The design size is taller than
    // omacalc's because the 50g keyboard is seven rows, not five, plus the
    // navigation row the stack browser needs.
    readonly property real uiScale: Math.min(width / 420, height / 820)
    property real appliedTextScale: backend.textScale

    Connections {
        target: backend

        function onTextScaleChanged() {
            var factor = backend.textScale / win.appliedTextScale;
            win.appliedTextScale = backend.textScale;
            if (win.visibility === Window.Windowed) {
                win.width = Math.round(win.width * factor);
                win.height = Math.round(win.height * factor);
            }
        }
    }

    function mixColors(base, tint, amount) {
        return Qt.rgba(
            base.r + (tint.r - base.r) * amount,
            base.g + (tint.g - base.g) * amount,
            base.b + (tint.b - base.b) * amount, 1);
    }
    readonly property color mutedColor: mixColors(pageColor, inkColor, 0.5)

    function scaledSize(pixels) {
        return Math.max(1, Math.round(pixels * uiScale));
    }

    Material.theme: darkMode ? Material.Dark : Material.Light
    Material.accent: backend.themeAccent
    color: pageColor

    // Qt maps Ctrl in a key sequence to Command on macOS by default, so one
    // "Ctrl+..." binding is ⌘ there and Ctrl everywhere else. Spelling the
    // Meta variant out as well would bind the *physical* Control key on a Mac
    // and the Super key on Linux, where the window manager has already
    // claimed Super+Q.
    Shortcut {
        sequence: "Ctrl+X"
        context: Qt.ApplicationShortcut
        onActivated: backend.pressCommand("cut")
    }

    Shortcut {
        sequence: "Ctrl+C"
        context: Qt.ApplicationShortcut
        onActivated: backend.pressCommand("copy")
    }

    Shortcut {
        sequence: "Ctrl+V"
        context: Qt.ApplicationShortcut
        onActivated: backend.pressCommand("paste")
    }

    Shortcut {
        sequence: "Ctrl+Z"
        context: Qt.ApplicationShortcut
        onActivated: backend.pressCommand("undo")
    }

    Shortcut {
        sequence: "Ctrl+M"
        context: Qt.ApplicationShortcut
        onActivated: backend.pressCommand("toggle_mode")
    }

    Shortcut {
        sequence: "Ctrl+Q"
        context: Qt.ApplicationShortcut
        onActivated: win.close()
    }

    Shortcut {
        sequence: "Ctrl+,"
        context: Qt.ApplicationShortcut
        onActivated: backend.pressCommand("settings")
    }

    Item {
        id: face
        objectName: "face"
        anchors.fill: parent
        // SafeArea is zero on a desktop and the notch / home indicator on
        // iPhone. Adding it here, not to the window, keeps the 420×820
        // design size intact for geometry restore on macOS and Windows.
        anchors.topMargin: win.scaledSize(16) + SafeArea.margins.top
        anchors.bottomMargin: win.scaledSize(16) + SafeArea.margins.bottom
        anchors.leftMargin: win.scaledSize(16) + SafeArea.margins.left
        anchors.rightMargin: win.scaledSize(16) + SafeArea.margins.right
        focus: true

        // The physical keyboard drives commands directly rather than pretending
        // to press keycaps: shift planes are reached with Alt (left) and
        // Ctrl+Alt (right), which no keycap can express. On macOS Option is
        // Alt — match the physical key, not the composed character, or
        // Option+S becomes ß and never reaches sqrt.
        Keys.onPressed: function(event) {
            if (event.modifiers & (Qt.ControlModifier | Qt.MetaModifier)) {
                // ControlModifier is Ctrl on Windows and Linux and ⌘ on macOS
                // (Qt swaps them); those belong to the Shortcuts above. Meta
                // is the physical Control on a Mac and Super elsewhere, bound
                // to nothing here - swallow it rather than type a digit under
                // a window-manager chord.
                return;
            }

            var command = "";
            if (event.modifiers & Qt.AltModifier) {
                switch (event.key) {
                case Qt.Key_S: command = "sqrt"; break;
                case Qt.Key_Q: command = "sq"; break;
                case Qt.Key_L: command = "ln"; break;
                case Qt.Key_E: command = "exp"; break;
                case Qt.Key_G: command = "log"; break;
                case Qt.Key_I: command = "inv"; break;
                case Qt.Key_P: command = "pi"; break;
                case Qt.Key_A: command = "abs"; break;
                default: return;
                }
            } else if (event.key >= Qt.Key_F1 && event.key <= Qt.Key_F6) {
                // The soft keys, in the position the calculator puts them.
                backend.pressMenu(event.key - Qt.Key_F1);
                event.accepted = true;
                return;
            } else if (event.key === Qt.Key_Up) {
                command = "up";
            } else if (event.key === Qt.Key_Down) {
                command = "down";
            } else if (event.key === Qt.Key_Left) {
                command = "left";
            } else if (event.key === Qt.Key_Right) {
                command = "right";
            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                command = "enter";
            } else if (event.key === Qt.Key_Backspace) {
                command = "backspace";
            } else if (event.key === Qt.Key_Delete) {
                command = "clear";
            } else if (event.key === Qt.Key_Escape) {
                command = "clear_entry";  // ON: cancel the command line
            } else if (event.key === Qt.Key_Space) {
                command = "spc";
            } else if (event.text === "," || event.text === ".") {
                command = ".";
            } else if (event.text === "=") {
                command = "enter";
            } else if (event.text === "s" || event.text === "S") {
                command = "chs";
            } else if (event.text === "e" || event.text === "E") {
                command = "eex";
            } else if (event.text === "x" || event.text === "X") {
                command = "swap";
            } else if (event.text === "r" || event.text === "R") {
                command = "rot";
            } else if (event.text === "d" || event.text === "D") {
                command = "drop";
            } else if (event.text === "^") {
                command = "pow";
            } else if (/^[0-9]$/.test(event.text)) {
                command = event.text;
            } else if (/^[+\-*\/%]$/.test(event.text)) {
                command = event.text === "%" ? "percent" : event.text;
            } else {
                return;
            }

            backend.pressCommand(command);
            event.accepted = true;
        }

        Item {
            id: displayArea
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: divider.top
            anchors.leftMargin: win.scaledSize(8)
            anchors.rightMargin: win.scaledSize(8)
            anchors.bottomMargin: win.scaledSize(14)

            StatusBar {
                id: statusBar
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                angleMode: backend.angleMode
                numberFormat: backend.numberFormatLabel
                entryMode: backend.rpnMode ? "RPN" : "ALG"
                errorText: backend.errorText
                mutedColor: win.mutedColor
                fontPixelSize: win.scaledSize(13)
            }

            // RPN: the stack, level 1 at the bottom, command line beneath it. Named
            // RpnStackView because QtQuick.Controls already owns "StackView".
            RpnStackView {
                anchors.top: statusBar.bottom
                anchors.topMargin: win.scaledSize(6)
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: softMenu.showing ? softMenu.top : parent.bottom
                anchors.bottomMargin: softMenu.showing ? win.scaledSize(6) : 0
                visible: backend.rpnMode && !backend.financeOpen && !backend.settingsOpen
                lines: backend.stackLines
                commandLine: backend.commandLine
                entering: backend.entering
                cursorLevel: backend.cursorLevel
                inkColor: win.inkColor
                mutedColor: win.mutedColor
                fontPixelSize: win.scaledSize(20)
                rowSpacing: win.scaledSize(3)
            }

            FinanceView {
                anchors.top: statusBar.bottom
                anchors.topMargin: win.scaledSize(6)
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: softMenu.showing ? softMenu.top : parent.bottom
                anchors.bottomMargin: softMenu.showing ? win.scaledSize(6) : 0
                visible: backend.rpnMode && backend.financeOpen && !backend.settingsOpen
                fields: backend.financeFields
                cursor: backend.financeCursor
                entry: backend.commandLine
                inkColor: win.inkColor
                mutedColor: win.mutedColor
                pageColor: win.pageColor
                fontPixelSize: win.scaledSize(18)
                titlePixelSize: win.scaledSize(13)
            }

            SettingsView {
                objectName: "settingsView"
                anchors.top: statusBar.bottom
                anchors.topMargin: win.scaledSize(6)
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: softMenu.showing ? softMenu.top : parent.bottom
                anchors.bottomMargin: softMenu.showing ? win.scaledSize(6) : 0
                visible: backend.settingsOpen
                rows: backend.settingsRows
                cursor: backend.settingsCursor
                inkColor: win.inkColor
                mutedColor: win.mutedColor
                pageColor: win.pageColor
                fontPixelSize: win.scaledSize(15)
                titlePixelSize: win.scaledSize(13)
                onRowActivated: function(index) { backend.activateSettingsRow(index); }
            }

            SoftMenu {
                id: softMenu
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                labels: (backend.rpnMode || backend.settingsOpen) ? backend.menuLabels : []
                slotEnabled: backend.menuEnabled
                pageColor: win.pageColor
                inkColor: win.inkColor
                fontPixelSize: win.scaledSize(12)
                onActivated: function(index) { backend.pressMenu(index); }
            }

            // ALG: omacalc's own expression-above-result pair, unchanged.
            Item {
                anchors.top: statusBar.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                visible: !backend.rpnMode && !backend.settingsOpen

                Text {
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.right: parent.right
                    text: backend.expression
                    color: win.mutedColor
                    elide: Text.ElideLeft
                    font.family: "iA Writer Mono S"
                    font.pixelSize: win.scaledSize(21)
                }

                Text {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    horizontalAlignment: Text.AlignRight
                    text: backend.display
                    color: win.inkColor
                    fontSizeMode: Text.HorizontalFit
                    minimumPixelSize: win.scaledSize(22)
                    font.family: "iA Writer Mono S"
                    font.pixelSize: win.scaledSize(64)
                }
            }
        }

        Rectangle {
            id: divider
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: keypad.top
            anchors.bottomMargin: win.scaledSize(14)
            height: 1
            color: win.mixColors(win.pageColor, win.inkColor, 0.16)
        }

        // Faceplate keypad: eight rows, ENTER spanning two columns on the last.
        ColumnLayout {
            id: keypad
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: Math.round(parent.height * 0.70)
            spacing: win.scaledSize(7)

            Repeater {
                model: backend.keyRows

                RowLayout {
                    id: keyRow
                    required property var modelData

                    // Every row is five columns wide. The width is computed from
                    // the keypad rather than left to fillWidth, which shares out
                    // surplus space *equally* between items and so would make the
                    // bottom row's three single keys wider than the columns above
                    // and its two-column ENTER narrower than the pair it spans.
                    readonly property real cellSpacing: win.scaledSize(7)
                    readonly property real cellUnit:
                        (keypad.width - 4 * cellSpacing) / 5

                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: cellSpacing

                    Repeater {
                        model: parent.modelData

                        CalcButton {
                            required property var modelData
                            readonly property int cellSpan:
                                (modelData.span !== undefined && modelData.span > 0)
                                ? modelData.span : 1

                            Layout.fillWidth: false
                            Layout.fillHeight: true
                            Layout.preferredWidth: keyRow.cellUnit * cellSpan
                                + (cellSpan - 1) * keyRow.cellSpacing
                            label: modelData.label
                            keyValue: modelData.keyId
                            kind: modelData.style
                            iconName: modelData.icon
                            labelLeft: modelData.labelLeft
                            labelRight: modelData.labelRight
                            live: modelData.live
                            hoverEnabled: backend.hasPointerHover
                            armedShift: backend.shiftState
                            pageColor: win.pageColor
                            inkColor: win.inkColor
                            legendPixelSize: win.scaledSize(9)
                            onActivated: backend.pressKeyId(modelData.keyId)
                        }
                    }
                }
            }
        }
    }

    // Remember the last windowed geometry rather than whatever the window
    // happens to measure at teardown: a maximized window reports screen-sized
    // dimensions, and the close sequence hides the window before destruction,
    // so neither the live geometry nor the final visibility can be trusted.
    property rect normalGeometry: Qt.rect(x, y, width, height)
    property bool wasMaximized: false

    function trackNormalGeometry() {
        if (visibility === Window.Windowed)
            normalGeometry = Qt.rect(x, y, width, height);
    }

    onXChanged: trackNormalGeometry()
    onYChanged: trackNormalGeometry()
    onWidthChanged: trackNormalGeometry()
    onHeightChanged: trackNormalGeometry()

    onVisibilityChanged: function() {
        if (win.visibility === Window.Maximized || win.visibility === Window.FullScreen)
            wasMaximized = true;
        else if (win.visibility === Window.Windowed)
            wasMaximized = false;
    }

    // The design size grown by the desktop text scale can be taller than the
    // screen it opens on - at 150% scaling 820 becomes 1230, which does not fit
    // a 1080-pixel display. A window born bigger than its screen comes up
    // filling it, which is what made this look like it opened maximized.
    //
    // The fitting is done by the backend, not here: QML's Screen attached
    // property only offers desktopAvailableWidth/Height, which span the whole
    // virtual desktop. Across monitors at different offsets that is larger than
    // any single screen, so nothing ever measured as too big.
    Component.onCompleted: {
        if (backend.isMobile) {
            // A phone has no window chrome to restore. Fill the screen and
            // let uiScale shrink the 420×820 face to whatever is left after
            // the SafeArea inset.
            win.flags = Qt.Window | Qt.MaximizeUsingFullscreenGeometryHint;
            win.visibility = Window.FullScreen;
            return;
        }

        var geometry = backend.windowGeometry();
        var wantedX = x;
        var wantedY = y;
        var wantedWidth = Math.round(420 * backend.textScale);
        var wantedHeight = Math.round(820 * backend.textScale);

        if (geometry.valid) {
            wantedX = geometry.x;
            wantedY = geometry.y;
            x = geometry.x;
            y = geometry.y;
            // Honour a smaller saved window; never a larger one. A leftover
            // fullscreen frame from the old stretch still "fits" the screen,
            // so fitToScreen would leave a 1920-wide calculator sitting there.
            if (geometry.width <= wantedWidth && geometry.height <= wantedHeight) {
                wantedWidth = geometry.width;
                wantedHeight = geometry.height;
            }
        }

        var size = backend.fitToScreen(wantedX, wantedY, wantedWidth, wantedHeight);
        width = Math.max(minimumWidth, size.width);
        height = Math.max(minimumHeight, size.height);

        // Never restore maximized. The faceplate is a fixed proportion; filling
        // the screen stretches it, and a stale `window/maximized` flag (left
        // by the oversized-window bug) had no way to clear itself: this
        // branch re-maximized, then onDestruction wrote the flag back.
    }

    Component.onDestruction: {
        if (!backend.isMobile)
            backend.saveWindowGeometry(
                normalGeometry.x, normalGeometry.y,
                normalGeometry.width, normalGeometry.height, wasMaximized)
    }
}
