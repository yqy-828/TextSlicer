#target photoshop
app.displayDialogs = DialogModes.NO;
var previousRulerUnits = app.preferences.rulerUnits;
app.preferences.rulerUnits = Units.PIXELS;

function readTextFile(path) {
    var file = File(path);
    if (!file.exists) {
        throw new Error("Missing manifest: " + path);
    }
    file.encoding = "UTF8";
    file.open("r");
    var text = file.read();
    file.close();
    return text;
}

function ensureFolder(path) {
    var folder = Folder(path);
    if (!folder.exists) {
        folder.create();
    }
}

function parentFolder(path) {
    return File(path).parent.fsName;
}

function placePngLayer(targetDoc, pngPath, layerName) {
    var sourceFile = File(pngPath);
    if (!sourceFile.exists) {
        throw new Error("Missing layer PNG: " + pngPath);
    }
    var sourceDoc = app.open(sourceFile);
    app.activeDocument = sourceDoc;
    sourceDoc.activeLayer.duplicate(targetDoc, ElementPlacement.PLACEATBEGINNING);
    sourceDoc.close(SaveOptions.DONOTSAVECHANGES);

    app.activeDocument = targetDoc;
    targetDoc.activeLayer.name = layerName;
}

function removeDefaultLayer(doc, defaultLayer) {
    app.activeDocument = doc;
    try {
        doc.activeLayer = defaultLayer;
        defaultLayer.remove();
    } catch (e) {
    }
}

if (typeof TEXT_SLICER_PSD_MANIFEST === "undefined" || typeof TEXT_SLICER_PSD_OUTPUT === "undefined") {
    throw new Error("TEXT_SLICER_PSD_MANIFEST and TEXT_SLICER_PSD_OUTPUT must be set before loading assemble_layers.jsx.");
}

var manifest = eval("(" + readTextFile(TEXT_SLICER_PSD_MANIFEST) + ")");
ensureFolder(parentFolder(TEXT_SLICER_PSD_OUTPUT));

var target = app.documents.add(
    manifest.canvas_width,
    manifest.canvas_height,
    72,
    "TextSlicer",
    NewDocumentMode.RGB,
    DocumentFill.TRANSPARENT
);
var defaultLayer = target.activeLayer;

for (var i = manifest.layers.length - 1; i >= 0; i--) {
    var layer = manifest.layers[i];
    placePngLayer(target, layer.file, layer.name);
}

removeDefaultLayer(target, defaultLayer);

var outFile = File(TEXT_SLICER_PSD_OUTPUT);
var saveOptions = new PhotoshopSaveOptions();
saveOptions.layers = true;
saveOptions.embedColorProfile = true;
target.saveAs(outFile, saveOptions, true, Extension.LOWERCASE);
target.close(SaveOptions.DONOTSAVECHANGES);
app.preferences.rulerUnits = previousRulerUnits;
