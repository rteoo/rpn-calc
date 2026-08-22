import QtQuick

// The RPN stack, drawn the way the 50g draws it: level 1 sits at the bottom,
// just above the command line, with higher levels stacked above it. Only as
// many levels as fit are shown - the stack itself is unbounded.
Item {
    id: root

    property var lines: []          // formatted levels, level 1 first
    property string commandLine: ""
    property bool entering: false
    property int cursorLevel: 0     // 0 = the interactive stack is closed
    property color inkColor: "#eeeeee"
    property color mutedColor: "#888888"
    property int fontPixelSize: 18
    property int rowSpacing: 2

    readonly property int rowHeight: Math.round(fontPixelSize * 1.35) + rowSpacing
    // The command line, when open, takes the bottom row for itself.
    readonly property int levelRows: Math.max(
        1, Math.floor(height / rowHeight) - (entering ? 1 : 0))

    // Walking the cursor deeper than the window is tall has to scroll, or the
    // selected level would sit off-screen with nothing to show for the keypress.
    readonly property int firstLevel:
        Math.max(1, cursorLevel - levelRows + 1)

    readonly property var visibleLevels: {
        var out = [];
        for (var i = levelRows - 1; i >= 0; --i) {
            var level = firstLevel + i;
            out.push({
                level: level,
                text: level - 1 < lines.length ? lines[level - 1] : "",
                selected: level === cursorLevel
            });
        }
        return out;
    }

    Column {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        spacing: root.rowSpacing

        Repeater {
            model: root.visibleLevels

            Item {
                width: root.width
                height: root.rowHeight - root.rowSpacing

                // The selected row is banded rather than merely marked: on a
                // deep stack the pointer alone is easy to lose track of.
                Rectangle {
                    anchors.fill: parent
                    anchors.leftMargin: -root.fontPixelSize * 0.3
                    anchors.rightMargin: -root.fontPixelSize * 0.3
                    radius: root.fontPixelSize * 0.2
                    visible: modelData.selected
                    color: root.inkColor
                    opacity: 0.12
                }

                Text {
                    id: levelLabel
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.level + ":"
                    color: modelData.selected ? root.inkColor : root.mutedColor
                    font.family: "iA Writer Mono S"
                    font.pixelSize: root.fontPixelSize
                }

                // The 50g's cursor: a filled triangle where the colon would be.
                Canvas {
                    id: cursor
                    anchors.left: levelLabel.right
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.round(root.fontPixelSize * 0.5)
                    height: Math.round(root.fontPixelSize * 0.62)
                    visible: modelData.selected

                    onPaint: {
                        var context = getContext("2d");
                        context.clearRect(0, 0, width, height);
                        context.fillStyle = String(root.inkColor);
                        context.beginPath();
                        context.moveTo(0, 0);
                        context.lineTo(width, height / 2);
                        context.lineTo(0, height);
                        context.closePath();
                        context.fill();
                    }

                    Connections {
                        target: root
                        function onInkColorChanged() { cursor.requestPaint(); }
                        function onFontPixelSizeChanged() { cursor.requestPaint(); }
                    }
                }

                Text {
                    anchors.left: cursor.right
                    anchors.leftMargin: root.fontPixelSize / 2
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    horizontalAlignment: Text.AlignRight
                    text: modelData.text
                    color: root.inkColor
                    elide: Text.ElideLeft
                    font.family: "iA Writer Mono S"
                    font.pixelSize: root.fontPixelSize
                }
            }
        }

        Item {
            width: root.width
            visible: root.entering
            height: visible ? root.rowHeight - root.rowSpacing : 0

            Text {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                horizontalAlignment: Text.AlignLeft
                text: root.commandLine
                color: root.inkColor
                elide: Text.ElideLeft
                font.family: "iA Writer Mono S"
                font.pixelSize: root.fontPixelSize
            }

            // A blinking cursor is the clearest signal that the command line is
            // open, which is what decides whether ENTER duplicates or pushes.
            Rectangle {
                id: cursor
                anchors.verticalCenter: parent.verticalCenter
                x: Math.min(root.width - width,
                            root.commandLine.length * root.fontPixelSize * 0.6)
                width: Math.max(1, Math.round(root.fontPixelSize * 0.09))
                height: root.fontPixelSize
                color: root.inkColor

                SequentialAnimation on opacity {
                    running: root.entering
                    loops: Animation.Infinite
                    PropertyAnimation { to: 0; duration: 500 }
                    PropertyAnimation { to: 1; duration: 500 }
                }
            }
        }
    }
}
