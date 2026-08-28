import QtQuick
import QtQuick.Layouts

// HP 50g-style TVM form. Two columns so the seven registers fit above the
// soft menu instead of overflowing onto the keypad (a single Column of
// seven rows was taller than the display once EDIT/AMOR/SOLVE appeared).
Item {
    id: root

    property var fields: []
    property int cursor: 0
    property string entry: ""
    property color inkColor: "#eeeeee"
    property color mutedColor: "#888888"
    property color pageColor: "#101010"
    property int fontPixelSize: 18
    property int titlePixelSize: 14

    clip: true

    function mixColors(base, tint, amount) {
        return Qt.rgba(
            base.r + (tint.r - base.r) * amount,
            base.g + (tint.g - base.g) * amount,
            base.b + (tint.b - base.b) * amount, 1);
    }

    function fieldAt(index) {
        return index < root.fields.length ? root.fields[index] : null
    }

    // One register cell: label on the left, value on the right.
    component FieldCell: Item {
        property var field: null
        property int fieldIndex: -1
        property bool selected: fieldIndex === root.cursor

        implicitHeight: Math.round(root.fontPixelSize * 1.35)

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
            text: parent.field ? parent.field.label : ""
            color: root.inkColor
            font.family: "iA Writer Mono S"
            font.pixelSize: root.fontPixelSize
        }

        Text {
            anchors.right: parent.right
            anchors.rightMargin: 4
            anchors.verticalCenter: parent.verticalCenter
            text: parent.field ? parent.field.value : ""
            color: root.inkColor
            font.family: "iA Writer Mono S"
            font.pixelSize: root.fontPixelSize
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Math.round(root.fontPixelSize * 0.2)

        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: "TIME VALUE OF MONEY"
            color: root.mutedColor
            font.family: "iA Writer Mono S"
            font.pixelSize: root.titlePixelSize
        }

        // N / I%YR
        RowLayout {
            Layout.fillWidth: true
            spacing: Math.round(root.fontPixelSize * 0.5)
            FieldCell {
                Layout.fillWidth: true
                field: root.fieldAt(0)
                fieldIndex: 0
            }
            FieldCell {
                Layout.fillWidth: true
                field: root.fieldAt(1)
                fieldIndex: 1
            }
        }

        // PV alone (left column)
        RowLayout {
            Layout.fillWidth: true
            spacing: Math.round(root.fontPixelSize * 0.5)
            FieldCell {
                Layout.fillWidth: true
                field: root.fieldAt(2)
                fieldIndex: 2
            }
            Item { Layout.fillWidth: true }
        }

        // PMT / P/YR
        RowLayout {
            Layout.fillWidth: true
            spacing: Math.round(root.fontPixelSize * 0.5)
            FieldCell {
                Layout.fillWidth: true
                field: root.fieldAt(3)
                fieldIndex: 3
            }
            FieldCell {
                Layout.fillWidth: true
                field: root.fieldAt(5)
                fieldIndex: 5
            }
        }

        // FV / Begin|End
        RowLayout {
            Layout.fillWidth: true
            spacing: Math.round(root.fontPixelSize * 0.5)
            FieldCell {
                Layout.fillWidth: true
                field: root.fieldAt(4)
                fieldIndex: 4
            }
            FieldCell {
                Layout.fillWidth: true
                field: root.fieldAt(6)
                fieldIndex: 6
            }
        }

        Item { Layout.fillHeight: true }

        // The entry line the form types into. It is the ordinary command
        // line: the form has to draw it, because it hides the stack view
        // that would otherwise be showing what is being typed.
        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignRight
            rightPadding: 4
            visible: root.entry !== ""
            text: root.entry + "_"
            color: root.inkColor
            font.family: "iA Writer Mono S"
            font.pixelSize: root.fontPixelSize
        }

        Text {
            Layout.fillWidth: true
            text: root.entry !== "" ? "ENTER stores into the field"
                                    : "Type a value, or SOLVE"
            color: root.mutedColor
            font.family: "iA Writer Mono S"
            font.pixelSize: Math.round(root.fontPixelSize * 0.75)
        }
    }
}
