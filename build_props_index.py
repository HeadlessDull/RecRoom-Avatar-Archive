"""Scan the Props/ folder and write props_index.json."""
import os, json, urllib.parse

ROOT     = os.path.dirname(__file__)
PROPS_DIR = os.path.join(ROOT, "Props")
OUT      = os.path.join(ROOT, "props_index.json")


def _rel(path):
    return path.replace(ROOT + os.sep, "").replace(os.sep, "/")


def _scan_item(path, label):
    entries  = os.listdir(path)
    subdirs  = sorted(d for d in entries if os.path.isdir(os.path.join(path, d)))
    pngs     = sorted(e for e in entries if e.lower().endswith(".png"))
    blends   = sorted(e for e in entries if e.lower().endswith(".blend"))
    preview  = _rel(os.path.join(path, pngs[0])) if pngs else ""

    if subdirs:
        children = []
        for sub in subdirs:
            sub_path = os.path.join(path, sub)
            sub_entries = os.listdir(sub_path)
            sub_png   = next((_rel(os.path.join(sub_path, e)) for e in sorted(sub_entries) if e.lower().endswith(".png")), "")
            sub_blend = next((_rel(os.path.join(sub_path, e)) for e in sorted(sub_entries) if e.lower().endswith(".blend")), "")
            children.append({"label": sub, "preview": sub_png, "blend": sub_blend, "children": []})
        return {"label": label, "preview": preview, "blend": "", "children": children}
    else:
        blend = _rel(os.path.join(path, blends[0])) if blends else ""
        return {"label": label, "preview": preview, "blend": blend, "children": []}


def build():
    if not os.path.isdir(PROPS_DIR):
        print(f"Props/ folder not found at {PROPS_DIR}")
        return

    items = []
    for name in sorted(os.listdir(PROPS_DIR)):
        full = os.path.join(PROPS_DIR, name)
        if os.path.isdir(full):
            items.append(_scan_item(full, name))

    index = {"Props": items}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    print(f"props_index.json written — {len(items)} props")


if __name__ == "__main__":
    build()
