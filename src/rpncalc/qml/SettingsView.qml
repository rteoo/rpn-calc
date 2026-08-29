import QtQuick
import QtQuick.Layouts

// Host options that used to live in a right-click Material menu. MENU on the
// face opens this panel inside the display; ▲ still owns the stack browser.
Item {
    id: root

    property var rows: []
    property int cursor: 0
    property color inkColor: "#eeeeee"
    property color mutedColor: "#888888"
    property color pageColor: "#101010"
    property int fontPixelSize: 16
    property int titlePixelSize: 13

    signal rowActivated(int index)

    clip: true

    function mixColors(base, tint, amount) {
        return Qt.rgba(
            base.r + (tint.r - base.r) * amount,
            base.g + (tint.g - base.g) * amount,
            base.b + (tint.b - base.b) * amount, 1);
    }

    function rowAt(index) {
        return index < root.rows.length ? root.rows[index] : null
    }

    component SettingsRow: Item {
        property var row: null
        property int rowIndex: -1
        property string rowObjectName: ""

        Layout.fillWidth: true
        Layout.preferredHeight: Math.round(root.fontPixelSize * 1.45)
        opacity: (row && row.enabled) ? 1.0 : 0.38

        readonly property bool selected: rowIndex === root.cursor

        Rectangle {
            anchors.fill: parent
            color: parent.selected
                   ? root.mixColors(root.pageColor, root.inkColor, 0.18)
                   : "transparent"
            radius: 2
        }

        readonly property bool isValueRow: row && row.kind === "value"

        Rectangle {
            id: box
            anchors.left: parent.left
            anchors.leftMargin: 4
            anchors.verticalCenter: parent.verticalCenter
            width: Math.round(root.fontPixelSize * 0.9)
            height: width
            radius: 2
            // A setting that walks a ladder has no box to tick; the row keeps
            // the same left inset so every label still starts on one line.
            visible: !parent.isValueRow
            color: "transparent"
            border.color: root.inkColor
            border.width: Math.max(1, Math.round(root.fontPixelSize * 0.08))

            Text {
                anchors.centerIn: parent
                visible: row && row.checked
                text: "✓"
                color: root.inkColor
                font.family: "iA Writer Mono S"
                font.pixelSize: Math.round(root.fontPixelSize * 0.75)
            }
        }

        Text {
            id: rowValue
            anchors.right: parent.right
            anchors.rightMargin: 4
            anchors.verticalCenter: parent.verticalCenter
            visible: parent.isValueRow
            text: row ? row.value : ""
            color: root.inkColor
            font.family: "iA Writer Mono S"
            font.pixelSize: root.fontPixelSize
        }

        Text {
            objectName: rowObjectName
            anchors.left: box.right
            anchors.leftMargin: Math.round(root.fontPixelSize * 0.45)
            anchors.right: rowValue.visible ? rowValue.left : parent.right
            anchors.rightMargin: Math.round(root.fontPixelSize * 0.45)
            anchors.verticalCenter: parent.verticalCenter
            text: row ? row.label : ""
            color: root.inkColor
            elide: Text.ElideRight
            font.family: "iA Writer Mono S"
            font.pixelSize: root.fontPixelSize
            property bool checked: row ? row.checked : false
        }

        MouseArea {
            anchors.fill: parent
            enabled: row && row.enabled
            onClicked: root.rowActivated(rowIndex)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Math.round(root.fontPixelSize * 0.35)

        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: "SETTINGS"
            color: root.mutedColor
            font.family: "iA Writer Mono S"
            font.pixelSize: root.titlePixelSize
        }

        SettingsRow {
            row: root.rowAt(0)
            rowIndex: 0
            rowObjectName: "decimalCommaItem"
        }
        SettingsRow {
            row: root.rowAt(1)
            rowIndex: 1
            rowObjectName: "thousandsItem"
        }
        SettingsRow {
            row: root.rowAt(2)
            rowIndex: 2
            rowObjectName: "digitsItem"
        }
        SettingsRow {
            row: root.rowAt(3)
            rowIndex: 3
            rowObjectName: "calculatorKeyItem"
        }

        Item { Layout.fillHeight: true }

        Text {
            Layout.fillWidth: true
            text: "ENTER toggles · arrows adjust · MENU closes"
            color: root.mutedColor
            font.family: "iA Writer Mono S"
            font.pixelSize: Math.round(root.fontPixelSize * 0.75)
        }
    }
}
