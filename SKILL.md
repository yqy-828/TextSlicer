---
name: text-slicer
description: Slice text, number, punctuation, and symbol art from Photoshop PSD/PSB or transparent PNG atlas inputs into fixed-name PNG assets, then pack them into Unity-ready TexturePacker JSON Array atlas PNG/JSON files. Use for TextSlicer, Chinese "文字切图", PSD layer slicing, single-layer PSD/PNG character atlases such as 原.png or 原.psd, Unity sprite atlas output, and optional atlas-to-layered-PSD rebuilding.
---

# TextSlicer

## Workflow

Use this skill when the user provides either:

- A layered PSD/PSB with one top-level character per layer or group.
- A wide transparent PNG/PSD atlas where characters are arranged left to right in one row, such as `原.png` or single-layer `原.psd`.

Run the entry script:

```powershell
powershell -ExecutionPolicy Bypass -File <skill>/scripts/Export-TextPsdLayers.ps1 -InputPath <path>
```

The slice output folder is always beside the input and has the same base name. For example, `原.png`, `原.psd`, or `holdNum.psd` writes slices to a folder named `原` or `holdNum`. By default, the script also packs those slices into `<base>_nub.png` and `<base>_nub.json` beside the input for Unity use.

## Layered PSD Mode

For a layered PSD/PSB, the first run exports full-canvas transparent previews, a contact sheet, and a `mapping_template.json`. Inspect the contact sheet visually, fill each `char` field, then rerun:

```powershell
powershell -ExecutionPolicy Bypass -File <skill>/scripts/Export-TextPsdLayers.ps1 -InputPath <path-to-psd> -MappingJson <work-dir>/mapping_template.json
```

Do not trust Photoshop layer names or layer order for core characters. Identify each layer by sight.

## Wide Atlas Mode

For a transparent PNG or single-layer PSD/PSB atlas, the script reads the rendered image with Pillow and splits it by contiguous non-transparent alpha columns. It does not need Photoshop for normal PNG output.

The default left-to-right character order is:

```text
0 1 2 3 4 5 6 7 8 9 . , R $ K M B T Q
```

If only the digits are present, output only `0.png` through `9.png`. If extra character segments exist after the fixed list, name them from `19.png` upward in atlas order.

Prefer `原.png` for atlas work when both PNG and PSD are available. `原.psd` is supported when Pillow can read the PSD composite preview, but PNG is smaller and more stable across machines.

When the input is `<base>.png`, keep that source file in place and write the final atlas to `<base>_nub.png` with data in `<base>_nub.json`.

## Naming And Cropping Rules

Fixed output names:

- `0.png` through `9.png`: digits `0` through `9`
- `10.png`: period `.`
- `11.png`: comma `,`
- `12.png`: `R`
- `13.png`: `$`
- `14.png`: `K`
- `15.png`: `M`
- `16.png`: `B`
- `17.png`: `T`
- `18.png`: `Q`

Cropping rules:

- Layered PSD mode keeps the original PSD height.
- Atlas mode uses the atlas's total alpha height.
- Digits `0-9` share one width, equal to the widest present digit.
- Period and comma share one width, equal to the wider present punctuation mark.
- All other fixed characters and extra symbols use their own alpha width.
- Characters are horizontally centered in their output crop and vertical placement is preserved within the chosen height.

The scripts overwrite same-name PNG files in the output folder and do not delete unrelated files.

## Atlas And JSON Packing

Packing is enabled by default after successful slicing. The output format matches TexturePacker `JSON (Array)` with PNG-32/RGBA8888 texture output:

- `<base>_nub.png`: packed atlas
- `<base>_nub.json`: frame data
- `rotated: false`
- `trimmed: false`
- no border padding, shape padding, extrude, or transparent trimming
- atlas width and height are hard-limited to `2048x2048`

The packer sorts numeric slice filenames by their numeric value (`0.png`, `1.png`, `2.png`, ..., `18.png`). Non-numeric filenames sort after numeric filenames by name. It lays them out with a deterministic shelf packer, chooses the lowest-area layout, and breaks ties toward lower atlas height. Use `-NoPack` to keep the old slice-only behavior. Use `-AtlasMaxWidth` and `-AtlasMaxHeight` to lower the maximum texture size; values above `2048` are capped.

The JSON writer intentionally uses TexturePacker-style formatting: CRLF line endings, tab-indented frame blocks, inline `frame`, `spriteSourceSize`, `sourceSize`, and `meta.size` objects, plus a `SmartUpdate` string with three 32-character hashes. The hash values are TextSlicer-generated and are not expected to equal TexturePacker's proprietary hash values byte-for-byte.

## Optional Atlas-To-PSD

To rebuild a wide atlas into a layered PSD, run:

```powershell
powershell -ExecutionPolicy Bypass -File <skill>/scripts/Export-TextPsdLayers.ps1 -InputPath <atlas.png-or-psd> -AtlasToPsd -OutputPsd <output.psd>
```

Use `-CanvasWidth <pixels>` to force a layer canvas width, such as `324` for the gold-text sample. Without it, the script uses the widest detected character width. The PSD contains one transparent layer per detected character.

## Script Notes

`-InputPsd` remains accepted as an alias for older prompts. Use `-KeepWorkDir` when preserving previews or PSD assembly intermediates is useful.

If Photoshop COM direct execution fails, the script automatically falls back to VBScript late binding, which is more reliable on this machine.
