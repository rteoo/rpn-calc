import QtQuick

// The 50g draws its soft-menu labels along the bottom of the screen, with six
// unlabelled keys underneath. There is no room on this face for another key
// row, so the labels are the buttons - and F1..F6 press them from the keyboard.
//
// The strip only exists while a menu does; the rest of the time the stack gets
// the space back.
Item {
    id: root

    property var labels: []
    property var slotEnabled: []
    property color pageColor: "#101010"
    property color inkColor: "#eeeeee"
    property int fontPixelSize: 11

    signal activated(int index)

    readonly property bool showing: labels.length > 0
    implicitHeight: showing ? Math.round(fontPixelSize * 2.0) : 0
    visible: showing

    function mixColors(base, tint, amount) {
        return Qt.rgba(
            base.r + (tint.r - base.r) * amount,
            base.g + (tint.g - base.g) * amount,
            base.b + (tint.b - base.b) * amount, 1);
    }

    Row {
        anchors.fill: parent
        spacing: Math.max(1, Math.round(root.fontPixelSize * 0.25))

        Repeater {
            model: root.labels

            Item {
                required property var modelData
                required property int index

                width: (root.width - (root.labels.length - 1)
                        * Math.max(1, Math.round(root.fontPixelSize * 0.25)))
                       / root.labels.length
                height: root.height

                readonly property bool live:
                    index < root.slotEnabled.length ? root.slotEnabled[index] : true

                Rectangle {
                    anchors.fill: parent
                    radius: Math.round(root.fontPixelSize * 0.25)
                    // Inverted labels, as the calculator draws them.
                    color: root.inkColor
                    opacity: !parent.live ? 0.25 : (hit.pressed ? 0.72 : 1.0)
                }

                Text {
                    anchors.centerIn: parent
                    width: parent.width - root.fontPixelSize * 0.4
                    horizontalAlignment: Text.AlignHCenter
                    text: modelData
                    color: root.pageColor
                    elide: Text.ElideRight
                    font.family: "iA Writer Mono S"
                    font.pixelSize: root.fontPixelSize
                }

                MouseArea {
                    id: hit
                    anchors.fill: parent
                    enabled: parent.live
                    onClicked: root.activated(index)
                }

                Accessible.role: Accessible.Button
                Accessible.name: modelData
                Accessible.onPressAction: root.activated(index)
            }
        }
    }
}
