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

    Shortcut {
        sequences: ["Ctrl+C", "Meta+C"]
        context: Qt.ApplicationShortcut
        onActivated: backend.copyResult()
    }

    Shortcut {
        sequences: ["Ctrl+V", "Meta+V"]
        context: Qt.ApplicationShortcut
        onActivated: backend.pasteNumber()
    }

    Shortcut {
        sequence: "Ctrl+Z"
        context: Qt.ApplicationShortcut
        onActivated: backend.pressCommand("undo")
    }

    Shortcut {
        sequence: "Ctrl+M"
        context: Qt.ApplicationShortcut
        onActivated: backend.toggleEntryMode()
    }

    Shortcut {
        sequence: "Ctrl+Q"
        context: Qt.ApplicationShortcut
        onActivated: win.close()
    }

    Item {
        id: face
        anchors.fill: parent
        anchors.margins: win.scaledSize(16)
        focus: true

        // The physical keyboard drives commands directly rather than pretending
        // to press keycaps: shift planes are reached with Alt (left) and
        // Ctrl+Alt (right), which no keycap can express.
        Keys.onPressed: function(event) {
            if (event.modifiers & Qt.ControlModifier) {
                return;  // reserved for the Shortcuts above
            }

            var command = "";
            if (event.modifiers & Qt.AltModifier) {
                switch (event.text.toLowerCase()) {
                case "s": command = "sqrt"; break;
                case "q": command = "sq"; break;
                case "l": command = "ln"; break;
                case "e": command = "exp"; break;
                case "g": command = "log"; break;
                case "i": command = "inv"; break;
                case "p": command = "pi"; break;
                case "a": command = "abs"; break;
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
                command = "clear_entry";
            } else if (event.key === Qt.Key_Escape) {
                command = "clear";
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
                visible: backend.rpnMode
                lines: backend.stackLines
                commandLine: backend.commandLine
                entering: backend.entering
                cursorLevel: backend.cursorLevel
                inkColor: win.inkColor
                mutedColor: win.mutedColor
                fontPixelSize: win.scaledSize(20)
                rowSpacing: win.scaledSize(3)
            }

            SoftMenu {
                id: softMenu
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                labels: backend.rpnMode ? backend.menuLabels : []
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
                visible: !backend.rpnMode

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

        // The 50g's lower keyboard: seven rows of five, same face in both modes,
        // exactly as the real calculator does it.
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
                    required property var modelData

                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: win.scaledSize(7)

                    Repeater {
                        model: parent.modelData

                        CalcButton {
                            required property var modelData

                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            label: modelData.label
                            keyValue: modelData.keyId
                            kind: modelData.style
                            iconName: modelData.icon
                            labelLeft: modelData.labelLeft
                            labelRight: modelData.labelRight
                            alphaLabel: modelData.alpha
                            live: modelData.live
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

    onVisibilityChanged: {
        if (visibility === Window.Maximized || visibility === Window.FullScreen)
            wasMaximized = true;
        else if (visibility === Window.Windowed)
            wasMaximized = false;
    }

    Component.onCompleted: {
        var geometry = backend.windowGeometry();
        if (geometry.valid) {
            x = geometry.x;
            y = geometry.y;
            width = geometry.width;
            height = geometry.height;
            if (geometry.maximized) showMaximized();
        } else {
            // First run: open at the design size, grown by the desktop text scale.
            width = Math.round(420 * backend.textScale);
            height = Math.round(820 * backend.textScale);
        }
    }

    Component.onDestruction: backend.saveWindowGeometry(
        normalGeometry.x, normalGeometry.y,
        normalGeometry.width, normalGeometry.height, wasMaximized)
}
