#!/usr/bin/env python3
"""
Structure understood:

    Items/
        <Category>/
            <ItemName>/                    ← DIRECT: has a .blend at top level
                ItemName.blend
                ItemName.png               ← optional preview
            <ItemName>/                    ← VARIANT GROUP: has sub-folders
                ItemName.png               ← optional group preview
                Variant A/
                    Variant A.blend
                    Variant A.png
                Variant B/
                    Variant B.blend

All paths in index.json are relative to the repo root
"""

import os
import json

ITEMS_DIR  = "Items"
OUTPUT     = "index.json"

CATEGORIES = [
    "Belt", "Ear", "Eye", "Face", "Hair",
    "Hat", "Legs", "Neck", "Shirt", "Shoes",
    "Shoulder", "Wrist",
]

def _is_hidden(name: str) -> bool:
    return name.startswith(".") or name.startswith("__")

def _rel(path: str) -> str:
    """Convert an OS path to a forward-slash repo-relative path."""
    return path.replace(os.sep, "/")

def _scan_leaf(path: str, label: str) -> dict:
    entries = [e for e in os.listdir(path) if not _is_hidden(e)]
    blend = next((_rel(os.path.join(path, e)) for e in entries
                  if e.lower().endswith(".blend")), "")
    png   = next((_rel(os.path.join(path, e)) for e in entries
                  if e.lower().endswith(".png")), "")
    return {"label": label, "preview": png, "blend": blend, "children": []}

def _scan_item(path: str, label: str) -> dict:
    entries = [e for e in os.listdir(path) if not _is_hidden(e)]
    blends  = [e for e in entries if e.lower().endswith(".blend")]
    pngs    = [e for e in entries if e.lower().endswith(".png")]
    subdirs = [e for e in entries if os.path.isdir(os.path.join(path, e))]

    preview = _rel(os.path.join(path, pngs[0])) if pngs else ""

    if blends:
        return {
            "label":    label,
            "preview":  preview,
            "blend":    _rel(os.path.join(path, blends[0])),
            "children": [],
        }
    elif subdirs:
        children = [_scan_leaf(os.path.join(path, s), s) for s in sorted(subdirs)]
        return {
            "label":    label,
            "preview":  preview,
            "blend":    "",
            "children": children,
        }
    else:
        return {"label": label, "preview": preview, "blend": "", "children": []}

def build_index() -> dict:
    index = {}
    for cat in CATEGORIES:
        cat_dir = os.path.join(ITEMS_DIR, cat)
        if not os.path.isdir(cat_dir):
            index[cat] = []
            continue
        items = []
        for name in sorted(os.listdir(cat_dir)):
            if _is_hidden(name):
                continue
            full = os.path.join(cat_dir, name)
            if os.path.isdir(full):
                items.append(_scan_item(full, name))
        index[cat] = items
    return index

if __name__ == "__main__":
    # Must be run from repo root
    if not os.path.isdir(ITEMS_DIR):
        print(f"ERROR: '{ITEMS_DIR}' folder not found. Run this from the repo root.")
        raise SystemExit(1)

    index = build_index()

    total = sum(
        1 + len(item["children"])
        for cat_items in index.values()
        for item in cat_items
    )

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    print(f"✓ Written {OUTPUT}  ({total} items across {len(CATEGORIES)} categories)")
    for cat, items in index.items():
        if items:
            print(f"  {cat}: {len(items)} item(s)")
