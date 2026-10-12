#!/usr/bin/env python
import argparse
import hashlib
import json
import math
import os
import shutil
from collections import OrderedDict

from PIL import Image, ImageDraw, ImageFont


FIXED_OUTPUTS = {
    "0": "0",
    "1": "1",
    "2": "2",
    "3": "3",
    "4": "4",
    "5": "5",
    "6": "6",
    "7": "7",
    "8": "8",
    "9": "9",
    ".": "10",
    "period": "10",
    "dot": "10",
    ",": "11",
    "comma": "11",
    "R": "12",
    "$": "13",
    "K": "14",
    "M": "15",
    "B": "16",
    "T": "17",
    "Q": "18",
}

ATLAS_CHARS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", ".", ",", "R", "$", "K", "M", "B", "T", "Q"]
DIGITS = set("0123456789")
PUNCT_OUTPUTS = {"10", "11"}
TEXTUREPACKER_APP = "https://www.codeandweb.com/texturepacker"
ATLAS_HARD_MAX_SIZE = 2048


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f, object_pairs_hook=OrderedDict)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def alpha_bbox(image):
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    return image.getchannel("A").getbbox()


def normalize_transparent_pixels(image):
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    pixels = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a == 0 and (r or g or b):
                pixels[x, y] = (0, 0, 0, 0)
    return image


def contiguous_runs(values):
    if not values:
        return []
    runs = []
    start = prev = values[0]
    for value in values[1:]:
        if value == prev + 1:
            prev = value
        else:
            runs.append((start, prev + 1))
            start = prev = value
    runs.append((start, prev + 1))
    return runs


def alpha_column_runs(image):
    alpha = image.getchannel("A")
    active = []
    for x in range(image.width):
        if alpha.crop((x, 0, x + 1, image.height)).getbbox():
            active.append(x)
    return contiguous_runs(active)


def open_rgba(path):
    try:
        return Image.open(path).convert("RGBA")
    except Exception as exc:
        raise RuntimeError(
            "Unable to read image composite with Pillow: {}. For PSD atlas inputs, export a PNG and retry.".format(path)
        ) from exc


def inspect_input(args):
    image = open_rgba(args.input)
    layers = []
    try:
        probe = Image.open(args.input)
        layers = list(getattr(probe, "layers", []) or [])
    except Exception:
        layers = []

    ext = os.path.splitext(args.input)[1].lower()
    kind = "atlas"
    if ext in {".psd", ".psb"} and len(layers) > 1:
        kind = "layered-psd"

    data = OrderedDict([
        ("kind", kind),
        ("width", image.width),
        ("height", image.height),
        ("alpha_bbox", list(alpha_bbox(image) or [])),
        ("layer_count", len(layers)),
    ])
    print(json.dumps(data, ensure_ascii=False))


def open_layer_png(preview_dir, layer):
    path = os.path.join(preview_dir, layer["preview_file"])
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return Image.open(path).convert("RGBA")


def horizontal_center(image):
    bbox = alpha_bbox(image)
    if not bbox:
        return image.copy(), None

    width, _ = image.size
    left, top, right, bottom = bbox
    content_width = right - left
    content = image.crop(bbox)
    centered_left = int(round((width - content_width) / 2.0))
    result = Image.new("RGBA", image.size, (0, 0, 0, 0))
    result.alpha_composite(content, (centered_left, top))
    return result, (centered_left, top, centered_left + content_width, bottom)


