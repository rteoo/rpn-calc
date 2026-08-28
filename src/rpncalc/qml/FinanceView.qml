import QtQuick

// HP 50g-style TVM form: TIME VALUE OF MONEY registers with a cursor.
// Soft-menu EDIT / AMOR / SOLVE is owned by SoftMenu in Main.qml.
Item {
    id: root

    property var fields: []
    property int cursor: 0
    property color inkColor: "#eeeeee"
    property color mutedColor: "#888888"
    property color pageColor: "#101010"
    property int fontPixelSize: 18
    property int titlePixelSize: 14

    function mixColors(base, tint, amount) {
        return Qt.rgba(
            base.r + (tint.r - base.r) * amount,
            base.g + (tint.g - base.g) * amount,
            base.b + (tint.b - base.b) * amount, 1);
    }

    Column {
        anchors.fill: parent
        spacing: Math.round(root.fontPixelSize * 0.25)

        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: "TIME VALUE OF MONEY"
            color: root.mutedColor
            font.family: "iA Writer Mono S"
            font.pixelSize: root.titlePixelSize
        }

        Repeater {
            model: root.fields

            Item {
                required property var modelData
                required property int index

                width: parent.width
                height: Math.round(root.fontPixelSize * 1.35)

                readonly property bool selected: index === root.cursor

                Rectangle {
                    anchors.fill: parent
                    color: parent.selected
                           ? root.mixColors(root.pageColor, root.inkColor, 0.18)
                           : "transparent"
                    radius: 2
                }

                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 4
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.label
                    color: root.inkColor
                    font.family: "iA Writer Mono S"
                    font.pixelSize: root.fontPixelSize
                }

                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 4
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.value
                    color: root.inkColor
                    font.family: "iA Writer Mono S"
                    font.pixelSize: root.fontPixelSize
                }
            }
        }

        Text {
            width: parent.width
            topPadding: Math.round(root.fontPixelSize * 0.4)
            text: "Enter value or SOLVE"
            color: root.mutedColor
            font.family: "iA Writer Mono S"
            font.pixelSize: Math.round(root.fontPixelSize * 0.75)
        }
    }
}
