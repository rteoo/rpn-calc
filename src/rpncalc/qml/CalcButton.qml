import QtQuick

// One keyboard cell: the shift legends printed on the faceplate above the cap,
// and the cap itself. Cap treatment is omacalc's - numbers sit almost flush
// with the page, operators lift a step lighter - with the yellow shift key
// standing out from them.
//
// Shift legends are yellow on both sides of the cap — one shift plane.
Item {
    id: control

    property string label
    property string keyValue: label
    property string kind: "number" // number | operator | enter | shift_right | nav
    property string iconName
    property string labelLeft
    property string labelRight
    property string armedShift: "none"
    property bool live: true
    property bool hoverEnabled: true
    property color pageColor: "#101010"
    property color inkColor: "#eeeeee"
    property color rightShiftColor: "#f0c419"
    property int legendPixelSize: 9

    signal activated()

    function mixColors(base, tint, amount) {
        return Qt.rgba(
            base.r + (tint.r - base.r) * amount,
            base.g + (tint.g - base.g) * amount,
            base.b + (tint.b - base.b) * amount, 1);
    }

    // An armed shift brightens its own legends and pushes the other plane back,
    // so the next keypress can be read off the face instead of from memory.
    function legendOpacity(plane) {
        if (armedShift === "none")
            return 0.62;
        return armedShift === plane ? 1.0 : 0.22;
    }

    Item {
        id: legends
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: Math.round(control.legendPixelSize * 1.5)

        Text {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(implicitWidth, parent.width * 0.55)
            text: control.labelLeft
            color: control.rightShiftColor
            opacity: control.legendOpacity("right")
            elide: Text.ElideRight
            font.family: "iA Writer Mono S"
            font.pixelSize: control.legendPixelSize
        }

        Text {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(implicitWidth, parent.width * 0.55)
            text: control.labelRight
            color: control.rightShiftColor
            opacity: control.legendOpacity("right")
            elide: Text.ElideRight
            font.family: "iA Writer Mono S"
            font.pixelSize: control.legendPixelSize
        }
    }

    Rectangle {
        id: cap
        anchors.top: legends.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom

        readonly property real restingLift: control.kind === "operator" ? 0.16 : 0.05
        readonly property real activeLift: restingLift
            + (hitArea.pressed ? 0.09 : (hitArea.containsMouse ? 0.045 : 0))
        readonly property bool armed:
            control.kind === "shift_right" && control.armedShift === "right"
        readonly property color capInk:
            (control.kind === "enter" || control.kind === "shift_right")
                ? control.pageColor : control.inkColor

        radius: Math.min(14, height * 0.18)
        opacity: control.live ? 1.0 : 0.38
        color: {
            if (control.kind === "shift_right")
                return control.rightShiftColor;
            if (control.kind === "enter")
                return control.mixColors(control.inkColor, control.pageColor,
                    hitArea.pressed ? 0.22 : (hitArea.containsMouse ? 0.1 : 0));
            return control.mixColors(control.pageColor, control.inkColor, activeLift);
        }
        border.width: armed ? 2 : (control.kind === "number" ? 1 : 0)
        border.color: armed
            ? control.rightShiftColor
            : control.mixColors(control.pageColor, control.inkColor, 0.13)

        Text {
            anchors.left: parent.left
            anchors.leftMargin: Math.round(parent.width * 0.04)
            anchors.right: parent.right
            anchors.rightMargin: Math.round(parent.width * 0.04)
            anchors.verticalCenter: parent.verticalCenter
            horizontalAlignment: Text.AlignHCenter
            visible: control.iconName === "" && control.kind !== "shift_right"
                     && control.label !== ""
            text: control.label
            color: cap.capInk
            elide: Text.ElideRight
            font.family: "iA Writer Mono S"
            font.pixelSize: Math.round(Math.min(
                parent.height * 0.44,
                width / Math.max(1, control.label.length) / 0.62))
        }

        // iA Writer Mono has no double-arrow glyph, so the shift keys get their
        // arrow drawn rather than typed - the same trick omacalc uses for its
        // backspace icon.
        Canvas {
            id: shiftIcon
            anchors.centerIn: parent
            width: Math.round(parent.width * 0.34)
            height: Math.round(width * 0.8)
            visible: control.kind === "shift_right"

            onPaint: {
                // Yellow shift key: an up-pointing arrow, matching the outline.
                var context = getContext("2d");
                var w = width;
                var h = height;
                context.clearRect(0, 0, w, h);
                context.fillStyle = String(cap.capInk);
                context.beginPath();
                context.moveTo(w / 2, 0);
                context.lineTo(w, h * 0.55);
                context.lineTo(w * 0.68, h * 0.55);
                context.lineTo(w * 0.68, h);
                context.lineTo(w * 0.32, h);
                context.lineTo(w * 0.32, h * 0.55);
                context.lineTo(0, h * 0.55);
                context.closePath();
                context.fill();
            }

            Connections {
                target: cap
                function onWidthChanged() { shiftIcon.requestPaint(); }
                function onHeightChanged() { shiftIcon.requestPaint(); }
                function onCapInkChanged() { shiftIcon.requestPaint(); }
            }
        }

        // Direction arrows, drawn for the same reason the shift arrows are:
        // the glyphs do not exist in the bundled font.
        Canvas {
            id: arrowIcon
            anchors.centerIn: parent
            width: Math.round(Math.min(parent.height, parent.width) * 0.34)
            height: width
            visible: ["up", "down", "left", "right"].indexOf(control.iconName) !== -1

            onPaint: {
                var context = getContext("2d");
                var w = width;
                var h = height;
                context.clearRect(0, 0, w, h);
                context.fillStyle = String(cap.capInk);
                context.beginPath();
                switch (control.iconName) {
                case "up":
                    context.moveTo(w / 2, 0); context.lineTo(w, h); context.lineTo(0, h);
                    break;
                case "down":
                    context.moveTo(w / 2, h); context.lineTo(w, 0); context.lineTo(0, 0);
                    break;
                case "left":
                    context.moveTo(0, h / 2); context.lineTo(w, 0); context.lineTo(w, h);
                    break;
                default:
                    context.moveTo(w, h / 2); context.lineTo(0, 0); context.lineTo(0, h);
                }
                context.closePath();
                context.fill();
            }

            Connections {
                target: cap
                function onWidthChanged() { arrowIcon.requestPaint(); }
                function onHeightChanged() { arrowIcon.requestPaint(); }
                function onCapInkChanged() { arrowIcon.requestPaint(); }
            }
        }

        Canvas {
            id: backspaceIcon
            anchors.centerIn: parent
            width: Math.round(Math.min(parent.height * 0.42, parent.width * 0.3) * 1.3)
            height: Math.round(width * 0.72)
            visible: control.iconName === "backspace"

            onPaint: {
                var context = getContext("2d");
                var w = width;
                var h = height;
                var notch = w * 0.28;
                context.clearRect(0, 0, w, h);
                context.strokeStyle = String(cap.capInk);
                context.lineWidth = Math.max(1.4, w * 0.07);
                context.lineCap = "round";
                context.lineJoin = "round";

                // The key cap: a rectangle whose left edge tapers to a point.
                context.beginPath();
                context.moveTo(notch, 1);
                context.lineTo(w - 1, 1);
                context.lineTo(w - 1, h - 1);
                context.lineTo(notch, h - 1);
                context.lineTo(1, h / 2);
                context.closePath();
                context.stroke();

                // The x inside.
                var cx = notch + (w - notch) / 2;
                var cy = h / 2;
                var arm = h * 0.18;
                context.beginPath();
                context.moveTo(cx - arm, cy - arm);
                context.lineTo(cx + arm, cy + arm);
                context.moveTo(cx + arm, cy - arm);
                context.lineTo(cx - arm, cy + arm);
                context.stroke();
            }

            Connections {
                target: control
                function onInkColorChanged() { backspaceIcon.requestPaint(); }
            }
            Connections {
                target: cap
                function onWidthChanged() { backspaceIcon.requestPaint(); }
                function onHeightChanged() { backspaceIcon.requestPaint(); }
            }
        }

        MouseArea {
            id: hitArea
            anchors.fill: parent
            hoverEnabled: control.hoverEnabled
            enabled: control.live
            onClicked: control.activated()
        }
    }

    Accessible.role: Accessible.Button
    Accessible.name: {
        if (iconName === "backspace") return "Backspace or drop";
        if (kind === "shift_right") return "Shift";
        if (label === "ENTER") return "Enter";
        if (label === "÷") return "Divide";
        if (label === "×") return "Multiply";
        if (label === "−") return "Subtract";
        if (label === "+") return "Add";
        if (label === "+/−") return "Change sign";
        return label;
    }
    Accessible.onPressAction: activated()
}
