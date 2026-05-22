#!/usr/bin/env python3
import os, json

FACE_DIR = "Face"
OUTPUT   = "face_index.json"

CATEGORIES = ["Eyes", "Eyebrows", "Mouths"]

def _is_hidden(name):
    return name.startswith(".") or name.startswith("__")

def _rel(path):
    return path.replace(os.sep, "/")

def _scan_leaf(path, label):
    """A variant sub-folder: find its .blend and optional .png."""
    entries = [e for e in os.listdir(path) if not _is_hidden(e)]
    blend = next((_rel(os.path.join(path, e)) for e in entries if e.lower().endswith(".blend")), "")
    png   = next((_rel(os.path.join(path, e)) for e in entries if e.lower().endswith(".png")),   "")
    return {"label": label, "preview": png, "blend": blend, "children": []}

def _scan_item(path, label):
    entries = [e for e in os.listdir(path) if not _is_hidden(e)]
    subdirs = [e for e in entries if os.path.isdir(os.path.join(path, e))]
    blends  = [e for e in entries if e.lower().endswith(".blend")]
    pngs    = [e for e in entries if e.lower().endswith(".png")]
    preview = _rel(os.path.join(path, pngs[0])) if pngs else ""

    # VARIANT GROUP wins if ANY sub-folders exist, even if a .blend is also present
    if subdirs:
        children = [_scan_leaf(os.path.join(path, s), s) for s in sorted(subdirs)]
        return {"label": label, "preview": preview, "blend": "", "children": children}

    # DIRECT — no sub-folders
    if blends:
        return {"label": label, "preview": preview,
                "blend": _rel(os.path.join(path, blends[0])), "children": []}

    return {"label": label, "preview": preview, "blend": "", "children": []}

def build_index():
    index = {}
    for cat in CATEGORIES:
        cat_dir = os.path.join(FACE_DIR, cat)
        if not os.path.isdir(cat_dir):
            index[cat] = []; continue
        items = []
        for name in sorted(os.listdir(cat_dir)):
            if _is_hidden(name): continue
            full = os.path.join(cat_dir, name)
            if os.path.isdir(full):
                items.append(_scan_item(full, name))
        index[cat] = items
    return index

if __name__ == "__main__":
    if not os.path.isdir(FACE_DIR):
        print(f"ERROR: '{FACE_DIR}' not found. Run from repo root.")
        raise SystemExit(1)

    index = build_index()

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    print(f"✓ {OUTPUT} written")
    for cat, items in index.items():
        if items:
            for item in items:
                variant_info = f" ({len(item['children'])} variants)" if item["children"] else ""
                print(f"  {cat} / {item['label']}{variant_info}")
