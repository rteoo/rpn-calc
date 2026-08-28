import QtQuick

// One caption on a keycap: the cap itself, or either shift legend.
//
// Plain Text is not enough for this faceplate, because iA Writer Mono is
// missing more than you would expect - it carries exactly one Greek letter,
// π, and no superscripts at all. Three cases:
//
//  - `Σ+`, `CLΣ`, `Δ%`: Σ and Δ are *drawn*, the same way the shift arrow,
//    the direction arrows and the backspace icon already are. A missing glyph
//    does not raise; it draws an empty box, so it survives every headless
//    test and only shows up on the face.
//  - `y<sup>x</sup>`: no superscript glyph either, so the exponent is markup
//    rendered as rich text, which raises the font's own `x`.
//  - everything else: ordinary text, the cheap path.
//
// The per-character layout the drawn case needs is only reasonable because
// the face is monospaced: every cell is one advance wide.
Item {
    id: root

    property string caption: ""
    property color inkColor: "#eeeeee"
    property int pixelSize: 12
    // 0 leaves the caption unconstrained; anything else elides plain text to
    // fit. Rich text is never elided - Qt cannot, and asking silently
    // truncated `eˣ` down to a bare `e`.
    property real maxWidth: 0
    property int horizontalAlignment: Text.AlignHCenter

    readonly property var drawnGlyphs: ["Σ", "Δ"]
    readonly property bool hasDrawnGlyph: {
        for (var i = 0; i < drawnGlyphs.length; i++)
            if (caption.indexOf(drawnGlyphs[i]) >= 0)
                return true;
        return false;
    }
    readonly property bool isRich: caption.indexOf("<") >= 0
    // What a screen reader should say, and what the cap auto-size measures.
    readonly property string plainText: caption.replace(/<[^>]*>/g, "")

    // Counted, not measured off the Row: the Row anchors to this item, so
    // taking its width back as our implicit width is a binding loop, and Qt
    // breaks it by leaving the drawn glyphs at zero size - the legends came
    // out as a bare "CL" and "−" with the Σ simply absent.
    implicitWidth: hasDrawnGlyph
                   ? caption.length * metrics.advanceWidth("0")
                   : plainLabel.implicitWidth
    implicitHeight: Math.round(pixelSize * 1.3)

    FontMetrics {
        id: metrics
        font.family: "iA Writer Mono S"
        font.pixelSize: root.pixelSize
    }

    // -- the ordinary and rich-text cases ----------------------------------

    Text {
        id: plainLabel
        anchors.fill: parent
        visible: !root.hasDrawnGlyph
        text: root.caption
        textFormat: root.isRich ? Text.RichText : Text.PlainText
        color: root.inkColor
        elide: (root.isRich || root.maxWidth <= 0) ? Text.ElideNone
                                                   : Text.ElideRight
        horizontalAlignment: root.horizontalAlignment
        verticalAlignment: Text.AlignVCenter
        font.family: "iA Writer Mono S"
        font.pixelSize: root.pixelSize
    }

    // -- the drawn case ----------------------------------------------------

    Row {
        id: glyphRow
        visible: root.hasDrawnGlyph
        height: parent.height
        anchors.horizontalCenter:
            root.horizontalAlignment === Text.AlignHCenter
            ? parent.horizontalCenter : undefined
        anchors.left: root.horizontalAlignment === Text.AlignLeft
                      ? parent.left : undefined
        anchors.right: root.horizontalAlignment === Text.AlignRight
                       ? parent.right : undefined

        Repeater {
            model: root.hasDrawnGlyph ? root.caption.split("") : []

            Item {
                required property string modelData

                readonly property bool drawn:
                    root.drawnGlyphs.indexOf(modelData) >= 0
                width: metrics.advanceWidth("0")
                height: glyphRow.height

                Text {
                    anchors.fill: parent
                    visible: !parent.drawn
                    text: parent.modelData
                    color: root.inkColor
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    font.family: "iA Writer Mono S"
                    font.pixelSize: root.pixelSize
                }

                Canvas {
                    id: drawnGlyph
                    anchors.centerIn: parent
                    visible: parent.drawn
                    // Matched to the font's own capital height and stem, so a
                    // drawn Σ sits on the same baseline as the + beside it.
                    width: Math.round(root.pixelSize * 0.62)
                    height: Math.round(root.pixelSize * 0.72)
                    antialiasing: true

                    onPaint: {
                        var context = getContext("2d");
                        context.clearRect(0, 0, width, height);
                        context.strokeStyle = String(root.inkColor);
                        context.lineWidth = Math.max(1, root.pixelSize * 0.075);
                        context.lineJoin = "miter";
                        context.beginPath();
                        var inset = context.lineWidth / 2;
                        if (parent.modelData === "Δ") {
                            context.moveTo(inset, height - inset);
                            context.lineTo(width / 2, inset);
                            context.lineTo(width - inset, height - inset);
                            context.closePath();
                        } else {
                            // Σ: top bar, in to the waist, back out, bottom bar.
                            context.moveTo(width - inset, inset);
                            context.lineTo(inset, inset);
                            context.lineTo(width * 0.62, height / 2);
                            context.lineTo(inset, height - inset);
                            context.lineTo(width - inset, height - inset);
                        }
                        context.stroke();
                    }

                    Connections {
                        target: root
                        function onInkColorChanged() { drawnGlyph.requestPaint(); }
                        function onPixelSizeChanged() { drawnGlyph.requestPaint(); }
                    }
                }
            }
        }
    }
}
