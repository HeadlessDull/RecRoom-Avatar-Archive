#!/usr/bin/env python3

import os, json

FACE_SHEETS_DIR = "FaceSheets"
OUTPUT          = "face_index.json"
CATEGORIES      = ["Eyes", "Mouths"]

def _is_hidden(name):
    return name.startswith(".") or name.startswith("__")

def _rel(path):
    return path.replace(os.sep, "/")

def _scan_style(path):
    entries = [e for e in os.listdir(path) if not _is_hidden(e) and e.lower().endswith(".png")]
    preview = None
    sprite  = None
    for e in entries:
        if e.lower() == "preview.png":
            preview = _rel(os.path.join(path, e))
        else:
            sprite = e
    return {
        "folder":  _rel(path),
        "preview": preview,
        "sprite":  sprite,
    }

def build():
    index = {}
    for cat in CATEGORIES:
        cat_dir = os.path.join(FACE_SHEETS_DIR, cat)
        if not os.path.isdir(cat_dir):
            index[cat] = []
            continue
        items = []
        for name in sorted(os.listdir(cat_dir)):
            if _is_hidden(name): continue
            full = os.path.join(cat_dir, name)
            if os.path.isdir(full):
                item = _scan_style(full)
                if item["sprite"]:
                    items.append(item)
        index[cat] = items
    return index

if __name__ == "__main__":
    if not os.path.isdir(FACE_SHEETS_DIR):
        print(f"ERROR: '{FACE_SHEETS_DIR}' not found. Run from repo root.")
        raise SystemExit(1)

    index = build()

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    print(f"✓ {OUTPUT} written")
    for cat, items in index.items():
        if items:
            for item in items:
                label = item["folder"].rsplit("/", 1)[-1]
                print(f"  {cat} / {label}  sprite={item['sprite']}  preview={'yes' if item['preview'] else 'no'}")
