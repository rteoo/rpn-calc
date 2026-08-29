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

        implicitHeight: Math.round(root.fontPixelSize * 1.2)

        Rectangle {
            anchors.fill: parent
            color: parent.selected
                   ? root.mixColors(root.pageColor, root.inkColor, 0.18)
                   : "transparent"
            radius: 2
        }

        Text {
            id: cellLabel
            anchors.left: parent.left
            anchors.leftMargin: 4
            anchors.verticalCenter: parent.verticalCenter
            text: parent.field ? parent.field.label : ""
            color: root.inkColor
            font.family: "iA Writer Mono S"
            font.pixelSize: root.fontPixelSize
        }

        // Bounded by the label rather than free to run under it. A solved
        // value carries full precision - FV on a 12-period 12% problem is
        // 1126.82503013197 - which is wider than half the display, and used
        // to draw straight through "FV:" as "FM26.82503013197". It shrinks
        // to fit and only elides once there is nothing left to give.
        Text {
            anchors.left: cellLabel.right
            anchors.leftMargin: 6
            anchors.right: parent.right
            anchors.rightMargin: 4
            anchors.verticalCenter: parent.verticalCenter
            horizontalAlignment: Text.AlignRight
            text: parent.field ? parent.field.value : ""
            color: root.inkColor
            elide: Text.ElideRight
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: Math.round(root.fontPixelSize * 0.55)
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

        // One line, not two. The entry line the form types into - it is the
        // ordinary command line, and the form has to draw it because it hides
        // the stack view that would otherwise show it - and the hint are
        // alternatives, and stacking them needed 178px of a 151px form, so
        // `clip: true` sliced the entry in half exactly when it mattered.
        Text {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.round(root.fontPixelSize * 1.2)
            verticalAlignment: Text.AlignVCenter
            horizontalAlignment: root.entry !== "" ? Text.AlignRight
                                                   : Text.AlignLeft
            rightPadding: 4
            text: root.entry !== "" ? root.entry + "_" : "Type a value, or SOLVE"
            color: root.entry !== "" ? root.inkColor : root.mutedColor
            elide: Text.ElideLeft
            font.family: "iA Writer Mono S"
            font.pixelSize: root.entry !== ""
                            ? root.fontPixelSize
                            : Math.round(root.fontPixelSize * 0.75)
        }
    }
}
