import QtQuick

// The 50g's header line: angle mode, display format, and the active entry mode,
// with errors taking over the row when there is one to show.
Item {
    id: root

    property string angleMode: "RAD"
    property string numberFormat: "STD"
    property string entryMode: "RPN"
    property string errorText: ""
    property color mutedColor: "#888888"
    property color errorColor: "#e05252"
    property int fontPixelSize: 14

    implicitHeight: Math.round(fontPixelSize * 1.5)

    Text {
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        visible: root.errorText === ""
        text: [root.angleMode, root.numberFormat].join("  ")
        color: root.mutedColor
        font.family: "iA Writer Mono S"
        font.pixelSize: root.fontPixelSize
    }

    Text {
        anchors.left: parent.left
        anchors.right: modeLabel.left
        anchors.rightMargin: root.fontPixelSize
        anchors.verticalCenter: parent.verticalCenter
        visible: root.errorText !== ""
        text: root.errorText
        color: root.errorColor
        elide: Text.ElideRight
        font.family: "iA Writer Mono S"
        font.pixelSize: root.fontPixelSize
    }

    Text {
        id: modeLabel
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: root.entryMode
        color: root.mutedColor
        font.family: "iA Writer Mono S"
        font.pixelSize: root.fontPixelSize
    }
}
