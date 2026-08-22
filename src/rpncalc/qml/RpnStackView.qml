import QtQuick

// The RPN stack, drawn the way the 50g draws it: level 1 sits at the bottom,
// just above the command line, with higher levels stacked above it. Only as
// many levels as fit are shown - the stack itself is unbounded.
Item {
    id: root

    property var lines: []          // formatted levels, level 1 first
    property string commandLine: ""
    property bool entering: false
    property color inkColor: "#eeeeee"
    property color mutedColor: "#888888"
    property int fontPixelSize: 18
    property int rowSpacing: 2

    readonly property int rowHeight: Math.round(fontPixelSize * 1.35) + rowSpacing
    // The command line, when open, takes the bottom row for itself.
    readonly property int levelRows: Math.max(
        1, Math.floor(height / rowHeight) - (entering ? 1 : 0))

    readonly property var visibleLevels: {
        var out = [];
        for (var i = levelRows - 1; i >= 0; --i)
            out.push({ level: i + 1, text: i < lines.length ? lines[i] : "" });
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

                Text {
                    id: levelLabel
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.level + ":"
                    color: root.mutedColor
                    font.family: "iA Writer Mono S"
                    font.pixelSize: root.fontPixelSize
                }

                Text {
                    anchors.left: levelLabel.right
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