def draw_checker(size, block=8):
    bg = Image.new("RGBA", size, (255, 255, 255, 255))
    draw = ImageDraw.Draw(bg)
    for y in range(0, size[1], block):
        for x in range(0, size[0], block):
            if ((x // block) + (y // block)) % 2:
                draw.rectangle([x, y, x + block - 1, y + block - 1], fill=(225, 225, 225, 255))
    return bg


def make_contact_sheet(args):
    metadata = load_json(args.metadata)
    layers = metadata.get("layers", [])
    if not layers:
        raise ValueError("metadata contains no layers")

    font = ImageFont.load_default()
    cell_w, cell_h = 220, 240
    cols = min(5, max(1, len(layers)))
    rows = int(math.ceil(len(layers) / float(cols)))
    sheet = Image.new("RGBA", (cols * cell_w, rows * cell_h), (236, 236, 236, 255))

    template_layers = []
    for i, layer in enumerate(layers):
        image = open_layer_png(args.preview_dir, layer)
        bbox = alpha_bbox(image)
        preview = image.crop(bbox) if bbox else Image.new("RGBA", (1, 1), (0, 0, 0, 0))

        scale = min(1.0, 150.0 / max(preview.width, preview.height, 1))
        preview_size = (max(1, int(preview.width * scale)), max(1, int(preview.height * scale)))
        preview = preview.resize(preview_size, Image.Resampling.LANCZOS)

        cell = draw_checker((cell_w, cell_h))
        cell.alpha_composite(preview, ((cell_w - preview.width) // 2, 58 + (150 - preview.height) // 2))
        draw = ImageDraw.Draw(cell)
        label = "{}  {}".format(layer["source_id"], layer.get("layer_name", ""))
        draw.rectangle([0, 0, cell_w - 1, 42], fill=(255, 255, 255, 235))
        draw.text((8, 8), label[:34], fill=(0, 0, 0, 255), font=font)
        draw.text((8, 26), "{}x{} bbox={}".format(image.width, image.height, bbox), fill=(80, 80, 80, 255), font=font)

        x = (i % cols) * cell_w
        y = (i // cols) * cell_h
        sheet.alpha_composite(cell, (x, y))

        template_layers.append(OrderedDict([
            ("source_id", layer["source_id"]),
            ("layer_name", layer.get("layer_name", "")),
            ("char", ""),
        ]))

    os.makedirs(os.path.dirname(os.path.abspath(args.sheet)), exist_ok=True)
    sheet.convert("RGB").save(args.sheet)
    save_json(args.template, OrderedDict([("layers", template_layers)]))
    print("Contact sheet: {}".format(args.sheet))
    print("Mapping template: {}".format(args.template))


def canonical_char(value):
    if value is None:
        return ""
    text = str(value).strip()
    aliases = {
        "PERIOD": "period",
        "DOT": "dot",
        "COMMA": "comma",
        "FULL STOP": "period",
        "MULTIPLY": "x",
        "TIMES": "x",
    }
    upper = text.upper()
    if upper in aliases:
        return aliases[upper]
    if upper in {"R", "K", "M", "B", "T", "Q"}:
        return upper
    return text


def parse_mapping(path):
    raw = load_json(path)
    entries = []
    if isinstance(raw, dict) and "layers" in raw:
        for row in raw["layers"]:
            source_id = row.get("source_id") or row.get("id")
            char = row.get("char", row.get("target", row.get("output", "")))
            if source_id and str(char).strip():
                entries.append((str(source_id), canonical_char(char)))
    elif isinstance(raw, dict):
        for source_id, char in raw.items():
            if str(char).strip():
                entries.append((str(source_id), canonical_char(char)))
    else:
        raise ValueError("mapping JSON must be an object or contain a layers array")

    if not entries:
        raise ValueError("mapping JSON has no filled char values")
    return entries


def assign_outputs(mapping_entries):
    assigned = OrderedDict()
    used = set()
    next_extra = 19

    for source_id, char in mapping_entries:
        fixed = FIXED_OUTPUTS.get(char)
        if fixed is not None:
            output = fixed
        else:
            while str(next_extra) in used:
                next_extra += 1
            output = str(next_extra)
            next_extra += 1

        if output in used:
            raise ValueError("duplicate output {}.png from mapping char {!r}".format(output, char))
        used.add(output)
        assigned[source_id] = OrderedDict([("char", char), ("output", output)])

    return assigned


def crop_for_output(centered, bbox, target_width):
    if bbox is None:
        raise ValueError("cannot crop an empty layer")
    canvas_w, canvas_h = centered.size
    left = int(round((canvas_w - target_width) / 2.0))
    right = left + target_width
    if left < 0 or right > canvas_w:
        raise ValueError("target width {} does not fit in canvas width {}".format(target_width, canvas_w))
    return centered.crop((left, 0, right, canvas_h))


def finalize(args):
    metadata = load_json(args.metadata)
    layer_by_id = {layer["source_id"]: layer for layer in metadata.get("layers", [])}
    mapping_entries = parse_mapping(args.mapping)
    assignments = assign_outputs(mapping_entries)

    prepared = OrderedDict()
    for source_id, assignment in assignments.items():
        if source_id not in layer_by_id:
            raise ValueError("mapping references unknown source_id: {}".format(source_id))
        image = open_layer_png(args.preview_dir, layer_by_id[source_id])
        centered, bbox = horizontal_center(image)
        if bbox is None:
            print("Skipping empty layer {}".format(source_id))
            continue
        prepared[source_id] = OrderedDict([
            ("assignment", assignment),
            ("image", centered),
            ("bbox", bbox),
            ("width", bbox[2] - bbox[0]),
        ])

    write_prepared_outputs(prepared, args.output_dir, layered=True)


def atlas_entries(image_path):
    image = open_rgba(image_path)
    bbox = alpha_bbox(image)
    if not bbox:
        raise ValueError("source image has no non-transparent pixels")

    _, top, _, bottom = bbox
    runs = alpha_column_runs(image)
    if not runs:
        raise ValueError("source image has no active alpha columns")

    entries = []
    for index, (left, right) in enumerate(runs):
        char = ATLAS_CHARS[index] if index < len(ATLAS_CHARS) else "extra{}".format(index - len(ATLAS_CHARS) + 1)
        output = FIXED_OUTPUTS.get(char, str(index))
        if index >= len(ATLAS_CHARS):
            output = str(19 + index - len(ATLAS_CHARS))
        segment = image.crop((left, top, right, bottom))
        entries.append(OrderedDict([
            ("source_id", "atlas_{:03d}".format(index)),
            ("char", char),
            ("output", output),
            ("image", segment),
            ("width", right - left),
            ("source_box", [left, top, right, bottom]),
        ]))
    return image, bbox, entries


def group_target_widths(items):
    digit_widths = [item["width"] for item in items if item["char"] in DIGITS]
    punct_widths = [item["width"] for item in items if item["output"] in PUNCT_OUTPUTS]
    return (
        max(digit_widths) if digit_widths else None,
        max(punct_widths) if punct_widths else None,
    )


def target_width_for(item, digit_target, punct_target):
    if item["char"] in DIGITS:
        return digit_target
    if item["output"] in PUNCT_OUTPUTS:
        return punct_target
    return item["width"]


def write_prepared_outputs(prepared, output_dir, layered=False):
    if not prepared:
        raise ValueError("no non-empty mapped layers to export")

    items = []
    if layered:
        for source_id, item in prepared.items():
            items.append(OrderedDict([
                ("source_id", source_id),
                ("char", item["assignment"]["char"]),
                ("output", item["assignment"]["output"]),
                ("image", item["image"]),
                ("bbox", item["bbox"]),
                ("width", item["width"]),
            ]))
    else:
        items = list(prepared)

    digit_target, punct_target = group_target_widths(items)
    os.makedirs(output_dir, exist_ok=True)

    for item in items:
        target_width = target_width_for(item, digit_target, punct_target)
        if layered:
            cropped = crop_for_output(item["image"], item["bbox"], target_width)
        else:
            cropped = Image.new("RGBA", (target_width, item["image"].height), (0, 0, 0, 0))
            cropped.alpha_composite(item["image"], ((target_width - item["width"]) // 2, 0))

        normalize_transparent_pixels(cropped)
        out_path = os.path.join(output_dir, item["output"] + ".png")
        cropped.save(out_path)
        print("{} -> {}".format(item["source_id"], out_path))


def sprite_sort_key(path):
    filename = os.path.basename(path)
    stem = os.path.splitext(filename)[0]
    try:
        return (0, int(stem), filename.lower())
    except ValueError:
        return (1, filename.lower())


def load_sprites(input_dir):
    paths = [
        os.path.join(input_dir, name)
        for name in os.listdir(input_dir)
        if name.lower().endswith(".png")
    ]
    sprites = []
    for path in sorted(paths, key=sprite_sort_key):
        image = Image.open(path).convert("RGBA")
        sprites.append(OrderedDict([
            ("filename", os.path.basename(path)),
            ("image", image),
            ("width", image.width),
            ("height", image.height),
        ]))
    if not sprites:
        raise ValueError("no PNG files found in {}".format(input_dir))
    return sprites


def shelf_layout(sprites, max_width, max_height):
    widest = max(sprite["width"] for sprite in sprites)
    if widest > max_width:
        raise ValueError("sprite width {} exceeds max atlas width {}".format(widest, max_width))

    best = None
    for limit in range(widest, max_width + 1):
        rows = []
        current = []
        row_width = 0
        row_height = 0
        for sprite in sprites:
            if current and row_width + sprite["width"] > limit:
                rows.append((current, row_width, row_height))
                current = []
                row_width = 0
                row_height = 0
            current.append(sprite)
            row_width += sprite["width"]
            row_height = max(row_height, sprite["height"])
        if current:
            rows.append((current, row_width, row_height))

        atlas_width = max(row[1] for row in rows)
        atlas_height = sum(row[2] for row in rows)
        if atlas_height > max_height:
            continue

        candidate = (atlas_width * atlas_height, atlas_height, atlas_width, rows)
        if best is None or candidate[:3] < best[:3]:
            best = candidate

    if best is None:
        raise ValueError("sprites do not fit in max atlas size {}x{}".format(max_width, max_height))
    return best[2], best[1], best[3]


def backup_if_overwriting_source(source_path, atlas_path):
    if not source_path:
        return None
    source_abs = os.path.abspath(source_path)
    atlas_abs = os.path.abspath(atlas_path)
    if os.path.normcase(source_abs) != os.path.normcase(atlas_abs):
        return None
    root, ext = os.path.splitext(source_abs)
    backup_path = root + ".source" + ext
    if not os.path.exists(backup_path):
        shutil.copy2(source_abs, backup_path)
    return backup_path


def json_string(value):
    return json.dumps(value, ensure_ascii=False)


def rect_json(rect):
    return '{{"x":{},"y":{},"w":{},"h":{}}}'.format(
        rect["x"],
        rect["y"],
        rect["w"],
        rect["h"],
    )


def size_json(size):
    return '{{"w":{},"h":{}}}'.format(size["w"], size["h"])


def texturepacker_smartupdate(frames, image_name, atlas_size):
    frame_bytes = json.dumps(frames, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    meta_bytes = "{}:{}x{}".format(image_name, atlas_size[0], atlas_size[1]).encode("utf-8")
    all_bytes = frame_bytes + b"\n" + meta_bytes
    return "$TexturePacker:SmartUpdate:{}:{}:{}$".format(
        hashlib.md5(frame_bytes).hexdigest(),
        hashlib.md5(meta_bytes).hexdigest(),
        hashlib.md5(all_bytes).hexdigest(),
    )


def save_texturepacker_json(frames, atlas_path, atlas_size, data_path):
    image_name = os.path.basename(atlas_path)
    smartupdate = texturepacker_smartupdate(frames, image_name, atlas_size)
    lines = ['{"frames": [', ""]

    for index, frame in enumerate(frames):
        frame_rect = frame["frame"]
        sprite_source = frame["spriteSourceSize"]
        source_size = frame["sourceSize"]
        is_last = index == len(frames) - 1
        lines.extend([
            "{",
            '\t"filename": {},'.format(json_string(frame["filename"])),
            '\t"frame": {},'.format(rect_json(frame_rect)),
            '\t"rotated": false,',
            '\t"trimmed": false,',
            '\t"spriteSourceSize": {},'.format(rect_json(sprite_source)),
            '\t"sourceSize": {}'.format(size_json(source_size)),
            "}]," if is_last else "},",
        ])

    lines.extend([
        '"meta": {',
        '\t"app": {},'.format(json_string(TEXTUREPACKER_APP)),
        '\t"version": "1.0",',
        '\t"image": {},'.format(json_string(image_name)),
        '\t"format": "RGBA8888",',
        '\t"size": {{"w":{},"h":{}}},'.format(atlas_size[0], atlas_size[1]),
        '\t"scale": "1",',
        '\t"smartupdate": {}'.format(json_string(smartupdate)),
        "}",
        "}",
    ])

    text = "\r\n".join(lines) + "\r\n"
    with open(data_path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def pack_atlas(args):
    sprites = load_sprites(args.input_dir)
    max_width = min(args.max_width, ATLAS_HARD_MAX_SIZE)
    max_height = min(args.max_height, ATLAS_HARD_MAX_SIZE)
    atlas_width, atlas_height, rows = shelf_layout(sprites, max_width, max_height)
    atlas = Image.new("RGBA", (atlas_width, atlas_height), (0, 0, 0, 0))
    frames = []

    y = 0
    for row, _, row_height in rows:
        x = 0
        for sprite in row:
            atlas.alpha_composite(sprite["image"], (x, y))
            frames.append(OrderedDict([
                ("filename", sprite["filename"]),
                ("frame", OrderedDict([
                    ("x", x),
                    ("y", y),
                    ("w", sprite["width"]),
                    ("h", sprite["height"]),
                ])),
                ("rotated", False),
                ("trimmed", False),
                ("spriteSourceSize", OrderedDict([
                    ("x", 0),
                    ("y", 0),
                    ("w", sprite["width"]),
                    ("h", sprite["height"]),
                ])),
                ("sourceSize", OrderedDict([
                    ("w", sprite["width"]),
                    ("h", sprite["height"]),
                ])),
            ]))
            x += sprite["width"]
        y += row_height

    normalize_transparent_pixels(atlas)
    os.makedirs(os.path.dirname(os.path.abspath(args.atlas)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.data)), exist_ok=True)
    backup_path = backup_if_overwriting_source(args.source, args.atlas)
    atlas.save(args.atlas)
    save_texturepacker_json(frames, args.atlas, (atlas_width, atlas_height), args.data)
    if backup_path:
        print("Backed up source -> {}".format(backup_path))
    print("Atlas -> {}".format(args.atlas))
    print("Data -> {}".format(args.data))


def atlas_finalize(args):
    _, _, entries = atlas_entries(args.input)
    write_prepared_outputs(entries, args.output_dir)


def safe_layer_name(char):
    return {
        ".": "period",
        ",": "comma",
        "$": "dollar",
    }.get(char, char)


def atlas_to_psd_assets(args):
    _, bbox, entries = atlas_entries(args.input)
    digit_target, punct_target = group_target_widths(entries)
    max_target = max(target_width_for(item, digit_target, punct_target) for item in entries)
    canvas_width = args.canvas_width or max_target
    if canvas_width < max_target:
        raise ValueError("canvas width {} is smaller than required {}".format(canvas_width, max_target))

    layer_dir = os.path.join(args.work_dir, "psd_layers")
    os.makedirs(layer_dir, exist_ok=True)
    layers = []

    for index, item in enumerate(entries):
        layer = Image.new("RGBA", (canvas_width, item["image"].height), (0, 0, 0, 0))
        layer.alpha_composite(item["image"], ((canvas_width - item["width"]) // 2, 0))
        normalize_transparent_pixels(layer)
        file_name = "layer_{:03d}.png".format(index)
        file_path = os.path.abspath(os.path.join(layer_dir, file_name))
        layer.save(file_path)
        layers.append(OrderedDict([
            ("index", index),
            ("char", item["char"]),
            ("name", safe_layer_name(item["char"])),
            ("file", file_path),
            ("source_box", item["source_box"]),
        ]))

    manifest = OrderedDict([
        ("source", os.path.abspath(args.input)),
        ("canvas_width", canvas_width),
        ("canvas_height", bbox[3] - bbox[1]),
        ("source_alpha_bbox", list(bbox)),
        ("layers", layers),
    ])
    os.makedirs(args.work_dir, exist_ok=True)
    save_json(args.manifest, manifest)
    print(args.manifest)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepare and finalize TextSlicer PNG slices.")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("--input", required=True)
    inspect.set_defaults(func=inspect_input)

    contact = sub.add_parser("make-contact-sheet")
    contact.add_argument("--metadata", required=True)
    contact.add_argument("--preview-dir", required=True)
    contact.add_argument("--sheet", required=True)
    contact.add_argument("--template", required=True)
    contact.set_defaults(func=make_contact_sheet)

    fin = sub.add_parser("finalize")
    fin.add_argument("--metadata", required=True)
    fin.add_argument("--preview-dir", required=True)
    fin.add_argument("--mapping", required=True)
    fin.add_argument("--output-dir", required=True)
    fin.set_defaults(func=finalize)

    atlas = sub.add_parser("atlas-finalize")
    atlas.add_argument("--input", required=True)
    atlas.add_argument("--output-dir", required=True)
    atlas.set_defaults(func=atlas_finalize)

    atlas_psd = sub.add_parser("atlas-to-psd-assets")
    atlas_psd.add_argument("--input", required=True)
    atlas_psd.add_argument("--work-dir", required=True)
    atlas_psd.add_argument("--manifest", required=True)
    atlas_psd.add_argument("--canvas-width", type=int)
    atlas_psd.set_defaults(func=atlas_to_psd_assets)

    pack = sub.add_parser("pack-atlas")
    pack.add_argument("--input-dir", required=True)
    pack.add_argument("--atlas", required=True)
    pack.add_argument("--data", required=True)
    pack.add_argument("--source")
    pack.add_argument("--max-width", type=int, default=2048)
    pack.add_argument("--max-height", type=int, default=2048)
    pack.set_defaults(func=pack_atlas)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
