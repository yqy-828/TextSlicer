#target photoshop

(function () {
    if (typeof TEXT_PSD_SLICER_INPUT === "undefined" ||
        typeof TEXT_PSD_SLICER_EXPORT_DIR === "undefined" ||
        typeof TEXT_PSD_SLICER_METADATA === "undefined") {
        throw new Error("Missing text PSD slicer runner variables.");
    }

    var oldDialogs = app.displayDialogs;
    var oldUnits = app.preferences.rulerUnits;
    app.displayDialogs = DialogModes.NO;
    app.preferences.rulerUnits = Units.PIXELS;

    function jsonEscape(value) {
        value = String(value);
        return value
            .replace(/\\/g, "\\\\")
            .replace(/"/g, '\\"')
            .replace(/\r/g, "\\r")
            .replace(/\n/g, "\\n")
            .replace(/\t/g, "\\t");
    }

    function fileStem(index) {
        var s = String(index);
        while (s.length < 3) {
            s = "0" + s;
        }
        return "layer_" + s;
    }

    function sameFile(a, b) {
        try {
            return File(a).fsName.toLowerCase() === File(b).fsName.toLowerCase();
        } catch (e) {
            return false;
        }
    }

    function findOpenDocument(path) {
        for (var i = 0; i < app.documents.length; i++) {
            try {
                if (sameFile(app.documents[i].fullName, path)) {
                    return app.documents[i];
                }
            } catch (e) {
            }
        }
        return null;
    }

    function exportPng(doc, outFile) {
        var opts = new ExportOptionsSaveForWeb();
        opts.format = SaveDocumentType.PNG;
        opts.PNG8 = false;
        opts.transparency = true;
        opts.interlaced = false;
        opts.quality = 100;
        doc.exportDocument(outFile, ExportType.SAVEFORWEB, opts);
    }

    function writeText(path, text) {
        var f = new File(path);
        f.encoding = "UTF8";
        f.open("w");
        f.write(text);
        f.close();
    }

    var sourceFile = new File(TEXT_PSD_SLICER_INPUT);
    var exportFolder = new Folder(TEXT_PSD_SLICER_EXPORT_DIR);
    if (!exportFolder.exists) {
        exportFolder.create();
    }

    var openedByScript = false;
    var sourceDoc = findOpenDocument(sourceFile);
    if (sourceDoc === null) {
        sourceDoc = app.open(sourceFile);
        openedByScript = true;
    }

    var workDoc = sourceDoc.duplicate(sourceDoc.name + "_text_psd_slicer_tmp", false);
    if (openedByScript) {
        sourceDoc.close(SaveOptions.DONOTSAVECHANGES);
    }

    app.activeDocument = workDoc;
    var widthPx = Math.round(workDoc.width.as("px"));
    var heightPx = Math.round(workDoc.height.as("px"));
    var topLayers = [];
    for (var i = 0; i < workDoc.layers.length; i++) {
        topLayers.push(workDoc.layers[i]);
    }

    var json = [];
    json.push("{");
    json.push('"source": "' + jsonEscape(sourceFile.fsName) + '",');
    json.push('"width": ' + widthPx + ",");
    json.push('"height": ' + heightPx + ",");
    json.push('"layers": [');

    for (var layerIndex = 0; layerIndex < topLayers.length; layerIndex++) {
        app.activeDocument = workDoc;
        var layer = topLayers[layerIndex];
        var sourceId = fileStem(layerIndex);
        var previewName = sourceId + ".png";
        var previewFile = new File(exportFolder.fsName + "/" + previewName);

        var tmpDoc = app.documents.add(
            widthPx,
            heightPx,
            workDoc.resolution,
            sourceId + "_tmp",
            NewDocumentMode.RGB,
            DocumentFill.TRANSPARENT
        );

        app.activeDocument = workDoc;
        workDoc.activeLayer = layer;
        layer.duplicate(tmpDoc, ElementPlacement.PLACEATBEGINNING);

        app.activeDocument = tmpDoc;
        try {
            tmpDoc.layers[0].visible = true;
        } catch (e) {
        }
        exportPng(tmpDoc, previewFile);
        tmpDoc.close(SaveOptions.DONOTSAVECHANGES);

        json.push("  {");
        json.push('    "source_id": "' + sourceId + '",');
        json.push('    "index": ' + layerIndex + ",");
        json.push('    "layer_name": "' + jsonEscape(layer.name) + '",');
        json.push('    "preview_file": "' + jsonEscape(previewName) + '"');
        json.push("  }" + (layerIndex < topLayers.length - 1 ? "," : ""));
    }

    json.push("]");
    json.push("}");
    writeText(TEXT_PSD_SLICER_METADATA, json.join("\n"));

    workDoc.close(SaveOptions.DONOTSAVECHANGES);
    app.displayDialogs = oldDialogs;
    app.preferences.rulerUnits = oldUnits;

    return "Exported " + topLayers.length + " top-level layers.";
}());
