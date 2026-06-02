"""Scan the NPCs/ folder and write npc_index.json."""
import os, json

ROOT     = os.path.dirname(__file__)
NPCS_DIR = os.path.join(ROOT, "NPCs")
OUT      = os.path.join(ROOT, "npc_index.json")


def _rel(path):
    return path.replace(ROOT + os.sep, "").replace(os.sep, "/")


def _scan_npc(path, label):
    entries = os.listdir(path)
    pngs    = sorted(e for e in entries if e.lower().endswith(".png"))
    blends  = sorted(e for e in entries if e.lower().endswith(".blend"))
    preview = _rel(os.path.join(path, pngs[0]))   if pngs   else ""
    blend   = _rel(os.path.join(path, blends[0])) if blends else ""
    return {"label": label, "preview": preview, "blend": blend, "children": []}


def build():
    if not os.path.isdir(NPCS_DIR):
        print(f"NPCs/ folder not found at {NPCS_DIR}")
        return

    items = []
    for name in sorted(os.listdir(NPCS_DIR)):
        full = os.path.join(NPCS_DIR, name)
        if os.path.isdir(full):
            items.append(_scan_npc(full, name))

    index = {"NPCs": items}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    print(f"npc_index.json written — {len(items)} NPCs")


if __name__ == "__main__":
    build()
