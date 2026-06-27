bl_info = {
    "name": "Rec Room Wardrobe Browser",
    "author": "Headless Dull",
    "version": (3, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > RR Archive",
    "description": "Browse and append rec room wardrobe items",
    "category": "Object",
}


# Imports (HAIII HEWOOOO!!!! :3)


import bpy, bpy.utils.previews, atexit
import os, json, tempfile, threading, hashlib, shutil, webbrowser, re
import urllib.request, urllib.error, urllib.parse
import importlib as _importlib, sys as _sys


# Rig UI


def _load_rig_ui():
    mod_path = os.path.join(os.path.dirname(__file__), "rig_ui_patch.py")
    spec = _importlib.util.spec_from_file_location("rig_ui_patch", mod_path)
    mod  = _importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _sys.modules["rig_ui_patch"] = mod
    mod.register_rig_ui()

def _unload_rig_ui():
    mod = _sys.modules.get("rig_ui_patch")
    if mod:
        try: mod.unregister_rig_ui()
        except: pass
        _sys.modules.pop("rig_ui_patch", None)


# Config


REPO          = "HeadlessDull/RecRoom-Avatar-Archive"
RAW_BASE      = f"https://raw.githubusercontent.com/{REPO}/main"
CATEGORIES    = ["Belt","Ear","Eye","Face","Hair","Hat","Legs","Neck","Shirt","Shoes","Shoulder","Wrist"]
APPEND_MAP    = {"FB": "FB Clothing", "MB": "MB Clothing"}
ARMATURE      = "Avatar_Skeleton"
RIG_FILE      = os.path.join(os.path.dirname(__file__), "Rec_Room_Rig.blend")
RIG_COL       = "Rec Room Rig"
RIG_UI_SCRIPT = "Avatar_RigUI.py"
CLOTHING_COLS    = {"FB": "FB Clothing", "MB": "MB Clothing"}
UNITY_RIG_FILE   = os.path.join(os.path.dirname(__file__), "Rec_Room_Unity_Rig.blend")
SHADERS_FILE     = os.path.join(os.path.dirname(__file__), "Rec_Room_Shaders.blend")
RENDER_FILE      = os.path.join(os.path.dirname(__file__), "render.blend")
RENDER_COL       = "render"
UNITY_RIG_COL    = "Rec Room Unity Rig"
UNITY_ARMATURE   = "Avatar Skeleton"
BAKE_COL_NAME    = "Bake"
BAKE_RES         = 1024

# Face browser config
FACE_CATEGORIES  = ["Eyes", "Mouths"]
FACE_INDEX_URL   = f"{RAW_BASE}/face_index.json"
FACE_CACHE_DIR   = os.path.join(os.path.dirname(__file__), ".cache", "face")

FACE_NODE_LABEL = {
    "Eyes":   "FACE_Eyes",
    "Mouths": "FACE_Mouth",
}

# State


INDEX_CACHE   = None
INDEX_ERROR   = ""
INDEX_LOADING = False
PREVIEW_COLL  = None
PROPS_CACHE   = None
PROPS_ERROR   = ""
PROPS_LOADING = False
PROPS_INDEX_URL = f"{RAW_BASE}/props_index.json"
PROPS_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache", "props")

FACE_CACHE    = None
FACE_ERROR    = ""
FACE_LOADING  = False



# Custom icons

_CUSTOM_ICONS = None

def _load_custom_icons():
    global _CUSTOM_ICONS
    _CUSTOM_ICONS = bpy.utils.previews.new()
    icon_path = os.path.join(os.path.dirname(__file__), "RRIcon.png")
    if os.path.isfile(icon_path):
        _CUSTOM_ICONS.load("RR_ICON", icon_path, "IMAGE")

def _unload_custom_icons():
    global _CUSTOM_ICONS
    if _CUSTOM_ICONS:
        bpy.utils.previews.remove(_CUSTOM_ICONS)
        _CUSTOM_ICONS = None

def _rr_icon():
    if _CUSTOM_ICONS and "RR_ICON" in _CUSTOM_ICONS:
        return _CUSTOM_ICONS["RR_ICON"].icon_id
    return 0


# Helpers


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "RRWardrobeBrowser"})
    with urllib.request.urlopen(req, timeout=30) as r: return r.read()

def _cache_dir():
    d = os.path.join(os.path.dirname(__file__), ".cache")
    os.makedirs(d, exist_ok=True)
    return d

def _preview_local(repo_path):
    return os.path.join(_cache_dir(), hashlib.md5(repo_path.encode()).hexdigest() + ".png")

def _download_preview(repo_path):
    if not repo_path: return
    local = _preview_local(repo_path)
    if os.path.isfile(local): return
    try:
        data = _fetch(f"{RAW_BASE}/{urllib.parse.quote(repo_path, safe='/').replace('(', '%28').replace(')', '%29')}")
        open(local, "wb").write(data)
    except Exception as e:
        print(f"Preview download failed: {repo_path} — {e}")

def _redraw_all():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()

def _load_into_preview_coll(local):
    global PREVIEW_COLL
    if PREVIEW_COLL is None: PREVIEW_COLL = bpy.utils.previews.new()
    if local not in PREVIEW_COLL:
        try: PREVIEW_COLL.load(local, local, "IMAGE")
        except: pass
    _redraw_all()


_PREVIEW_ICONS = {}
_FETCHING = set()
_DOWNLOAD_SEMAPHORE = threading.Semaphore(5)
MISSING_ICON = 0

def _load_icon(local):
    """Load a PNG into PREVIEW_COLL and return its icon_id. Call on main thread only."""
    global PREVIEW_COLL
    if PREVIEW_COLL is None: PREVIEW_COLL = bpy.utils.previews.new()
    if local in PREVIEW_COLL:
        ico = PREVIEW_COLL[local].icon_id
        if ico != 0: return ico
        try: del PREVIEW_COLL[local]
        except: pass
    try:
        PREVIEW_COLL.load(local, local, "IMAGE")
        return PREVIEW_COLL[local].icon_id
    except:
        return 0

def _watch_and_load(repo_path, local):
    """Background thread: wait up to 10s for file to appear, then load icon via timer."""
    import time
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if os.path.isfile(local):
            def _do_load(l=local, p=repo_path):
                ico = _load_icon(l)
                _PREVIEW_ICONS[l] = ico if ico != 0 else -1
                _redraw_all()
                return None
            bpy.app.timers.register(_do_load, first_interval=0.05)
            return
        time.sleep(0.1)
    _PREVIEW_ICONS[local] = -1

def load_preview(repo_path):
    """Return icon_id for a preview. Kicks off download+watch if not started yet."""
    if not repo_path: return 0
    local = _preview_local(repo_path)
    if local in _PREVIEW_ICONS:
        ico = _PREVIEW_ICONS[local]
        return ico if ico > 0 else 0
    if os.path.isfile(local):
        ico = _load_icon(local)
        _PREVIEW_ICONS[local] = ico if ico != 0 else 0
        return ico
    if repo_path not in _FETCHING:
        _FETCHING.add(repo_path)
        def _fetch_and_watch(rp=repo_path, lp=local):
            with _DOWNLOAD_SEMAPHORE:
                _download_preview(rp)
            _watch_and_load(rp, lp)
        threading.Thread(target=_fetch_and_watch, daemon=True).start()
    return 0

def _reset_previews():
    """Clear all preview state. Call when index refreshes or cache clears."""
    global PREVIEW_COLL, _DOWNLOAD_SEMAPHORE
    _PREVIEW_ICONS.clear()
    _FETCHING.clear()
    _DOWNLOAD_SEMAPHORE = threading.Semaphore(5)
    if PREVIEW_COLL:
        bpy.utils.previews.remove(PREVIEW_COLL)
        PREVIEW_COLL = None

def _preload_cached_previews():
    """Load all cached PNGs into PREVIEW_COLL, then redraw."""
    global PREVIEW_COLL
    if PREVIEW_COLL is None: PREVIEW_COLL = bpy.utils.previews.new()
    cache_root = os.path.join(os.path.dirname(__file__), ".cache")
    if not os.path.isdir(cache_root): return None
    for dirpath, _, filenames in os.walk(cache_root):
        for fname in filenames:
            if not fname.lower().endswith(".png"): continue
            local = os.path.join(dirpath, fname)
            if local not in PREVIEW_COLL:
                try: PREVIEW_COLL.load(local, local, "IMAGE")
                except: pass
    bpy.app.timers.register(_redraw_all, first_interval=0.3)
    return None

def _prefetch_single(repo_path):
    """Kick off a preview download without waiting for the icon to load."""
    if not repo_path or repo_path in _FETCHING: return
    local = _preview_local(repo_path)
    if os.path.isfile(local): return
    _FETCHING.add(repo_path)
    def _dl(rp=repo_path, lp=local):
        with _DOWNLOAD_SEMAPHORE:
            _download_preview(rp)
        _watch_and_load(rp, lp)
    threading.Thread(target=_dl, daemon=True).start()


# Index loading


def _load_index_bg():
    global INDEX_CACHE, INDEX_ERROR, INDEX_LOADING
    try:
        INDEX_CACHE = json.loads(_fetch(f"{RAW_BASE}/index.json"))
        bpy.app.timers.register(_preload_cached_previews, first_interval=0.2)
    except urllib.error.HTTPError as e:
        INDEX_ERROR = ("index.json not found — run build_index.py." if e.code == 404 else
                       f"HTTP {e.code}: {e.reason}")
    except Exception as e:
        INDEX_ERROR = str(e)
    finally:
        INDEX_LOADING = False
        bpy.app.timers.register(lambda: _redraw_all() or None, first_interval=0.05)

def fetch_index():
    global INDEX_LOADING
    if INDEX_CACHE or INDEX_LOADING: return
    INDEX_LOADING = True
    threading.Thread(target=_load_index_bg, daemon=True).start()

def _load_props_bg():
    global PROPS_CACHE, PROPS_ERROR, PROPS_LOADING
    try:
        PROPS_CACHE = json.loads(_fetch(PROPS_INDEX_URL))
    except urllib.error.HTTPError as e:
        PROPS_ERROR = "props_index.json not found." if e.code == 404 else f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        PROPS_ERROR = str(e)
    finally:
        PROPS_LOADING = False
        bpy.app.timers.register(lambda: _redraw_all() or None, first_interval=0.05)

def fetch_props():
    global PROPS_LOADING
    if PROPS_CACHE or PROPS_LOADING: return
    PROPS_LOADING = True
    threading.Thread(target=_load_props_bg, daemon=True).start()

def _load_face_bg():
    global FACE_CACHE, FACE_ERROR, FACE_LOADING
    try:
        FACE_CACHE = json.loads(_fetch(FACE_INDEX_URL))
        bpy.app.timers.register(_preload_cached_previews, first_interval=0.2)
    except urllib.error.HTTPError as e:
        FACE_ERROR = "face_index.json not found." if e.code == 404 else f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        FACE_ERROR = str(e)
    finally:
        FACE_LOADING = False
        bpy.app.timers.register(lambda: _redraw_all() or None, first_interval=0.05)

def fetch_face():
    global FACE_LOADING
    if FACE_CACHE or FACE_LOADING: return
    FACE_LOADING = True
    threading.Thread(target=_load_face_bg, daemon=True).start()

def _subdir_preview_local(subdir, repo_path):
    d = os.path.join(os.path.dirname(__file__), ".cache", subdir)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, hashlib.md5(repo_path.encode()).hexdigest() + ".png")

def _load_subdir_preview(subdir, repo_path):
    if not repo_path: return 0
    local = _subdir_preview_local(subdir, repo_path)
    global PREVIEW_COLL
    if PREVIEW_COLL and local in PREVIEW_COLL:
        return PREVIEW_COLL[local].icon_id
    if os.path.isfile(local):
        if PREVIEW_COLL is None: PREVIEW_COLL = bpy.utils.previews.new()
        try:
            PREVIEW_COLL.load(local, local, "IMAGE")
            return PREVIEW_COLL[local].icon_id
        except: pass
    if repo_path not in _FETCHING:
        _FETCHING.add(repo_path)
        def _dl(rp=repo_path, lp=local):
            try:
                data = _fetch(f"{RAW_BASE}/{urllib.parse.quote(rp, safe='/').replace('(','%28').replace(')','%29')}")
                open(lp, "wb").write(data)
            except: pass
            if os.path.isfile(lp):
                bpy.app.timers.register(lambda l=lp: _load_into_preview_coll(l), first_interval=0.1)
        threading.Thread(target=_dl, daemon=True).start()
    return 0

def load_prop_preview(repo_path):
    return _load_subdir_preview("props", repo_path)

def load_face_preview(repo_path):
    return _load_subdir_preview("face", repo_path)



# Search / data helpers


PROP_CATEGORIES = ["Weapons", "Toys", "Decoration"]

def all_props(category="Weapons"):
    if not PROPS_CACHE: return []
    return PROPS_CACHE.get(category, [])

def search_props(q, category="Weapons"):
    q = q.lower()
    out = []
    for item in all_props(category):
        if item["children"]:
            matched = [c for c in item["children"] if q in c["label"].lower()]
            out.append({**item, "children": matched} if matched
                       else item if q in item["label"].lower() else None)
        elif item.get("blend") and q in item["label"].lower():
            out.append(item)
    return [x for x in out if x]

def all_items():
    if not INDEX_CACHE: return []
    return [i for cat in CATEGORIES for i in INDEX_CACHE.get(cat, [])]

def search_items(q):
    q = q.lower()
    out = []
    for item in all_items():
        if item["children"]:
            matched = [c for c in item["children"] if q in c["label"].lower()]
            out.append({**item, "children": matched} if matched
                       else item if q in item["label"].lower() else None)
        elif item["blend"] and q in item["label"].lower():
            out.append(item)
    return [x for x in out if x]

def flatten(items):
    return [i for item in items
            for i in (flatten(item["children"]) if item["children"] else [item] if item["blend"] else [])]

def all_face_items(category):
    if not FACE_CACHE: return []
    return FACE_CACHE.get(category, [])

def _face_label(item):
    """Derive display label from folder path: 'FaceSheets/DimplesDown' -> 'Dimples Down'"""
    return item["folder"].rsplit("/", 1)[-1].replace("_", " ")

def search_face_items(q, category):
    q = q.lower()
    return [i for i in all_face_items(category) if q in _face_label(i).lower()]

def _open_set(ctx):
    return set(x for x in ctx.scene.wardrobe_open_groups.split(",") if x)

def _toggle_open(ctx, key):
    s = _open_set(ctx)
    s.discard(key) if key in s else s.add(key)
    ctx.scene.wardrobe_open_groups = ",".join(s)

def _safe_key(label):
    return "".join(c if c.isalnum() else "_" for c in label).lower()

def _collect_objects(col):
    return list(col.objects) + [o for c in col.children for o in _collect_objects(c)]

def _remove_col(col):
    for c in list(col.children): _remove_col(c)
    for c in list(bpy.data.collections):
        if col.name in {x.name for x in c.children}: c.children.unlink(col)
    for s in bpy.data.scenes:
        if col.name in {x.name for x in s.collection.children}: s.collection.children.unlink(col)
    bpy.data.collections.remove(col)

def _base(name):
    parts = name.rsplit(".", 1)
    return parts[0] if len(parts) == 2 and parts[1].isdigit() else name

def _all_children(col):
    for c in col.children:
        yield c
        yield from _all_children(c)

def _rig_in_scene():
    for c in bpy.data.collections:
        if (_base(c.name) == RIG_COL and
                any(c.name in {x.name for x in s.collection.children}
                    for s in bpy.data.scenes)):
            return c
    return None

def _check_rig(col):
    if not col: return False, [RIG_COL]
    child_base_names = {_base(c.name) for c in _all_children(col)}
    missing = [req for req in CLOTHING_COLS.values() if req not in child_base_names]
    if ARMATURE not in {_base(o.name) for o in _collect_objects(col)}: missing.append(ARMATURE)
    return len(missing) == 0, missing


# Classic Bean Emulator



BEAN_VG_SOURCES = [
    "Jnt.Spine.Root.Tweak",
    "Jnt.Spine.Root",
    "Jnt.Spine.Chest",
    "Jnt.Spine.Mid.Tweak",
    "Jnt.Spine.Mid",
]
BEAN_VG_TARGET  = "Jnt.Spine.Chest.Tweak"


def _mb_clothing_col():
    """Return the 'MB Clothing' collection if it exists anywhere in bpy.data."""
    for col in bpy.data.collections:
        if _base(col.name) == "MB Clothing":
            return col
    return None


def _remap_bean_vgroups(obj):
    """Merge BEAN_VG_SOURCES weights into BEAN_VG_TARGET, then remove source groups.

    Already-processed objects (none of the source groups present) are skipped silently.
    """
    if obj.type != "MESH":
        return

    mesh = obj.data


    present_sources = [n for n in BEAN_VG_SOURCES if obj.vertex_groups.get(n)]
    if not present_sources:
        return


    tgt_vg = obj.vertex_groups.get(BEAN_VG_TARGET)
    if tgt_vg is None:
        tgt_vg = obj.vertex_groups.new(name=BEAN_VG_TARGET)

    tgt_idx = tgt_vg.index


    weights = {}
    for v in mesh.vertices:
        for grp in v.groups:
            if grp.group == tgt_idx:
                weights[v.index] = grp.weight
                break


    for src_name in present_sources:
        src_vg = obj.vertex_groups.get(src_name)
        if src_vg is None:
            continue
        src_idx = src_vg.index
        for v in mesh.vertices:
            for grp in v.groups:
                if grp.group == src_idx:
                    weights[v.index] = min(1.0, weights.get(v.index, 0.0) + grp.weight)
                    break


    for v_idx, w in weights.items():
        tgt_vg.add([v_idx], w, "REPLACE")


    for src_name in present_sources:
        vg = obj.vertex_groups.get(src_name)
        if vg:
            obj.vertex_groups.remove(vg)


def _bean_torso_obj():
    """Return MB_BeanTorso_LOD0 from the BeanBody collection, or None."""
    bean_body = bpy.data.collections.get("BeanBody")
    if not bean_body:
        return None
    for obj in _collect_objects(bean_body):
        if obj.type == "MESH" and _base(obj.name) == "MB_BeanTorso_LOD0":
            return obj
    return None


def _apply_bean_emulator(context):
    """Remap bean vertex groups on all MB Clothing meshes + MB_BeanTorso_LOD0."""
    count = 0

    mb_col = _mb_clothing_col()
    if mb_col:
        for obj in _collect_objects(mb_col):
            if obj.type == "MESH":
                _remap_bean_vgroups(obj)
                count += 1

    torso = _bean_torso_obj()
    if torso:
        _remap_bean_vgroups(torso)
        count += 1

    context.scene.wardrobe_bean_active = True
    return count


# Atlas helpers


import math as _math

def _atlas_resolution(piece_count, per_tile_res=1024, max_atlas=4096):
    """Return (atlas_size, tile_size) for *piece_count* square tiles.

    Strategy:
    - Pack tiles into the smallest power-of-two square atlas.
    - If that atlas would exceed max_atlas, scale tile_size down evenly
      so everything fits inside max_atlas x max_atlas.
    """
    if piece_count <= 0:
        return per_tile_res, per_tile_res

    cols = _math.ceil(_math.sqrt(piece_count))
    rows = _math.ceil(piece_count / cols)

    def next_pow2(x):
        p = 1
        while p < x: p <<= 1
        return p

    atlas_w = next_pow2(cols * per_tile_res)
    atlas_h = next_pow2(rows * per_tile_res)
    atlas_size = max(atlas_w, atlas_h)

    if atlas_size > max_atlas:
        tile_size = max_atlas // cols
        p = 1
        while p * 2 <= tile_size: p <<= 1
        tile_size = p
        atlas_size = max_atlas
    else:
        tile_size = per_tile_res

    return atlas_size, tile_size


def _build_atlas(pieces_subset, piece_maps, map_key, atlas_name,
                 atlas_size, tile_size, is_normal=False, use_alpha=False):
    """Blit per-piece baked images into a single atlas image.

    Returns the new atlas bpy.data.images object.
    Tile layout: left-to-right, top-to-bottom.
    use_alpha keeps a meaningful alpha channel (e.g. metallic's packed smoothness).
    """
    import numpy as np

    cols = _math.ceil(_math.sqrt(len(pieces_subset)))

    atlas = bpy.data.images.new(atlas_name, width=atlas_size, height=atlas_size,
                                alpha=use_alpha, float_buffer=False)
    if is_normal:
        atlas.colorspace_settings.name = "Non-Color"

    atlas_px = [0.0] * (atlas_size * atlas_size * 4)

    for idx, (orig, dup, _) in enumerate(pieces_subset):
        src_img = piece_maps[dup.name][map_key]

        src_img.scale(tile_size, tile_size)
        tile_px = list(src_img.pixels)

        col_idx = idx % cols
        row_idx = idx // cols


        dst_x = col_idx * tile_size
        dst_y = atlas_size - (row_idx + 1) * tile_size

        for ty in range(tile_size):
            src_row_start = ty * tile_size * 4
            dst_row        = dst_y + ty
            if dst_row < 0 or dst_row >= atlas_size: continue
            dst_row_start  = (dst_row * atlas_size + dst_x) * 4
            atlas_px[dst_row_start:dst_row_start + tile_size * 4] =                 tile_px[src_row_start:src_row_start + tile_size * 4]

    atlas.pixels = atlas_px
    return atlas, cols


def _remap_uvs_to_atlas(pieces_subset, cols, atlas_size, tile_size):
    """Scale + translate each mesh's UVs into its atlas tile slot."""
    tile_uv  = tile_size / atlas_size

    for idx, (orig, dup, _) in enumerate(pieces_subset):
        col_idx = idx % cols
        row_idx = idx // cols

        uv_x = col_idx * tile_uv
        uv_y = 1.0 - (row_idx + 1) * tile_uv

        mesh = dup.data
        uv_layer = mesh.uv_layers.active
        if uv_layer is None: continue
        for uv_loop in uv_layer.data:
            uv_loop.uv.x = uv_loop.uv.x * tile_uv + uv_x
            uv_loop.uv.y = uv_loop.uv.y * tile_uv + uv_y


def _merge_pieces(context, pieces_subset, merged_name, bake_col):
    """Join all meshes in pieces_subset into one object using bpy.ops.object.join.

    Temporarily links objects into scene.collection so the join operator can
    see them, then moves the result back into bake_col only.
    Returns the merged object.
    """
    if not pieces_subset: return None

    scene = context.scene
    objs  = [dup for _, dup, _ in pieces_subset]


    for o in objs:
        if o.name not in scene.collection.objects:
            scene.collection.objects.link(o)

    for o in scene.objects: o.select_set(False)
    for o in objs:
        o.select_set(True)
    context.view_layer.objects.active = objs[0]

    bpy.ops.object.join()

    merged = context.view_layer.objects.active
    merged.name = merged_name


    if merged.name in scene.collection.objects:
        scene.collection.objects.unlink(merged)
    if merged.name not in {o.name for o in bake_col.objects}:
        bake_col.objects.link(merged)

    return merged


# Export helpers


def _nose_mesh_objects():
    """Return direct mesh children of the Nose_Meshes empty (child of Avatar_Meshes)."""
    avatar_meshes = bpy.data.objects.get("Avatar_Meshes")
    if not avatar_meshes:
        return []
    nose = next((c for c in avatar_meshes.children if c.name == "Nose_Meshes"), None)
    if not nose:
        return []
    return [c for c in nose.children if c.type == "MESH"]


def _get_source_objects(body_type):
    """Return (bake_objs, ref_objs, clothing_names).

    bake_objs      -- objects to duplicate, bake, and export
    ref_objs       -- objects to export as-is (no bake) with a blank material
    clothing_names -- subset of bake_objs that are clothing (for atlas split)

    FB: FB Clothing + BodyMesh_LOD0 + Nose_Meshes children  (all baked)
    MB: MB Clothing + MB_BeanTorso_LOD0 + Nose_Meshes children (baked)
        + BodyMesh_LOD0 from FullBody (ref only, not baked)
    """
    bake_objs      = []
    ref_objs       = []
    clothing_names = set()

    if body_type == "FB":
        fb_col = bpy.data.collections.get("FullBody")
        if fb_col:
            for sub in _all_children(fb_col):
                if _base(sub.name) == "FB Clothing":
                    for o in _collect_objects(sub):
                        if o.type == "MESH":
                            bake_objs.append(o)
                            clothing_names.add(o.name)
            for o in _collect_objects(fb_col):
                if o.type == "MESH" and o.name not in clothing_names:
                    bake_objs.append(o)
    else:
        mb_col = bpy.data.collections.get("BeanBody")
        if mb_col:
            for sub in _all_children(mb_col):
                if _base(sub.name) == "MB Clothing":
                    for o in _collect_objects(sub):
                        if o.type == "MESH":
                            bake_objs.append(o)
                            clothing_names.add(o.name)
            for o in _collect_objects(mb_col):
                if o.type == "MESH" and o.name not in clothing_names:
                    bake_objs.append(o)
        fb_col = bpy.data.collections.get("FullBody")
        if fb_col:
            body_ref = next((o for o in _collect_objects(fb_col)
                             if o.type == "MESH" and _base(o.name) == "BodyMesh_LOD0"), None)
            if body_ref:
                ref_objs.append(body_ref)


    for o in _nose_mesh_objects():
        bake_objs.append(o)

    seen = set(); result = []
    for o in bake_objs:
        if o.name not in seen:
            seen.add(o.name); result.append(o)
    return result, ref_objs, clothing_names


def _get_source_objects_selected(body_type, selected_names):
    """Export Selected Only mode.

    Only includes clothing objects from FB/MB Clothing whose names are in selected_names.
    BodyMesh_LOD0 always included as ref so Unity can read the rig.
    """
    bake_objs      = []
    clothing_names = set()
    clothing_col   = "FB Clothing" if body_type == "FB" else "MB Clothing"
    body_col_name  = "FullBody"    if body_type == "FB" else "BeanBody"

    col = bpy.data.collections.get(body_col_name)
    if col:
        for sub in _all_children(col):
            if _base(sub.name) == clothing_col:
                for o in _collect_objects(sub):
                    if o.type == "MESH" and o.name in selected_names:
                        bake_objs.append(o)
                        clothing_names.add(o.name)

    ref_objs = []
    fb_col = bpy.data.collections.get("FullBody")
    if fb_col:
        body_ref = next((o for o in _collect_objects(fb_col)
                         if o.type == "MESH" and _base(o.name) == "BodyMesh_LOD0"), None)
        if body_ref:
            ref_objs.append(body_ref)

    seen = set(); result = []
    for o in bake_objs:
        if o.name not in seen:
            seen.add(o.name); result.append(o)
    return result, ref_objs, clothing_names


def _ensure_bake_col(context):
    col = bpy.data.collections.get(BAKE_COL_NAME)
    if not col:
        col = bpy.data.collections.new(BAKE_COL_NAME)
        context.scene.collection.children.link(col)
    return col

def _apply_modifiers(obj, context):
    """Apply all non-armature modifiers, remove armature modifiers."""
    context.view_layer.objects.active = obj
    obj.select_set(True)
    for mod in list(obj.modifiers):
        if mod.type != "ARMATURE":
            try: bpy.ops.object.modifier_apply(modifier=mod.name)
            except: obj.modifiers.remove(mod)
    for mod in list(obj.modifiers):
        if mod.type == "ARMATURE": obj.modifiers.remove(mod)
    obj.select_set(False)

def _cleanup_export(bake_col):
    if not bake_col: return
    objs   = list(_collect_objects(bake_col))
    meshes = [o.data for o in objs if o.type == "MESH" and o.data]
    mats   = [m for o in objs if o.type == "MESH"
              for m in o.data.materials if m and "_bake" in m.name]
    images = [i for i in bpy.data.images if "_bake" in i.name]
    for obj in objs:
        for col in list(bpy.data.collections):
            if obj.name in {o.name for o in col.objects}: col.objects.unlink(obj)
        bpy.data.objects.remove(obj, do_unlink=True)
    for m in meshes:
        if m.users == 0: bpy.data.meshes.remove(m)
    for m in set(mats):
        if m.users == 0: bpy.data.materials.remove(m)
    for i in images: bpy.data.images.remove(i)
    _remove_col(bake_col)

def _add_bake_image_node(mat, img):
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    for n in [n for n in nodes if n.name == "BAKE_TARGET"]: nodes.remove(n)
    node = nodes.new("ShaderNodeTexImage")
    node.name = "BAKE_TARGET"; node.image = img
    for n in nodes: n.select = False
    node.select = True; nodes.active = node


def _bake_metallic_emission(mat, img):
    """Bake whichever node's 'Metallic' input feeds the shader into img.

    Items that have had 'Setup Material' applied use the custom Rec Room
    shader group instead of a Principled BSDF (that operator strips
    Principled BSDF nodes out entirely), so this looks for a 'Metallic'
    input on ANY node rather than assuming Principled BSDF specifically.

    Cycles has no native 'metallic' bake pass, so this temporarily reroutes
    that value (a link, or just its scalar value) through an Emission
    shader wired straight into the Material Output, bakes EMIT, then
    restores the original Surface link.
    Returns True on success, False if no node had a 'Metallic' input, no
    Material Output was found, or the bake itself failed.
    """
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    out_node = next((n for n in nodes if n.type == "OUTPUT_MATERIAL"), None)
    if not out_node:
        return False

    metallic_in = next((n.inputs["Metallic"] for n in nodes if "Metallic" in n.inputs), None)
    if metallic_in is None:
        return False

    emit = nodes.new("ShaderNodeEmission")
    emit.name = "TEMP_METALLIC_EMIT"
    if metallic_in.links:
        links.new(metallic_in.links[0].from_socket, emit.inputs["Color"])
    else:
        v = metallic_in.default_value
        emit.inputs["Color"].default_value = (v, v, v, 1.0)

    surface_in   = out_node.inputs["Surface"]
    orig_link    = surface_in.links[0] if surface_in.links else None
    orig_socket  = orig_link.from_socket if orig_link else None
    links.new(emit.outputs["Emission"], surface_in)

    _add_bake_image_node(mat, img)
    ok = True
    try:
        bpy.ops.object.bake(type="EMIT")
    except Exception:
        ok = False

    if orig_socket:
        links.new(orig_socket, surface_in)
    nodes.remove(emit)
    return ok


def _pack_metallic_smoothness(metallic_img, roughness_img):
    """Write smoothness (1 - roughness) into metallic_img's alpha channel.

    Matches Unity Standard shader's expected layout: Metallic (RGB),
    Smoothness (A). metallic_img must have been created with alpha=True.
    Modifies metallic_img in place.
    """
    import numpy as np
    m_px = np.array(metallic_img.pixels[:], dtype=np.float32).reshape(-1, 4)
    r_px = np.array(roughness_img.pixels[:], dtype=np.float32).reshape(-1, 4)
    m_px[:, 3] = 1.0 - r_px[:, 0]
    metallic_img.pixels = m_px.reshape(-1).tolist()


# Cache


def _wipe_cache_dir():
    """Delete the entire .cache folder tree and recreate it empty."""
    cache_root = os.path.join(os.path.dirname(__file__), ".cache")
    if os.path.isdir(cache_root):
        shutil.rmtree(cache_root, ignore_errors=True)
    os.makedirs(cache_root, exist_ok=True)


# Preferences


SHADER_ITEMS = [
    ("RGBA_AVATAR",  "RGBA Avatar",  "[RR] Rec Room Avatar Item Shader"),
    ("SOLID_AVATAR", "Solid Avatar", "[RR] Solid Rec Room Avatar Item Shader"),
    ("BASE_HAIR",    "Base Hair",    "[RR] Rec Room Hair Shader (Base)"),
    ("CURLY_HAIR",   "Curly Hair",   "[RR] Rec Room Hair Shader (Curly)"),
    ("BRAID_HAIR",   "Braid Hair",   "[RR] Rec Room Hair Shader (Braid)"),
]
SHADER_NODE_NAME = {item[0]: item[2] for item in SHADER_ITEMS}


class WardrobePreferences(bpy.types.AddonPreferences):
    bl_idname = __name__
    def _update_delete_cache(self, context):
        global _delete_cache_on_exit_enabled
        _delete_cache_on_exit_enabled = self.delete_cache_on_exit

    delete_cache_on_exit: bpy.props.BoolProperty(
        name="Delete Cache on Exit",
        description="Automatically delete cached preview images when Blender closes",
        default=False,
        update=_update_delete_cache,
    )

    dev_extras: bpy.props.BoolProperty(name="Development Extras", default=False)
    shader_type: bpy.props.EnumProperty(
        name="Shader",
        items=[(i[0], i[1], i[2]) for i in SHADER_ITEMS],
        default="RGBA_AVATAR",
    )
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "delete_cache_on_exit")
        layout.prop(self, "dev_extras")
        layout.separator()
        layout.label(text="Links:", icon="URL")
        row = layout.row(align=True)
        op = row.operator("wardrobe.open_url", text="Discord", icon="COMMUNITY")
        op.url = DISCORD_URL
        op = row.operator("wardrobe.open_url", text="RRO Map Addon", icon="WORLD")
        op.url = RRO_MAP_URL


# Operators


DISCORD_URL     = "https://discord.gg/UauGKxtuWJ"
RRO_MAP_URL     = "https://github.com/HeadlessDull/RecRoom-World-Archive"
FACE_HTML_PATH      = "file:///" + os.path.join(os.path.dirname(__file__), "face.html").replace(os.sep, "/")
HAIR_HTML_PATH      = "file:///" + os.path.join(os.path.dirname(__file__), "hair_recolor.html").replace(os.sep, "/")


class WARDROBE_OT_open_url(bpy.types.Operator):
    bl_idname   = "wardrobe.open_url"; bl_label = "Open URL"
    bl_description = "Open link in your browser"; bl_options = {"REGISTER"}
    url: bpy.props.StringProperty()
    def execute(self, context):
        webbrowser.open(self.url); return {"FINISHED"}

class WARDROBE_OT_open_face_html(bpy.types.Operator):
    bl_idname   = "wardrobe.open_face_html"; bl_label = "Open face.html"
    bl_description = "Open face.html in browser"; bl_options = {"REGISTER"}
    def execute(self, context):
        webbrowser.open(FACE_HTML_PATH); return {"FINISHED"}

class WARDROBE_OT_open_hair_html(bpy.types.Operator):
    bl_idname   = "wardrobe.open_hair_html"; bl_label = "Open hair_recolor.html"
    bl_description = "Open hair_recolor.html in browser"; bl_options = {"REGISTER"}
    def execute(self, context):
        webbrowser.open(HAIR_HTML_PATH); return {"FINISHED"}


class WARDROBE_OT_clear_cache(bpy.types.Operator):
    bl_idname = "wardrobe.clear_cache"; bl_label = "Clear Preview Cache"
    bl_description = "Delete ALL cached preview images (wardrobe, props, face, npc) so they re-download"
    bl_options = {"REGISTER"}
    def execute(self, context):
        _reset_previews()
        _wipe_cache_dir()
        self.report({"INFO"}, "Cache cleared.")
        return {"FINISHED"}


class WARDROBE_OT_setup_render(bpy.types.Operator):
    bl_idname      = "wardrobe.setup_render"
    bl_label       = "Setup Render Scene"
    bl_description = "Append render collection and world, set resolution to 1080x1080"
    bl_options     = {"REGISTER", "UNDO"}

    def execute(self, context):
        if not os.path.isfile(RENDER_FILE):
            self.report({"ERROR"}, "render.blend not found in addon folder.")
            return {"CANCELLED"}

        scene = context.scene

        with bpy.data.libraries.load(RENDER_FILE, link=False) as (data_from, data_to):
            if RENDER_COL in data_from.collections:
                data_to.collections = [RENDER_COL]
            else:
                self.report({"ERROR"}, f"'{RENDER_COL}' collection not found in render.blend.")
                return {"CANCELLED"}
            if data_from.worlds:
                data_to.worlds = list(data_from.worlds)

        for col in data_to.collections:
            if col is None: continue
            if col.name not in {c.name for c in scene.collection.children}:
                scene.collection.children.link(col)

        if data_to.worlds:
            for world in data_to.worlds:
                if world is not None:
                    scene.world = world
                    break

        scene.render.resolution_x = 1080
        scene.render.resolution_y = 1080
        scene.render.resolution_percentage = 100
        scene.render.film_transparent = True

        self.report({"INFO"}, "Render scene set up — 1080x1080.")
        return {"FINISHED"}


class WARDROBE_OT_setup_material(bpy.types.Operator):
    bl_idname      = "wardrobe.setup_material"
    bl_label       = "Setup Current Material"
    bl_description = "Replace Principled BSDF with selected Rec Room shader"
    bl_options     = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != "MESH":
            self.report({"ERROR"}, "No active mesh object.")
            return {"CANCELLED"}
        mat = obj.active_material
        if not mat:
            self.report({"ERROR"}, "No active material.")
            return {"CANCELLED"}
        if not mat.use_nodes:
            mat.use_nodes = True

        prefs      = context.preferences.addons[__name__].preferences
        node_name  = SHADER_NODE_NAME[prefs.shader_type]
        nodes      = mat.node_tree.nodes
        links      = mat.node_tree.links

        if any(n.type == "GROUP" and n.node_tree and n.node_tree.name == node_name
               for n in nodes):
            self.report({"INFO"}, f"'{node_name}' already in material — skipped.")
            return {"FINISHED"}

        if not os.path.isfile(SHADERS_FILE):
            self.report({"ERROR"}, "Rec_Room_Shaders.blend not found in addon folder.")
            return {"CANCELLED"}
        with bpy.data.libraries.load(SHADERS_FILE, link=False) as (data_from, data_to):
            data_to.node_groups = [ng for ng in data_from.node_groups
                                   if ng not in bpy.data.node_groups]

        ng = bpy.data.node_groups.get(node_name)
        if not ng:
            self.report({"ERROR"}, f"Node group '{node_name}' not found in blend file.")
            return {"CANCELLED"}

        out_node = next((n for n in nodes if n.type == "OUTPUT_MATERIAL"), None)
        if not out_node:
            out_node = nodes.new("ShaderNodeOutputMaterial")

        for n in [n for n in nodes if n.type == "BSDF_PRINCIPLED"]:
            nodes.remove(n)

        rr_node = nodes.new("ShaderNodeGroup")
        rr_node.node_tree = ng
        rr_node.name = node_name
        rr_node.location = (out_node.location.x - 300, out_node.location.y)
        rr_node.width = 360

        links.new(rr_node.outputs[0], out_node.inputs["Surface"])

        if prefs.shader_type in ("RGBA_AVATAR", "SOLID_AVATAR"):
            normals_name = "[RR] Compressed Unity Normals"
            ng_normals = bpy.data.node_groups.get(normals_name)
            if ng_normals:
                if not any(n.type == "GROUP" and n.node_tree and n.node_tree.name == normals_name
                           for n in nodes):
                    norm_node = nodes.new("ShaderNodeGroup")
                    norm_node.node_tree = ng_normals
                    norm_node.name = normals_name
                    norm_node.width = 360
                    norm_node.location = (rr_node.location.x - 400, rr_node.location.y - 200)
                    if "Normal" in rr_node.inputs:
                        links.new(norm_node.outputs[0], rr_node.inputs["Normal"])
            else:
                self.report({"WARNING"}, f"'{normals_name}' not found in shader blend.")

        self.report({"INFO"}, f"Applied '{node_name}' to {mat.name}.")
        return {"FINISHED"}


class WARDROBE_OT_repatch_rig_ui(bpy.types.Operator):
    bl_idname      = "wardrobe.repatch_rig_ui"
    bl_label       = "Re-patch Rig UI"
    bl_description = "Reload the Rig UI script from the addon"
    bl_options     = {"REGISTER"}

    def execute(self, context):
        try:
            _load_rig_ui()
            self.report({"INFO"}, "Rig UI re-patched successfully.")
        except Exception as e:
            self.report({"ERROR"}, f"Rig UI patch failed: {e}")
            return {"CANCELLED"}
        return {"FINISHED"}


class WARDROBE_OT_enable(bpy.types.Operator):
    bl_idname = "wardrobe.enable"; bl_label = "Enable Wardrobe Browser"
    bl_description = "Enable the wardrobe browser"; bl_options = {'REGISTER'}
    def execute(self, context):
        context.scene.wardrobe_enabled = True
        fetch_index()
        return {"FINISHED"}


class WARDROBE_OT_append_rig(bpy.types.Operator):
    bl_idname = "wardrobe.append_rig"; bl_label = "Set Up Scene"
    bl_description = "Append the Rec Room Rig and set colour management to Standard"; bl_options = {'REGISTER'}
    def execute(self, context):
        if not os.path.isfile(RIG_FILE):
            self.report({"ERROR"}, "Rec_Room_Rig.blend not found inside addon folder.")
            return {"CANCELLED"}
        view_settings = context.scene.view_settings
        if view_settings.view_transform != "Standard":
            view_settings.view_transform = "Standard"
            self.report({"INFO"}, "Colour management set to Standard.")
        with bpy.data.libraries.load(RIG_FILE, link=False) as (data_from, data_to):
            if RIG_COL not in data_from.collections:
                self.report({"ERROR"}, f"'{RIG_COL}' not found in rig blend.")
                return {"CANCELLED"}
            data_to.collections = [RIG_COL]
            data_to.texts = [t for t in data_from.texts if t == RIG_UI_SCRIPT]
        appended_col = None
        for col in data_to.collections:
            if col is None: continue
            if col.name not in {c.name for c in context.scene.collection.children}:
                context.scene.collection.children.link(col)
            appended_col = col
        try:
            _load_rig_ui()
        except Exception as e:
            self.report({"WARNING"}, f"Rig UI load warning: {e}")
        bpy.ops.ed.undo_push(message="Set Up Scene")
        self.report({"INFO"}, f"Scene set up: {appended_col.name if appended_col else RIG_COL}")
        return {"FINISHED"}


class WARDROBE_OT_fetch_index(bpy.types.Operator):
    bl_idname = "wardrobe.fetch_index"; bl_label = "Refresh Index"
    bl_description = "Re-download index.json from GitHub"; bl_options = {'REGISTER'}
    def execute(self, context):
        global INDEX_CACHE, INDEX_ERROR, PREVIEW_COLL
        INDEX_CACHE = None; INDEX_ERROR = ""
        _reset_previews()
        fetch_index()
        bpy.app.timers.register(_preload_cached_previews, first_interval=0.5)
        self.report({"INFO"}, "Fetching index…"); return {"FINISHED"}


class WARDROBE_OT_fetch_props(bpy.types.Operator):
    bl_idname = "wardrobe.fetch_props"; bl_label = "Refresh Props"
    bl_description = "Re-download props_index.json"; bl_options = {"REGISTER"}
    def execute(self, context):
        global PROPS_CACHE, PROPS_ERROR
        PROPS_CACHE = None; PROPS_ERROR = ""
        fetch_props()
        self.report({"INFO"}, "Fetching props…"); return {"FINISHED"}


class WARDROBE_OT_fetch_face(bpy.types.Operator):
    bl_idname = "wardrobe.fetch_face"; bl_label = "Refresh Face"
    bl_description = "Re-download face_index.json"; bl_options = {"REGISTER"}
    def execute(self, context):
        global FACE_CACHE, FACE_ERROR
        FACE_CACHE = None; FACE_ERROR = ""
        fetch_face()
        self.report({"INFO"}, "Fetching face items…"); return {"FINISHED"}


class WARDROBE_OT_clear_prop_search(bpy.types.Operator):
    bl_idname = "wardrobe.clear_prop_search"; bl_label = "Clear"; bl_options = {"REGISTER"}
    def execute(self, context):
        context.scene.wardrobe_prop_search = ""; return {"FINISHED"}


class WARDROBE_OT_toggle_prop_group(bpy.types.Operator):
    bl_idname = "wardrobe.toggle_prop_group"; bl_label = "Toggle"; bl_options = {"REGISTER"}
    group_key: bpy.props.StringProperty()
    def execute(self, context):
        s = set(x for x in context.scene.wardrobe_open_prop_groups.split(",") if x)
        s.discard(self.group_key) if self.group_key in s else s.add(self.group_key)
        context.scene.wardrobe_open_prop_groups = ",".join(s)
        return {"FINISHED"}


class WARDROBE_OT_select_prop(bpy.types.Operator):
    bl_idname = "wardrobe.select_prop"; bl_label = "Select Prop"; bl_options = {"REGISTER"}
    blend_path: bpy.props.StringProperty()
    item_label: bpy.props.StringProperty()
    def execute(self, context):
        context.scene.wardrobe_selected_prop_blend = self.blend_path
        context.scene.wardrobe_selected_prop_label = self.item_label
        return {"FINISHED"}


class WARDROBE_OT_append_prop(bpy.types.Operator):
    bl_idname = "wardrobe.append_prop"; bl_label = "Append Prop"
    bl_description = "Download and append prop to scene"; bl_options = {"REGISTER"}
    def execute(self, context):
        repo_path = context.scene.wardrobe_selected_prop_blend
        if not repo_path: self.report({"ERROR"}, "Nothing selected."); return {"CANCELLED"}
        try:
            data = _fetch(f"{RAW_BASE}/{urllib.parse.quote(repo_path, safe='/')}")
        except Exception as e:
            self.report({"ERROR"}, f"Download failed: {e}"); return {"CANCELLED"}
        tmp = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".blend", delete=False) as f:
                f.write(data); tmp = f.name
            with bpy.data.libraries.load(tmp, link=False) as (src, dst):
                dst.collections = [c for c in src.collections if c == "prop"]
            props_col = bpy.data.collections.get("Props")
            if not props_col:
                props_col = bpy.data.collections.new("Props")
                context.scene.collection.children.link(props_col)
            moved = []
            for col in dst.collections:
                if not col: continue
                for obj in list(col.objects):
                    if obj.name not in {o.name for o in props_col.objects}:
                        props_col.objects.link(obj)
                    moved.append(obj.name)
                _remove_col(col)
        finally:
            try: os.remove(tmp)
            except: pass
        if not moved: self.report({"WARNING"}, "No objects found."); return {"CANCELLED"}
        bpy.ops.ed.undo_push(message=f"Append {context.scene.wardrobe_selected_prop_label}")
        self.report({"INFO"}, f"Added {len(moved)} prop object(s)")
        return {"FINISHED"}


class WARDROBE_OT_clear_search(bpy.types.Operator):
    bl_idname = "wardrobe.clear_search"; bl_label = "Clear Search"; bl_options = {'REGISTER'}
    def execute(self, context):
        context.scene.wardrobe_search = ""; return {"FINISHED"}


class WARDROBE_OT_toggle_group(bpy.types.Operator):
    bl_idname = "wardrobe.toggle_group"; bl_label = "Toggle Group"; bl_options = {'REGISTER'}
    group_key: bpy.props.StringProperty()
    def execute(self, context):
        _toggle_open(context, self.group_key); return {"FINISHED"}


class WARDROBE_OT_select_item(bpy.types.Operator):
    bl_idname = "wardrobe.select_item"; bl_label = "Select"; bl_options = {'REGISTER'}
    blend_path: bpy.props.StringProperty()
    item_label: bpy.props.StringProperty()
    def execute(self, context):
        context.scene.wardrobe_selected_blend = self.blend_path
        context.scene.wardrobe_selected_label = self.item_label
        return {"FINISHED"}


class WARDROBE_OT_append_selected(bpy.types.Operator):
    bl_idname = "wardrobe.append_selected"; bl_label = "Append to Scene"
    bl_description = "Download .blend and append to scene"; bl_options = {'REGISTER'}
    def execute(self, context):
        repo_path = context.scene.wardrobe_selected_blend
        if not repo_path: self.report({"ERROR"}, "Nothing selected."); return {"CANCELLED"}
        rig_col = _rig_in_scene()
        ok, missing = _check_rig(rig_col)
        if not ok:
            self.report({"ERROR"}, f"Rig missing: {', '.join(missing)}. Append the rig first.")
            return {"CANCELLED"}
        def _base_name(n): return n.rsplit(".", 1)[0] if n.rsplit(".", 1)[-1].isdigit() else n
        arm = next((o for o in _collect_objects(rig_col) if _base_name(o.name) == ARMATURE), None)
        if not arm: self.report({"WARNING"}, f"'{ARMATURE}' not found — skipping armature wiring.")
        try:
            data = _fetch(f"{RAW_BASE}/{urllib.parse.quote(repo_path, safe='/')}")
        except Exception as e:
            self.report({"ERROR"}, f"Download failed: {e}"); return {"CANCELLED"}
        tmp = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".blend", delete=False) as f:
                f.write(data); tmp = f.name
            with bpy.data.libraries.load(tmp, link=False) as (src, dst):
                dst.collections = [c for c in src.collections if c in APPEND_MAP]
            moved = []
            for wrapper in dst.collections:
                if not wrapper: continue
                target_name = CLOTHING_COLS.get(wrapper.name, "")
                target = next((c for c in _all_children(rig_col)
                               if _base(c.name) == target_name), None) or rig_col
                for obj in _collect_objects(wrapper):
                    if obj.name not in {o.name for o in target.objects}: target.objects.link(obj)
                    if arm and obj.type == 'MESH':
                        for mod in obj.modifiers:
                            if mod.type == 'ARMATURE' and not mod.object: mod.object = arm
                    moved.append(obj.name)
                _remove_col(wrapper)
        finally:
            try: os.remove(tmp)
            except: pass
        if not moved: self.report({"WARNING"}, "No objects found."); return {"CANCELLED"}
        bpy.ops.ed.undo_push(message=f"Append {context.scene.wardrobe_selected_label}")
        self.report({"INFO"}, f"Added {len(moved)} object(s)" + (f" | Wired to {ARMATURE}" if arm else ""))
        return {"FINISHED"}


class WARDROBE_OT_apply_item(bpy.types.Operator):
    """Click-to-apply wardrobe item: sets selection then immediately appends."""
    bl_idname = "wardrobe.apply_item"; bl_label = "Apply Item"; bl_options = {"REGISTER", "UNDO"}
    blend_path: bpy.props.StringProperty()
    item_label: bpy.props.StringProperty()
    def execute(self, context):
        context.scene.wardrobe_selected_blend = self.blend_path
        context.scene.wardrobe_selected_label = self.item_label
        return bpy.ops.wardrobe.append_selected()


class WARDROBE_OT_apply_prop(bpy.types.Operator):
    """Click-to-apply prop: sets selection then immediately appends."""
    bl_idname = "wardrobe.apply_prop"; bl_label = "Apply Prop"; bl_options = {"REGISTER", "UNDO"}
    blend_path: bpy.props.StringProperty()
    item_label: bpy.props.StringProperty()
    def execute(self, context):
        context.scene.wardrobe_selected_prop_blend = self.blend_path
        context.scene.wardrobe_selected_prop_label = self.item_label
        return bpy.ops.wardrobe.append_prop()


class WARDROBE_OT_apply_face(bpy.types.Operator):
    """Click-to-apply face sprite: sets selection then immediately swaps."""
    bl_idname = "wardrobe.apply_face"; bl_label = "Apply Face"; bl_options = {"REGISTER", "UNDO"}
    blend_path: bpy.props.StringProperty()
    item_label: bpy.props.StringProperty()
    category:   bpy.props.StringProperty()
    def execute(self, context):
        context.scene.wardrobe_selected_face_blend    = self.blend_path
        context.scene.wardrobe_selected_face_label    = self.item_label
        context.scene.wardrobe_selected_face_category = self.category
        return bpy.ops.wardrobe.apply_face_item()


# Face browser operators


class WARDROBE_OT_clear_face_search(bpy.types.Operator):
    bl_idname = "wardrobe.clear_face_search"; bl_label = "Clear"; bl_options = {"REGISTER"}
    def execute(self, context):
        context.scene.wardrobe_face_search = ""; return {"FINISHED"}


class WARDROBE_OT_select_face_item(bpy.types.Operator):
    bl_idname = "wardrobe.select_face_item"; bl_label = "Select Face Item"; bl_options = {"REGISTER"}
    blend_path: bpy.props.StringProperty()
    item_label: bpy.props.StringProperty()
    category:   bpy.props.StringProperty()
    def execute(self, context):
        context.scene.wardrobe_selected_face_blend    = self.blend_path
        context.scene.wardrobe_selected_face_label    = self.item_label
        context.scene.wardrobe_selected_face_category = self.category
        return {"FINISHED"}


class WARDROBE_OT_apply_face_item(bpy.types.Operator):
    bl_idname      = "wardrobe.apply_face_item"
    bl_label       = "Apply to Face"
    bl_description = "Download sprite sheet PNG and hot-swap image node in face shader"
    bl_options     = {"REGISTER", "UNDO"}

    def execute(self, context):
        folder_path = context.scene.wardrobe_selected_face_blend
        category    = context.scene.wardrobe_selected_face_category
        label       = context.scene.wardrobe_selected_face_label

        if not folder_path:
            self.report({"ERROR"}, "Nothing selected."); return {"CANCELLED"}

        node_label = FACE_NODE_LABEL.get(category)
        if not node_label:
            self.report({"ERROR"}, f"Unknown category: {category}"); return {"CANCELLED"}

        sprite_filename = ""
        if FACE_CACHE:
            for item in FACE_CACHE.get(category, []):
                if item.get("folder") == folder_path:
                    sprite_filename = item.get("sprite", "")
                    break
        if not sprite_filename:
            self.report({"ERROR"}, f"No sprite filename found for {folder_path}"); return {"CANCELLED"}

        repo_path = f"{folder_path}/{sprite_filename}"
        encoded   = urllib.parse.quote(repo_path, safe="/").replace("(", "%28").replace(")", "%29")
        try:
            data = _fetch(f"{RAW_BASE}/{encoded}")
        except Exception as e:
            self.report({"ERROR"}, f"Download failed: {e}"); return {"CANCELLED"}

        tmp = ""
        swapped = 0
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(data); tmp = f.name

            internal_name = f"__face_{node_label}__"
            old = bpy.data.images.get(internal_name)
            if old:
                bpy.data.images.remove(old)

            new_img = bpy.data.images.load(tmp, check_existing=False)
            new_img.name = internal_name
            new_img.pack()

            for mat in bpy.data.materials:
                if not mat.use_nodes: continue
                for node in mat.node_tree.nodes:
                    if node.type == "TEX_IMAGE" and node.label == node_label:
                        node.image = new_img
                        swapped += 1
        finally:
            try: os.remove(tmp)
            except: pass

        if swapped == 0:
            self.report({"WARNING"}, f"No node found with label '{node_label}' — did you set it in the .blend?")
            return {"CANCELLED"}

        bpy.ops.ed.undo_push(message=f"Apply face: {label}")
        self.report({"INFO"}, f"Applied '{label}' to {swapped} node(s)")
        return {"FINISHED"}


# Unity Export


def _get_cycles_devices():
    """Return device items matching Blender's Cycles preferences list."""
    items = [("CPU", "CPU", "Bake using CPU")]
    try:
        prefs = bpy.context.preferences.addons.get("cycles")
        if prefs:
            for dev in prefs.preferences.devices:
                if dev.type != "CPU":
                    safe_id = dev.name.replace(" ","_").replace("(","").replace(")","")
                    api = {"CUDA": " (CUDA)", "OPTIX": " (OptiX - faster)",
                           "HIP": " (HIP)", "METAL": " (Metal)"}.get(dev.type, "")
                    items.append((safe_id, dev.name + api, f"Bake using {dev.name}"))
    except Exception:
        pass
    return items


def _set_bake_device(device_id):
    scene = bpy.context.scene
    if device_id == "CPU":
        scene.cycles.device = "CPU"
    else:
        scene.cycles.device = "GPU"
        try:
            prefs = bpy.context.preferences.addons.get("cycles")
            if prefs:
                cprefs = prefs.preferences
                for compute_type in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
                    try:
                        cprefs.compute_device_type = compute_type
                        cprefs.refresh_devices()
                        if any(d.type != "CPU" for d in cprefs.devices):
                            break
                    except Exception:
                        continue
                for dev in cprefs.devices:
                    dev.use = True
        except Exception:
            pass


class WARDROBE_OT_set_bake_device(bpy.types.Operator):
    bl_idname = "wardrobe.set_bake_device"; bl_label = "Set Bake Device"
    bl_options = {"REGISTER"}
    device_id: bpy.props.StringProperty()
    def execute(self, context):
        context.scene.wardrobe_bake_device = self.device_id
        return {"FINISHED"}


class WARDROBE_OT_export_unity(bpy.types.Operator):
    bl_idname      = "wardrobe.export_unity"
    bl_label       = "Export Avatar"
    bl_description = "Bake and export FBX for Unity"
    bl_options     = {"REGISTER"}

    body_type: bpy.props.EnumProperty(
        name="Body Type",
        items=[("FB", "Full Body (FB)", ""), ("MB", "Bean Body (MB)", "")],
        default="FB",
    )
    directory: bpy.props.StringProperty(subtype="DIR_PATH", default="")

    def invoke(self, context, event):
        self.body_type = context.scene.wardrobe_export_body
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        scene    = context.scene
        out_dir  = self.directory or tempfile.gettempdir()
        fbx_path = os.path.join(out_dir, "model.fbx")
        tex_dir  = os.path.join(out_dir, "textures")
        os.makedirs(tex_dir, exist_ok=True)


        selected_names = {o.name for o in context.selected_objects if o.type == "MESH"}

        if scene.wardrobe_export_selected:
            if not selected_names:
                self.report({"ERROR"}, "No objects selected. Select clothing objects in the viewport first.")
                return {"CANCELLED"}
            source_objs, ref_objs, clothing_names = _get_source_objects_selected(self.body_type, selected_names)
            if not source_objs:
                self.report({"ERROR"}, "None of the selected objects are in FB/MB Clothing.")
                return {"CANCELLED"}
        else:
            source_objs, ref_objs, clothing_names = _get_source_objects(self.body_type)
            if not source_objs:
                self.report({"ERROR"}, "No mesh objects found for selected body type.")
                return {"CANCELLED"}

        if not os.path.isfile(UNITY_RIG_FILE):
            self.report({"ERROR"}, "Rec_Room_Unity_Rig.blend not found in addon folder.")
            return {"CANCELLED"}


        scene.wardrobe_export_exclude_names = ",".join(selected_names) if scene.wardrobe_export_exclude else ""


        prev_engine = scene.render.engine
        prev_device = scene.cycles.device
        scene.render.engine = "CYCLES"
        _set_bake_device(scene.wardrobe_bake_device)

        bk = scene.render.bake
        bk.use_selected_to_active = False
        bk.target                 = "IMAGE_TEXTURES"
        bk.use_clear              = True
        bk.margin                 = 16
        bk.margin_type            = "ADJACENT_FACES"
        bk.use_pass_direct        = False
        bk.use_pass_indirect      = False
        bk.use_pass_color         = True

        bake_col = _ensure_bake_col(context)
        pieces   = []
        applied_temps = []


        for orig in source_objs:
            depsgraph = context.evaluated_depsgraph_get()
            orig_eval = orig.evaluated_get(depsgraph)
            eval_mesh = bpy.data.meshes.new_from_object(orig_eval, depsgraph=depsgraph)

            tmp = bpy.data.objects.new(orig.name + "_tmp_applied", eval_mesh)
            for mat in orig.data.materials:
                tmp.data.materials.append(mat)
            tmp.name = orig.name + "_tmp_applied"
            scene.collection.objects.link(tmp)
            if not tmp.data.uv_layers:
                tmp.data.uv_layers.new(name="UVMap")
            applied_temps.append((orig, tmp))

        for orig, tmp in applied_temps:
            tmp = bpy.data.objects.get(tmp.name)
            if tmp is None: continue
            if len(tmp.data.materials) <= 1:
                dup = tmp.copy()
                dup.data = tmp.data.copy()
                dup.name = orig.name + "_bake"
                dup.data.materials.clear()
                for mat in tmp.data.materials:
                    dup.data.materials.append(mat.copy() if mat else None)
                bake_col.objects.link(dup)
                for vg in orig.vertex_groups:
                    new_vg = dup.vertex_groups.new(name=vg.name)
                    for v in orig.data.vertices:
                        for grp in v.groups:
                            if grp.group == vg.index:
                                new_vg.add([v.index], grp.weight, "REPLACE")
                pieces.append((orig, dup, orig.name in clothing_names))
                bpy.data.objects.remove(tmp, do_unlink=True)
            else:
                names_before = {o.name for o in bpy.data.objects if o.type == "MESH"}
                for o in scene.objects: o.select_set(False)
                context.view_layer.objects.active = tmp
                tmp.select_set(True)
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.ops.mesh.separate(type="MATERIAL")
                bpy.ops.object.mode_set(mode="OBJECT")
                tmp_pieces = [o for o in bpy.data.objects
                              if o.type == "MESH" and
                              (o.name == tmp.name or o.name not in names_before)]
                self.report({"INFO"}, f"Separated {orig.name} into {len(tmp_pieces)} piece(s)")
                for tp in tmp_pieces:
                    dup = tp.copy()
                    dup.data = tp.data.copy()
                    dup.name = tp.name.replace("_tmp_applied", "") + "_bake"
                    dup.data.materials.clear()
                    for mat in tp.data.materials:
                        dup.data.materials.append(mat.copy() if mat else None)
                    bake_col.objects.link(dup)
                    for vg in orig.vertex_groups:
                        new_vg = dup.vertex_groups.new(name=vg.name)
                        for v in orig.data.vertices:
                            for grp in v.groups:
                                if grp.group == vg.index:
                                    new_vg.add([v.index], grp.weight, "REPLACE")
                    pieces.append((orig, dup, orig.name in clothing_names))
                for tp in tmp_pieces:
                    try: bpy.data.objects.remove(tp, do_unlink=True)
                    except: pass


        for orig, dup, _ in pieces:
            context.view_layer.objects.active = dup
            for o in scene.objects: o.select_set(False)
            dup.select_set(True)
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            dup.select_set(False)


        for orig, dup, _ in pieces:
            for attr in list(dup.data.color_attributes):
                dup.data.color_attributes.remove(attr)


        piece_maps = {}
        for orig, dup, _ in pieces:
            if not dup.data.uv_layers:
                dup.data.uv_layers.new(name="UVMap")
            old_mat  = dup.data.materials[0] if dup.data.materials else None
            bake_mat = old_mat.copy() if old_mat else bpy.data.materials.new(dup.name + "_mat")
            bake_mat.use_nodes = True
            dup.data.materials[0] = bake_mat

            def _new_img(suffix, non_color=False, alpha=False):
                img = bpy.data.images.new(dup.name + suffix,
                                          width=BAKE_RES, height=BAKE_RES, alpha=alpha)
                if non_color:
                    img.colorspace_settings.name = "Non-Color"
                return img

            piece_maps[dup.name] = {
                "mat":        bake_mat,
                "albedo":     _new_img("_albedo_bake"),
                "normal":     _new_img("_normal_bake",     non_color=True),
                "emission":   _new_img("_emission_bake",   non_color=True),
                "roughness":  _new_img("_roughness_bake",  non_color=True),
                "metallic":   _new_img("_metallic_bake",   non_color=True, alpha=True),
            }


        for o in scene.objects: o.select_set(False)
        for orig, dup, _ in pieces:
            maps = piece_maps[dup.name]
            context.view_layer.objects.active = dup
            dup.select_set(True)
            for bake_type, key in [
                ("DIFFUSE",   "albedo"),
                ("NORMAL",    "normal"),
                ("EMIT",      "emission"),
                ("ROUGHNESS", "roughness"),
            ]:
                _add_bake_image_node(maps["mat"], maps[key])
                try:
                    bpy.ops.object.bake(type=bake_type)
                    self.report({"INFO"}, f"{bake_type}: {dup.name}")
                except Exception as e:
                    self.report({"WARNING"}, f"{bake_type} failed {dup.name}: {e}")

            if _bake_metallic_emission(maps["mat"], maps["metallic"]):
                self.report({"INFO"}, f"METALLIC: {dup.name}")
            else:
                self.report({"WARNING"}, f"METALLIC bake failed {dup.name} — alpha will default to fully smooth")
            _pack_metallic_smoothness(maps["metallic"], maps["roughness"])

            dup.select_set(False)


        unity_arm = None
        with bpy.data.libraries.load(UNITY_RIG_FILE, link=False) as (df, dt):
            if UNITY_RIG_COL in df.collections:
                dt.collections = [UNITY_RIG_COL]
        for col in dt.collections:
            if col is None: continue
            if col.name not in {c.name for c in bake_col.children}:
                bake_col.children.link(col)
            for obj in _collect_objects(col):
                if obj.type == "ARMATURE":
                    unity_arm = obj; break

        if not unity_arm:
            self.report({"WARNING"}, f"Armature not found in {UNITY_RIG_FILE}.")


        for orig, dup, _ in pieces:
            mod = dup.modifiers.new(name="Armature", type="ARMATURE")
            if unity_arm: mod.object = unity_arm


        ref_dups = []
        for ref in ref_objs:
            ref_dup = ref.copy()
            ref_dup.data = ref.data.copy()
            ref_dup.name = ref.name + "_ref"
            ref_dup.data.materials.clear()
            blank = bpy.data.materials.new(ref.name + "_blank")
            blank.use_nodes = True
            ref_dup.data.materials.append(blank)
            bake_col.objects.link(ref_dup)
            mod = ref_dup.modifiers.new(name="Armature", type="ARMATURE")
            if unity_arm: mod.object = unity_arm
            ref_dups.append(ref_dup)

        _CHEST_SOURCES = {"Jnt.Spine.Chest", "Jnt.Spine.Chest.Tweak"}
        _CHEST_TARGET  = "Jnt.Spine.UpperChest"
        for orig, dup, _ in pieces:
            if dup.type != "MESH": continue
            for vg in dup.vertex_groups:
                if vg.name in _CHEST_SOURCES:
                    vg.name = _CHEST_TARGET

        exclude_set = set(scene.wardrobe_export_exclude_names.split(",")) if scene.wardrobe_export_exclude else set()

        if scene.wardrobe_export_optimize:
            _skip = lambda o: ("FacialSpritesMesh_LOD0" in o.name or
                               (scene.wardrobe_export_exclude_hair and "hair" in o.name.lower()))

            clothing_pieces = [(o, d, c) for o, d, c in pieces
                               if c and not _skip(o) and o.name not in exclude_set]
            body_pieces     = [(o, d, c) for o, d, c in pieces
                               if not c and not _skip(o) and o.name not in exclude_set]

            if clothing_pieces or body_pieces:
                for group_pieces, merged_name in [
                    (clothing_pieces, "Clothing"),
                    (body_pieces,     "Body"),
                ]:
                    if not group_pieces:
                        continue

                    n = len(group_pieces)
                    atlas_size, tile_size = _atlas_resolution(n)
                    cols = _math.ceil(_math.sqrt(n))
                    self.report({"INFO"}, f"{merged_name}: {n} piece(s) → {atlas_size}px atlas ({tile_size}px tiles)")

                    _remap_uvs_to_atlas(group_pieces, cols, atlas_size, tile_size)

                    atlases = {}
                    for key, name_suffix, is_nc, use_a in [
                        ("albedo",   "_albedo_atlas",   False, False),
                        ("normal",   "_normal_atlas",   True,  False),
                        ("emission", "_emission_atlas", True,  False),
                        ("metallic", "_metallic_atlas", True,  True),
                    ]:
                        atlases[key] = _build_atlas(
                            group_pieces, piece_maps,
                            key, f"{merged_name}{name_suffix}",
                            atlas_size, tile_size, is_normal=is_nc, use_alpha=use_a,
                        )[0]
                        atlases[key].filepath_raw = os.path.join(tex_dir, merged_name + f"_{key}.png")
                        atlases[key].file_format  = "PNG"
                        atlases[key].save()

                    atlas_mat = bpy.data.materials.new(merged_name + "_mat")
                    atlas_mat.use_nodes = True
                    nodes = atlas_mat.node_tree.nodes
                    links = atlas_mat.node_tree.links
                    bsdf  = nodes.get("Principled BSDF")

                    def _img_node(img, loc, link_to=None):
                        n = nodes.new("ShaderNodeTexImage")
                        n.image = img; n.location = loc
                        if link_to and bsdf:
                            links.new(n.outputs["Color"], bsdf.inputs[link_to])
                        return n

                    _img_node(atlases["albedo"],   (-300,  300), "Base Color")
                    emit_n = _img_node(atlases["emission"], (-300, -350), "Emission Color")
                    metal_n = _img_node(atlases["metallic"], (-600, -550))
                    if bsdf:
                        links.new(metal_n.outputs["Color"], bsdf.inputs["Metallic"])
                        invert_n = nodes.new("ShaderNodeInvert")
                        invert_n.location = (-300, -550)
                        links.new(metal_n.outputs["Alpha"], invert_n.inputs["Color"])
                        links.new(invert_n.outputs["Color"], bsdf.inputs["Roughness"])

                    norm_n = nodes.new("ShaderNodeTexImage")
                    norm_n.image    = atlases["normal"]
                    norm_n.location = (-600, -100)
                    norm_map = nodes.new("ShaderNodeNormalMap")
                    norm_map.location = (-300, -100)
                    links.new(norm_n.outputs["Color"], norm_map.inputs["Color"])
                    if bsdf:
                        links.new(norm_map.outputs["Normal"], bsdf.inputs["Normal"])

                    for orig, dup, _ in group_pieces:
                        dup.data.materials.clear()
                        dup.data.materials.append(atlas_mat)

                    merged = _merge_pieces(context, group_pieces, merged_name, bake_col)
                    if merged and merged.type == "MESH":
                        for vg in merged.vertex_groups:
                            if vg.name in _CHEST_SOURCES:
                                vg.name = _CHEST_TARGET
                    if merged and unity_arm:
                        mod = merged.modifiers.new(name="Armature", type="ARMATURE")
                        mod.object = unity_arm

                    pieces[:] = [p for p in pieces if p not in group_pieces]
                    if merged:
                        pieces.append((merged, merged, False))

        for orig, dup, _ in pieces:
            maps   = piece_maps.get(dup.name, {})
            if not maps: continue
            prefix = "individual_" if (hasattr(orig, "name") and orig.name in exclude_set) else ""
            for key in ("albedo", "normal", "emission", "metallic"):
                img = maps.get(key)
                if img:
                    img.filepath_raw = os.path.join(tex_dir, f"{prefix}{dup.name}_{key}.png")
                    img.file_format  = "PNG"; img.save()
            _add_bake_image_node(maps["mat"], maps["albedo"])

        export_ok = False
        try:
            for o in scene.objects: o.select_set(False)
            for _, dup, _ in pieces:
                dup.select_set(True)
            for col in bake_col.children:
                for obj in _collect_objects(col):
                    obj.select_set(True)
            for rd in ref_dups:
                rd.select_set(True)

            bpy.ops.export_scene.fbx(
                filepath=fbx_path,
                use_selection=True,
                path_mode="COPY",
                embed_textures=False,
                bake_anim=False,
                mesh_smooth_type="FACE",
                add_leaf_bones=False,
                use_mesh_modifiers=True,
                armature_nodetype="ROOT",
                use_armature_deform_only=False,
                bake_space_transform=False,
            )
            export_ok = True
        except Exception as e:
            self.report({"ERROR"}, f"FBX export failed: {e}")
        finally:
            _cleanup_export(bake_col)
            scene.render.engine = prev_engine
            scene.cycles.device = prev_device

        if export_ok:
            self.report({"INFO"}, f"Exported model.fbx → {out_dir}")

            hair_html = os.path.join(os.path.dirname(__file__), "hair_recolor.html")
            if os.path.isfile(hair_html):
                webbrowser.open(f"file:///{hair_html.replace(os.sep, '/')}")
            else:
                self.report({"WARNING"}, "hair_recolor.html not found in addon folder.")

            if scene.wardrobe_export_vrchat:
                for folder in ("Editor", "HandPoses"):
                    src = os.path.join(os.path.dirname(__file__), folder)
                    if os.path.isdir(src):
                        shutil.copytree(src, os.path.join(out_dir, folder), dirs_exist_ok=True)
                        self.report({"INFO"}, f"Copied {folder}/ to export folder.")
                    else:
                        self.report({"WARNING"}, f"{folder}/ not found in addon folder.")
                face_html = os.path.join(os.path.dirname(__file__), "face.html")
                if os.path.isfile(face_html):
                    webbrowser.open(f"file:///{face_html.replace(os.sep, '/')}")
                else:
                    self.report({"WARNING"}, "face.html not found in addon folder.")

            return {"FINISHED"}
        return {"CANCELLED"}


# Classic Bean Emulator operators


class WARDROBE_OT_bean_emulator(bpy.types.Operator):
    bl_idname      = "wardrobe.bean_emulator"
    bl_label       = "Classic Bean Emulator"
    bl_description = ("Remap MB Clothing vertex groups to match the Classic Bean body. "
                      "This is permanent and cannot be undone after saving")
    bl_options     = {"REGISTER"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.scale_y = 0.9
        col.label(text="Classic Bean Emulator", icon="ERROR")
        col.separator()
        col.label(text="This will merge the following vertex groups on every")
        col.label(text="mesh in MB Clothing and on MB_BeanTorso_LOD0:")
        col.separator()
        col.label(text="  Jnt.Spine.Root.Tweak  +  Jnt.Spine.Root")
        col.label(text="  Jnt.Spine.Chest  +  Jnt.Spine.Mid.Tweak  +  Jnt.Spine.Mid")
        col.label(text="       ↓  added into  ↓")
        col.label(text="  Jnt.Spine.Chest.Tweak")
        col.separator()
        col.label(text="The five source groups are then deleted.")
        col.separator()
        col.label(text="Any clothing appended afterwards will be processed")
        col.label(text="automatically. This operation cannot be reversed.")
        col.separator()
        col.label(text="Are you sure you want to continue?")

    def execute(self, context):
        count = _apply_bean_emulator(context)
        self.report({"INFO"}, f"Bean Emulator applied to {count} object(s).")
        return {"FINISHED"}


class WARDROBE_OT_alpha_channel_packed(bpy.types.Operator):
    bl_idname      = "wardrobe.alpha_channel_packed"
    bl_label       = "Switch all textures alpha to Channel Packed"
    bl_description = "Find every image set to sRGB and switch its alpha mode to Channel Packed"
    bl_options     = {"REGISTER", "UNDO"}

    def execute(self, context):
        count = 0
        for img in bpy.data.images:
            if img.colorspace_settings.name == "sRGB":
                img.alpha_mode = "CHANNEL_PACKED"
                count += 1
        self.report({"INFO"}, f"Set Channel Packed alpha on {count} sRGB image(s).")
        return {"FINISHED"}


# Quick Item Setup


def _load_rr_shader_group(node_name):
    """Return the named node group, loading it from Rec_Room_Shaders.blend
    if it isn't already in bpy.data.node_groups. None if it can't be found."""
    ng = bpy.data.node_groups.get(node_name)
    if ng:
        return ng
    if not os.path.isfile(SHADERS_FILE):
        return None
    with bpy.data.libraries.load(SHADERS_FILE, link=False) as (data_from, data_to):
        if node_name in data_from.node_groups:
            data_to.node_groups = [node_name]
    return bpy.data.node_groups.get(node_name)


def _input_by_name(node, name, occurrence=0):
    """Return the occurrence-th input socket on node matching name.

    Some RR shader groups reuse the same display name twice (e.g. Solid has
    a base 'Color' AND an Emission 'Color'), and Blender's name-based socket
    lookup only ever returns the first match, so duplicates need to be
    addressed by position instead of by name alone.
    """
    matches = [s for s in node.inputs if s.name == name]
    return matches[occurrence] if len(matches) > occurrence else None


def _input_like(node, must_contain, must_not_contain=()):
    """Find an input socket whose name contains every string in
    must_contain and none of must_not_contain (case-insensitive).

    More forgiving than an exact name match for sockets with punctuation in
    their label (e.g. '(RGBA)', 'Gloss (Alpha)') where an exact string
    compare can silently miss if the label isn't quite what it looks like.
    """
    for s in node.inputs:
        name = s.name.lower()
        if all(m.lower() in name for m in must_contain) and not any(m.lower() in name for m in must_not_contain):
            return s
    return None


def _emission_color_input(node):
    """The Emission section's color socket. Confirmed via a live node-group
    interface dump that the real socket name is the full 'Emission Color'
    (the sidebar UI strips the redundant 'Emission' panel-name prefix from
    the displayed label, showing just 'Color' -- but the underlying name is
    not 'Color'). Match on both words directly rather than reconstructing
    position relative to a 'Strength' socket, since that socket is actually
    named 'Emission Strength' too and never matched a bare 'strength' check."""
    return _input_like(node, ["emission", "color"])


def _base_color_input(node, shader_key):
    if shader_key == "SOLID_AVATAR":
        return _input_by_name(node, "Color", occurrence=0)
    if shader_key == "RGBA_AVATAR":
        return _input_by_name(node, "Black", occurrence=0)
    return None


def _set_color_input(socket, rgb):
    if socket is None or rgb is None:
        return
    socket.default_value = (rgb[0], rgb[1], rgb[2], 1.0)


def _srgb_to_linear(c):
    c = min(1.0, max(0.0, c))
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _mat_color_to_linear(rgb):
    """Unity .mat colors are typically picked in sRGB space, but Blender's
    socket default_value is always linear -- convert so they actually match
    instead of just looking 'close'."""
    if rgb is None:
        return None
    return tuple(_srgb_to_linear(c) for c in rgb)


_QUICK_MAT_COLOR_PATTERNS = {
    "red":      r"_Red_Col:\s*\{\s*r:\s*([\d.]+),\s*g:\s*([\d.]+),\s*b:\s*([\d.]+)",
    "green":    r"_Green_Col:\s*\{\s*r:\s*([\d.]+),\s*g:\s*([\d.]+),\s*b:\s*([\d.]+)",
    "blue":     r"_Blue_Col:\s*\{\s*r:\s*([\d.]+),\s*g:\s*([\d.]+),\s*b:\s*([\d.]+)",
    "emission": r"_Emission_Col:\s*\{\s*r:\s*([\d.]+),\s*g:\s*([\d.]+),\s*b:\s*([\d.]+)",
}

_QUICK_MAT_BASE_PATTERNS = [
    r"_Base_Col:\s*\{\s*r:\s*([\d.]+),\s*g:\s*([\d.]+),\s*b:\s*([\d.]+)",
]


def _parse_quick_mat_colors(path):
    """Pull only the color fields out of a Unity .mat file (same fields the
    reference HTML reads) -- no floats, per the 'just colors' instruction."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        return {}

    colors = {}
    for key, pattern in _QUICK_MAT_COLOR_PATTERNS.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            colors[key] = tuple(min(1.0, max(0.0, float(g))) for g in m.groups())

    for pattern in _QUICK_MAT_BASE_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            colors["base"] = tuple(min(1.0, max(0.0, float(g))) for g in m.groups())
            break

    return colors


def _fbx_body_type(fname):
    """Return 'FB', 'MB', or None from the filename's FB_/MB_ marker,
    tolerating a leading bracket/paren before it (e.g. '(MB_Item).fbx')."""
    stripped = fname.lstrip("([{ \t")
    if stripped.startswith("FB_"):
        return "FB"
    if stripped.startswith("MB_"):
        return "MB"
    return None


def _scan_quick_folder(folder):
    """Find the *_Tex/_Spec/_Norm/_Emit textures and FB_*/MB_* fbx files in
    the item folder."""
    tex_paths   = {"tex": None, "spec": None, "norm": None, "emit": None}
    fbx_by_type = {"FB": [], "MB": []}
    suffix_map  = {"tex": "_tex", "spec": "_spec", "norm": "_norm", "emit": "_emit"}
    img_exts    = (".png", ".tga", ".jpg", ".jpeg", ".tif", ".tiff")

    for fname in sorted(os.listdir(folder)):
        full = os.path.join(folder, fname)
        if not os.path.isfile(full):
            continue
        stem, ext = os.path.splitext(fname.lower())
        if ext == ".fbx":
            body_type = _fbx_body_type(fname)
            if body_type:
                fbx_by_type[body_type].append(full)
            continue
        if ext in img_exts:
            for key, suffix in suffix_map.items():
                if stem.endswith(suffix):
                    tex_paths[key] = full
                    break

    return tex_paths, fbx_by_type


def _quick_img_tex_node(nodes, path, location, non_color=False, channel_packed=False):
    if not path:
        return None
    try:
        img = bpy.data.images.load(path, check_existing=True)
    except Exception:
        return None
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    if channel_packed:
        img.alpha_mode = "CHANNEL_PACKED"
    node = nodes.new("ShaderNodeTexImage")
    node.image    = img
    node.location = location
    return node


def _build_quick_material(name, shader_key, mat_colors, tex_paths):
    """Build a fresh material wired with the RR avatar shader for shader_key,
    applying the parsed .mat colors and any discovered textures.
    Returns (material, error_message) -- material is None on failure.
    """
    node_name = SHADER_NODE_NAME[shader_key]
    ng = _load_rr_shader_group(node_name)
    if not ng:
        return None, f"Node group '{node_name}' not found in Rec_Room_Shaders.blend"

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    for n in list(nodes):
        nodes.remove(n)

    out_node = nodes.new("ShaderNodeOutputMaterial")
    rr_node  = nodes.new("ShaderNodeGroup")
    rr_node.node_tree = ng
    rr_node.name      = node_name
    rr_node.width     = 360
    rr_node.location  = (out_node.location.x - 400, out_node.location.y)
    links.new(rr_node.outputs[0], out_node.inputs["Surface"])

    norm_node = None
    ng_normals = _load_rr_shader_group("[RR] Compressed Unity Normals")
    if ng_normals:
        norm_node = nodes.new("ShaderNodeGroup")
        norm_node.node_tree = ng_normals
        norm_node.name      = "[RR] Compressed Unity Normals"
        norm_node.width     = 360
        norm_node.location  = (rr_node.location.x - 400, rr_node.location.y - 250)
        if "Normal" in rr_node.inputs:
            links.new(norm_node.outputs[0], rr_node.inputs["Normal"])


    if shader_key == "RGBA_AVATAR":
        main_tex_in   = _input_like(rr_node, ["rgba"], ["alpha"])
        alpha_rgba_in = _input_like(rr_node, ["alpha", "rgba"])
    else:
        main_tex_in   = _base_color_input(rr_node, shader_key)
        alpha_rgba_in = None
    if tex_paths.get("tex") and (main_tex_in or alpha_rgba_in):
        tex_node = _quick_img_tex_node(nodes, tex_paths["tex"],
                                       (rr_node.location.x - 700, rr_node.location.y + 300),
                                       channel_packed=True)
        if tex_node:
            if main_tex_in:
                links.new(tex_node.outputs["Color"], main_tex_in)
            if alpha_rgba_in:
                links.new(tex_node.outputs["Alpha"], alpha_rgba_in)


    if tex_paths.get("spec"):
        spec_node = _quick_img_tex_node(nodes, tex_paths["spec"],
                                        (rr_node.location.x - 700, rr_node.location.y),
                                        non_color=True)
        if spec_node:
            tint_in  = _input_like(rr_node, ["tint"])
            gloss_in = _input_like(rr_node, ["gloss"], ["strength"])
            if tint_in:
                links.new(spec_node.outputs["Color"], tint_in)
            if gloss_in:
                links.new(spec_node.outputs["Alpha"], gloss_in)


    if tex_paths.get("norm") and norm_node:
        norm_tex = _quick_img_tex_node(nodes, tex_paths["norm"],
                                       (norm_node.location.x - 400, norm_node.location.y),
                                       non_color=True)
        if norm_tex:
            if "Color" in norm_node.inputs:
                links.new(norm_tex.outputs["Color"], norm_node.inputs["Color"])
            if "Alpha" in norm_node.inputs:
                links.new(norm_tex.outputs["Alpha"], norm_node.inputs["Alpha"])


    emit_in = _emission_color_input(rr_node)
    if tex_paths.get("emit") and emit_in:
        emit_node = _quick_img_tex_node(nodes, tex_paths["emit"],
                                        (rr_node.location.x - 700, rr_node.location.y - 350))
        if emit_node:
            links.new(emit_node.outputs["Color"], emit_in)
    else:
        _set_color_input(emit_in, (0.0, 0.0, 0.0))


    if shader_key == "RGBA_AVATAR":
        _set_color_input(_input_by_name(rr_node, "Red"),   _mat_color_to_linear(mat_colors.get("red")))
        _set_color_input(_input_by_name(rr_node, "Green"), _mat_color_to_linear(mat_colors.get("green")))
        _set_color_input(_input_by_name(rr_node, "Blue"),  _mat_color_to_linear(mat_colors.get("blue")))
    _set_color_input(_base_color_input(rr_node, shader_key), _mat_color_to_linear(mat_colors.get("base")))

    return mat, ""


def _import_and_clean_fbx(fbx_path, context):
    """Import fbx_path, strip its armature, any LOD1/LOD2 mesh, and any
    empty, rotate the remaining mesh(es) 90 degrees on X to match the rig's
    orientation, and return whatever mesh object(s) remain."""
    before = {o.name for o in bpy.data.objects}
    try:
        bpy.ops.import_scene.fbx(filepath=fbx_path)
    except Exception:
        return []
    new_objs = [o for o in bpy.data.objects if o.name not in before]

    keep = []
    for obj in new_objs:
        lname = obj.name.lower()
        if obj.type in ("ARMATURE", "EMPTY") or "lod1" in lname or "lod2" in lname:
            for col in list(obj.users_collection):
                col.objects.unlink(obj)
            bpy.data.objects.remove(obj, do_unlink=True)
        else:
            keep.append(obj)

    for obj in keep:
        if obj.type != "MESH":
            continue
        obj.rotation_euler.x += _math.radians(90)
        for o in context.scene.objects:
            o.select_set(False)
        context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        obj.select_set(False)

    return keep


def _quick_get_or_make_collection(name, parent):
    col = bpy.data.collections.get(name)
    if not col:
        col = bpy.data.collections.new(name)
    if parent is not None and col.name not in {c.name for c in parent.children}:
        parent.children.link(col)
    return col


def _quick_move_to_collection(obj, target_col):
    for col in list(obj.users_collection):
        col.objects.unlink(obj)
    target_col.objects.link(obj)


def _run_quick_item_setup(operator, context, folder):
    if not folder or not os.path.isdir(folder):
        operator.report({"ERROR"}, "No valid folder selected.")
        return {"CANCELLED"}

    scene      = context.scene
    shader_key = scene.wardrobe_quick_shader
    mat_path   = scene.wardrobe_quick_mat_path

    view_settings = scene.view_settings
    if view_settings.view_transform != "Standard":
        view_settings.view_transform = "Standard"

    tex_paths, fbx_by_type = _scan_quick_folder(folder)

    if not fbx_by_type["FB"] and not fbx_by_type["MB"]:
        operator.report({"ERROR"}, "No FB_*.fbx or MB_*.fbx found in that folder.")
        return {"CANCELLED"}

    mat_colors = {}
    if shader_key == "RGBA_AVATAR" and mat_path:
        mat_colors = _parse_quick_mat_colors(mat_path)

    item_name = os.path.basename(os.path.normpath(folder)) or "Item"
    mat, err = _build_quick_material(item_name + "_mat", shader_key, mat_colors, tex_paths)
    if not mat:
        operator.report({"ERROR"}, err or "Failed to build material.")
        return {"CANCELLED"}


    item_col = _quick_get_or_make_collection("Item", None)
    if item_col.name not in {c.name for c in scene.collection.children}:
        scene.collection.children.link(item_col)

    imported_count = 0
    for body_type in ("FB", "MB"):
        fbx_list = fbx_by_type[body_type]
        if not fbx_list:
            continue
        sub_col = _quick_get_or_make_collection(body_type, item_col)
        for fbx_path in fbx_list:
            kept = _import_and_clean_fbx(fbx_path, context)
            for obj in kept:
                if obj.type == "MESH":
                    obj.data.materials.clear()
                    obj.data.materials.append(mat)
                _quick_move_to_collection(obj, sub_col)
                imported_count += 1

    bpy.data.orphans_purge(do_recursive=True)

    body_types_used = len([k for k in fbx_by_type if fbx_by_type[k]])
    operator.report({"INFO"},
                     f"Quick Item Setup done — {imported_count} object(s) across {body_types_used} body type(s).")
    return {"FINISHED"}


class WARDROBE_OT_quick_setup_start(bpy.types.Operator):
    bl_idname      = "wardrobe.quick_setup_start"
    bl_label       = "Quick Item Setup"
    bl_description = "Build a Rec Room item material from Unity assets and import its FB/MB meshes"
    bl_options     = {"REGISTER"}

    shader_type: bpy.props.EnumProperty(
        name="Shader",
        items=[
            ("RGBA_AVATAR",  "RGBA Rec Room Shader",  "Channel-masked, multi-color item"),
            ("SOLID_AVATAR", "Solid Rec Room Avatar Shader", "Single flat color item"),
        ],
        default="RGBA_AVATAR",
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        self.layout.prop(self, "shader_type", expand=True)

    def execute(self, context):
        context.scene.wardrobe_quick_shader = self.shader_type
        if self.shader_type == "RGBA_AVATAR":
            bpy.ops.wardrobe.quick_setup_pick_mat('INVOKE_DEFAULT')
        else:
            context.scene.wardrobe_quick_mat_path = ""
            bpy.ops.wardrobe.quick_setup_pick_folder('INVOKE_DEFAULT')
        return {"FINISHED"}


class WARDROBE_OT_quick_setup_pick_mat(bpy.types.Operator):
    bl_idname      = "wardrobe.quick_setup_pick_mat"
    bl_label       = "Pick .mat File"
    bl_description = "Select the Unity .mat file for this item's colors"
    bl_options     = {"REGISTER"}

    filepath:    bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.mat;*.txt;*.asset", options={"HIDDEN"})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        context.scene.wardrobe_quick_mat_path = self.filepath
        bpy.ops.wardrobe.quick_setup_pick_folder('INVOKE_DEFAULT')
        return {"FINISHED"}


class WARDROBE_OT_quick_setup_pick_folder(bpy.types.Operator):
    bl_idname      = "wardrobe.quick_setup_pick_folder"
    bl_label       = "Pick Item Folder"
    bl_description = "Select the folder with this item's textures and FB_/MB_ fbx files"
    bl_options     = {"REGISTER", "UNDO"}

    directory: bpy.props.StringProperty(subtype="DIR_PATH")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        return _run_quick_item_setup(self, context, self.directory)


class WARDROBE_OT_load_mat_colors(bpy.types.Operator):
    bl_idname      = "wardrobe.load_mat_colors"
    bl_label       = "Load Colors from .mat"
    bl_description = ("Pick a Unity .mat file and apply its color values "
                      "to the active object's active material "
                      "(looks for an RR shader node group inside it)")
    bl_options     = {"REGISTER", "UNDO"}

    filepath:    bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.mat;*.txt;*.asset", options={"HIDDEN"})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != "MESH":
            self.report({"ERROR"}, "No active mesh object."); return {"CANCELLED"}
        mat = obj.active_material
        if not mat or not mat.use_nodes:
            self.report({"ERROR"}, "No active material with nodes."); return {"CANCELLED"}


        rr_node = None
        for node in mat.node_tree.nodes:
            if node.type == "GROUP" and node.node_tree:
                name = node.node_tree.name
                if name in (SHADER_NODE_NAME["RGBA_AVATAR"], SHADER_NODE_NAME["SOLID_AVATAR"]):
                    rr_node = node
                    break
        if not rr_node:
            self.report({"ERROR"}, "No RR shader node group found in material."); return {"CANCELLED"}

        shader_key = ("RGBA_AVATAR"
                      if rr_node.node_tree.name == SHADER_NODE_NAME["RGBA_AVATAR"]
                      else "SOLID_AVATAR")

        mat_colors = _parse_quick_mat_colors(self.filepath)
        if not mat_colors:
            self.report({"WARNING"}, "No color values found in .mat file."); return {"CANCELLED"}

        if shader_key == "RGBA_AVATAR":
            _set_color_input(_input_by_name(rr_node, "Red"),   _mat_color_to_linear(mat_colors.get("red")))
            _set_color_input(_input_by_name(rr_node, "Green"), _mat_color_to_linear(mat_colors.get("green")))
            _set_color_input(_input_by_name(rr_node, "Blue"),  _mat_color_to_linear(mat_colors.get("blue")))
        _set_color_input(_base_color_input(rr_node, shader_key), _mat_color_to_linear(mat_colors.get("base")))


        emit_in = _emission_color_input(rr_node)
        if emit_in and not emit_in.is_linked:
            emit_val = _mat_color_to_linear(mat_colors.get("emission"))
            if emit_val:
                _set_color_input(emit_in, emit_val)
            else:
                _set_color_input(emit_in, (0.0, 0.0, 0.0))

        self.report({"INFO"}, f"Colors applied to '{mat.name}' from .mat file.")
        return {"FINISHED"}


# Panel


class WARDROBE_PT_main(bpy.types.Panel):
    bl_label = "Rec Room Wardrobe"; bl_idname = "WARDROBE_PT_main"
    bl_space_type = "VIEW_3D"; bl_region_type = "UI"; bl_category = "RR Archive"

    def draw_header(self, context):
        ico = _rr_icon()
        if ico:
            self.layout.label(text="", icon_value=ico)

    def draw(self, context):
        layout, scene = self.layout, context.scene

        if not scene.wardrobe_enabled:
            col = layout.column(align=True)
            col.scale_y = 1.6
            col.operator("wardrobe.enable", text="Enable Wardrobe Browser", icon="PLAY")
            return

        box = layout.box()
        rrow = box.row(align=True)
        rrow.prop(scene, "wardrobe_rig_open", text="Rec Room Rig",
                  icon="TRIA_DOWN" if scene.wardrobe_rig_open else "TRIA_RIGHT",
                  emboss=False)
        if scene.wardrobe_rig_open:
            rig = _rig_in_scene()
            if rig:
                ok, missing = _check_rig(rig)
                row = box.row()
                row.alert = not ok
                row.label(text=f"{rig.name} ✓" if ok else f"Missing: {', '.join(missing)}",
                          icon="CHECKMARK" if ok else "ERROR")
                sub = box.row()
                sub.enabled = False
                sub.operator("wardrobe.append_rig", text="Rig already in scene", icon="ADD")
                box.operator("wardrobe.repatch_rig_ui", text="Re-patch Rig UI", icon="FILE_REFRESH")

                box.separator()
                if scene.wardrobe_bean_active:
                    box.operator("wardrobe.bean_emulator",
                                 text="Re-apply Bean Emulator", icon="MOD_SOLIDIFY")
                else:
                    box.operator("wardrobe.bean_emulator",
                                 text="Classic Bean Emulator", icon="MOD_SOLIDIFY")
            else:
                box.operator("wardrobe.append_rig", text="Set Up Scene", icon="SCENE_DATA")

        # Dev extras
        a = context.preferences.addons.get(__name__)
        if a and a.preferences.dev_extras:
            box = layout.box()
            drow = box.row(align=True)
            drow.prop(scene, "wardrobe_devextras_open", text="Development Extras",
                      icon="TRIA_DOWN" if scene.wardrobe_devextras_open else "TRIA_RIGHT",
                      emboss=False)
            if scene.wardrobe_devextras_open:
                row = box.row(align=True)
                row.prop(a.preferences, "shader_type", text="")
                row.operator("wardrobe.setup_material", text="Setup Material", icon="NODE_MATERIAL")
                box.operator("wardrobe.setup_render", text="Setup Render Scene", icon="SCENE")
                box.operator("wardrobe.alpha_channel_packed", text="Switch all textures alpha to Channel Packed", icon="IMAGE_ALPHA")
                box.separator()
                box.operator("wardrobe.quick_setup_start", text="Quick Item Setup", icon="IMPORT")
                box.operator("wardrobe.load_mat_colors", text="Load Colors from .mat", icon="EYEDROPPER")

        layout.separator()

        box = layout.box()
        row = box.row(align=True)
        row.prop(scene, "wardrobe_browser_open", text="Wardrobe Browser",
                 icon="TRIA_DOWN" if scene.wardrobe_browser_open else "TRIA_RIGHT",
                 emboss=False)
        if scene.wardrobe_browser_open:
            ibox = box.box()
            irow = ibox.row(align=True)
            if INDEX_LOADING:
                irow.label(text="Loading…", icon="TIME")
            elif INDEX_ERROR:
                irow.alert = True; irow.label(text=INDEX_ERROR, icon="ERROR"); irow.alert = False
                ibox.operator("wardrobe.fetch_index", text="Retry", icon="FILE_REFRESH")
            elif INDEX_CACHE is None:
                irow.label(text="Not loaded", icon="QUESTION")
                ibox.operator("wardrobe.fetch_index", text="Load from GitHub", icon="URL")
                fetch_index()
            else:
                irow.label(text="Index loaded ✓", icon="CHECKMARK")
                irow.operator("wardrobe.fetch_index", text="", icon="FILE_REFRESH")
                irow.operator("wardrobe.clear_cache", text="", icon="TRASH")

                box.separator()
                q = scene.wardrobe_search.strip()
                row = box.row(align=True)
                row.prop(scene, "wardrobe_search", text="", icon="VIEWZOOM")
                if q: row.operator("wardrobe.clear_search", text="", icon="X")
                box.separator()

                open_grps = _open_set(context)
                if q:
                    results = search_items(q)
                    box.label(text=f'{len(flatten(results))} result(s):' if results else f'No results for "{q}"',
                              icon="VIEWZOOM" if results else "INFO")
                    self._category_grid(box, results, open_grps, scene.wardrobe_selected_blend,
                                        "wardrobe.apply_item", load_preview, "blend", lambda i: i["label"],
                                        "wardrobe.toggle_group")
                else:
                    box.prop(scene, "wardrobe_category", text="")
                    box.separator()
                    self._category_grid(box, (INDEX_CACHE or {}).get(scene.wardrobe_category, []),
                                        open_grps, scene.wardrobe_selected_blend,
                                        "wardrobe.apply_item", load_preview, "blend", lambda i: i["label"],
                                        "wardrobe.toggle_group")

        layout.separator()

        pbox = layout.box()
        prow = pbox.row(align=True)
        prow.prop(scene, "wardrobe_props_open", text="Props Browser",
                  icon="TRIA_DOWN" if scene.wardrobe_props_open else "TRIA_RIGHT",
                  emboss=False)
        if scene.wardrobe_props_open:
            ibox = pbox.box()
            irow = ibox.row(align=True)
            if PROPS_LOADING:
                irow.label(text="Loading…", icon="TIME")
            elif PROPS_ERROR:
                irow.alert = True; irow.label(text=PROPS_ERROR, icon="ERROR"); irow.alert = False
                ibox.operator("wardrobe.fetch_props", text="Retry", icon="FILE_REFRESH")
            elif PROPS_CACHE is None:
                irow.label(text="Not loaded", icon="QUESTION")
                ibox.operator("wardrobe.fetch_props", text="Load from GitHub", icon="URL")
                fetch_props()
            else:
                irow.label(text="Props loaded ✓", icon="CHECKMARK")
                irow.operator("wardrobe.fetch_props", text="", icon="FILE_REFRESH")
                pbox.separator()

                pbox.prop(scene, "wardrobe_prop_category", expand=True)
                pbox.separator()

                q = scene.wardrobe_prop_search.strip()
                srow = pbox.row(align=True)
                srow.prop(scene, "wardrobe_prop_search", text="", icon="VIEWZOOM")
                if q: srow.operator("wardrobe.clear_prop_search", text="", icon="X")
                pbox.separator()
                open_grps = set(x for x in scene.wardrobe_open_prop_groups.split(",") if x)
                sel = scene.wardrobe_selected_prop_blend
                cat = scene.wardrobe_prop_category
                items = search_props(q, cat) if q else all_props(cat)
                if q and not items:
                    pbox.label(text=f'No results for "{q}"', icon="INFO")
                else:
                    self._category_grid(pbox, items, open_grps, sel,
                                        "wardrobe.apply_prop", load_prop_preview, "blend", lambda i: i["label"],
                                        "wardrobe.toggle_prop_group")


        layout.separator()

        fbox = layout.box()
        frow = fbox.row(align=True)
        frow.prop(scene, "wardrobe_face_open", text="Face Browser",
                  icon="TRIA_DOWN" if scene.wardrobe_face_open else "TRIA_RIGHT",
                  emboss=False)
        if scene.wardrobe_face_open:
            ibox = fbox.box()
            irow = ibox.row(align=True)
            if FACE_LOADING:
                irow.label(text="Loading…", icon="TIME")
            elif FACE_ERROR:
                irow.alert = True; irow.label(text=FACE_ERROR, icon="ERROR"); irow.alert = False
                ibox.operator("wardrobe.fetch_face", text="Retry", icon="FILE_REFRESH")
            elif FACE_CACHE is None:
                irow.label(text="Not loaded", icon="QUESTION")
                ibox.operator("wardrobe.fetch_face", text="Load from GitHub", icon="URL")
                fetch_face()
            else:
                irow.label(text="Face index loaded ✓", icon="CHECKMARK")
                irow.operator("wardrobe.fetch_face", text="", icon="FILE_REFRESH")
                fbox.separator()

                fbox.prop(scene, "wardrobe_face_category", expand=True)
                fbox.separator()

                q = scene.wardrobe_face_search.strip()
                srow = fbox.row(align=True)
                srow.prop(scene, "wardrobe_face_search", text="", icon="VIEWZOOM")
                if q: srow.operator("wardrobe.clear_face_search", text="", icon="X")
                fbox.separator()

                cat   = scene.wardrobe_face_category
                sel   = scene.wardrobe_selected_face_blend
                items = search_face_items(q, cat) if q else all_face_items(cat)
                if q and not items:
                    fbox.label(text=f'No results for "{q}"', icon="INFO")
                else:
                    self._face_category_grid(fbox, items, sel, cat)

        layout.separator()

        ebox = layout.box()
        erow = ebox.row(align=True)
        erow.prop(scene, "wardrobe_export_open", text="Unity Export (Beta)",
                  icon="TRIA_DOWN" if scene.wardrobe_export_open else "TRIA_RIGHT",
                  emboss=False)
        if scene.wardrobe_export_open:
            ebox.prop(scene, "wardrobe_export_body", text="Body")
            ebox.prop(scene, "wardrobe_bake_device", text="Device")
            if scene.wardrobe_export_body == "MB":
                col = ebox.column(align=True)
                col.scale_y = 0.65
                col.label(text="Exports full body mesh with it,", icon="INFO")
                col.label(text="its a limitation of how unity handles")
                col.label(text="the rig. After its set to humanoid")
                col.label(text="and applied you should be able to")
                col.label(text="delete the FB mesh.")
            col2 = ebox.column(align=True)
            col2.scale_y = 0.65
            col2.label(text="FB & MB Clothing must be enabled", icon="ERROR")
            col2.label(text="in Rig UI for export to work.")
            ebox.prop(scene, "wardrobe_export_optimize", text="Optimize on Export (Recommended)")


            row_hair = ebox.row(align=True)
            row_hair.enabled = scene.wardrobe_export_optimize
            row_hair.prop(scene, "wardrobe_export_exclude_hair", text="Exclude Hair from Optimize")


            row = ebox.row(align=True)
            row.enabled = not scene.wardrobe_export_exclude
            row.prop(scene, "wardrobe_export_selected", text="Export Selected Clothing Only")


            row2 = ebox.row(align=True)
            row2.enabled = not scene.wardrobe_export_selected and scene.wardrobe_export_optimize
            row2.prop(scene, "wardrobe_export_exclude", text="Exclude Selected from Optimize")

            row = ebox.row(align=True)
            row.prop(scene, "wardrobe_export_vrchat", text="Export For VRChat")
            ebox.operator("wardrobe.export_unity", text="Export for Unity", icon="EXPORT")


            ebox.separator()
            drow = ebox.row(align=True)
            drow.prop(scene, "wardrobe_debug_open", text="Debug",
                      icon="TRIA_DOWN" if scene.wardrobe_debug_open else "TRIA_RIGHT",
                      emboss=False)
            if scene.wardrobe_debug_open:
                ebox.operator("wardrobe.open_face_html", text="Open face.html", icon="HIDE_OFF")
                ebox.operator("wardrobe.open_hair_html", text="Open hair_recolor.html", icon="PARTICLEMODE")


    def _grid_tile(self, grid, op_id, label, blend, ico, is_sel,
                   extra_fn=None, item=None, use_box=False):
        outer = grid.column(align=True)
        cell  = outer.box().column(align=True) if use_box else outer
        if ico:
            cell.template_icon(icon_value=ico, scale=5.0)
        else:
            row = cell.row(); row.scale_y = 5.0
            row.label(text="", icon="IMAGE_DATA")
        btn = cell.row(align=True)
        btn.alert = is_sel
        op = btn.operator(op_id, text=label, emboss=True, depress=is_sel)
        if extra_fn:
            extra_fn(op, item, label)
        else:
            op.blend_path = blend
            op.item_label = label

    def _category_grid(self, layout, items, open_grps, sel,
                        op_id, load_fn, blend_key, label_fn, toggle_op):
        grid = layout.grid_flow(row_major=True, columns=0,
                                even_columns=True, even_rows=True, align=True)

        for item in items:
            is_group = item.get("children") is not None and len(item["children"]) > 0
            if is_group:
                key = _safe_key(item["label"]); is_open = key in open_grps
                ico = load_fn(item.get("preview")) if item.get("preview") else 0
                if not ico and item.get("preview") and load_fn == load_preview:
                    _prefetch_single(item["preview"])
                cell = grid.column(align=True)
                if ico:
                    cell.template_icon(icon_value=ico, scale=5.0)
                else:
                    row = cell.row(); row.scale_y = 5.0
                    row.label(text="", icon="TRIA_DOWN" if is_open else "TRIA_RIGHT")
                btn = cell.row(align=True)
                op = btn.operator(toggle_op, text=item["label"],
                                  icon="TRIA_DOWN" if is_open else "TRIA_RIGHT",
                                  emboss=True)
                op.group_key = key
                if is_open:
                    for child in item["children"]:
                        blend = child.get(blend_key, "") if isinstance(blend_key, str) else blend_key(child)
                        if not blend: continue
                        lbl = label_fn(child)
                        ico_c = load_fn(child.get("preview")) if child.get("preview") else 0
                        self._grid_tile(grid, op_id, lbl, blend, ico_c, blend == sel,
                                        use_box=True)
            else:
                blend = item.get(blend_key, "") if isinstance(blend_key, str) else blend_key(item)
                if not blend: continue
                lbl = label_fn(item)
                ico = load_fn(item.get("preview")) if item.get("preview") else 0
                self._grid_tile(grid, op_id, lbl, blend, ico, blend == sel)

    def _face_category_grid(self, layout, items, sel, cat):
        grid = layout.grid_flow(row_major=True, columns=0,
                                even_columns=True, even_rows=False, align=True)
        for item in items:
            label  = _face_label(item)
            folder = item["folder"]
            ico    = load_face_preview(item["preview"]) if item.get("preview") else 0
            def _extra(op, it, lbl, _cat=cat):
                op.blend_path = it["folder"]
                op.item_label = lbl
                op.category   = _cat
            self._grid_tile(grid, "wardrobe.apply_face", label, folder,
                            ico, folder == sel, extra_fn=_extra, item=item)

    def _item(self, layout, item, open_grps, sel): pass
    def _face_item(self, layout, item, sel, cat): pass
    def _prop_item(self, layout, item, open_grps, sel): pass


# Registration


classes = [
    WardrobePreferences,
    WARDROBE_OT_open_url,
    WARDROBE_OT_open_face_html, WARDROBE_OT_open_hair_html,
    WARDROBE_OT_clear_cache, WARDROBE_OT_setup_render, WARDROBE_OT_setup_material,
    WARDROBE_OT_repatch_rig_ui, WARDROBE_OT_enable, WARDROBE_OT_append_rig,
    WARDROBE_OT_fetch_index, WARDROBE_OT_clear_search,
    WARDROBE_OT_toggle_group, WARDROBE_OT_select_item, WARDROBE_OT_append_selected,
    WARDROBE_OT_apply_item, WARDROBE_OT_apply_prop, WARDROBE_OT_apply_face,
    WARDROBE_OT_fetch_props, WARDROBE_OT_clear_prop_search, WARDROBE_OT_toggle_prop_group,
    WARDROBE_OT_select_prop, WARDROBE_OT_append_prop,
    WARDROBE_OT_fetch_face, WARDROBE_OT_clear_face_search,
    WARDROBE_OT_select_face_item, WARDROBE_OT_apply_face_item,
    WARDROBE_OT_set_bake_device, WARDROBE_OT_export_unity,
    WARDROBE_OT_bean_emulator,
    WARDROBE_OT_alpha_channel_packed,
    WARDROBE_OT_quick_setup_start,
    WARDROBE_OT_quick_setup_pick_mat,
    WARDROBE_OT_quick_setup_pick_folder,
    WARDROBE_OT_load_mat_colors,
    WARDROBE_PT_main,
]

_delete_cache_on_exit_enabled = True

def _clear_cache_on_exit():
    if not _delete_cache_on_exit_enabled:
        return
    _wipe_cache_dir()


def register():
    _load_custom_icons()
    atexit.register(_clear_cache_on_exit)
    for cls in classes: bpy.utils.register_class(cls)
    def _init_pref():
        global _delete_cache_on_exit_enabled
        try:
            prefs = bpy.context.preferences.addons.get(__name__)
            if prefs:
                _delete_cache_on_exit_enabled = prefs.preferences.delete_cache_on_exit
        except Exception: pass
    bpy.app.timers.register(_init_pref, first_interval=0.5)

    bpy.types.Scene.wardrobe_enabled        = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.wardrobe_category       = bpy.props.EnumProperty(name="Category", items=[(c,c,"") for c in CATEGORIES])
    bpy.types.Scene.wardrobe_search         = bpy.props.StringProperty(name="Search", default="")
    bpy.types.Scene.wardrobe_selected_blend = bpy.props.StringProperty(default="")
    bpy.types.Scene.wardrobe_selected_label = bpy.props.StringProperty(default="")
    bpy.types.Scene.wardrobe_open_groups    = bpy.props.StringProperty(default="")
    bpy.types.Scene.wardrobe_browser_open   = bpy.props.BoolProperty(name="Wardrobe", default=False)
    bpy.types.Scene.wardrobe_props_open     = bpy.props.BoolProperty(name="Props", default=False)
    bpy.types.Scene.wardrobe_prop_category  = bpy.props.EnumProperty(
        name="Prop Category",
        items=[(c, c, "") for c in PROP_CATEGORIES],
        default="Weapons",
    )
    bpy.types.Scene.wardrobe_prop_search    = bpy.props.StringProperty(name="Search", default="")
    bpy.types.Scene.wardrobe_selected_prop_blend = bpy.props.StringProperty(default="")
    bpy.types.Scene.wardrobe_selected_prop_label = bpy.props.StringProperty(default="")
    bpy.types.Scene.wardrobe_open_prop_groups    = bpy.props.StringProperty(default="")
    bpy.types.Scene.wardrobe_export_body    = bpy.props.EnumProperty(
        name="Body Type",
        items=[("FB","Full Body (FB)",""),("MB","Bean Body (MB)","")],
        default="FB",
    )
    bpy.types.Scene.wardrobe_bake_device    = bpy.props.EnumProperty(
        name="Bake Device",
        items=lambda self, ctx: _get_cycles_devices(),
    )
    bpy.types.Scene.wardrobe_export_optimize = bpy.props.BoolProperty(
        name="Optimize on Export",
        description="Atlas + merge clothing and body meshes before export (Recommended)",
        default=True,
    )
    bpy.types.Scene.wardrobe_export_exclude_hair = bpy.props.BoolProperty(
        name="Exclude Hair from Optimize",
        description="Hair meshes are baked individually and excluded from the atlas/merge step",
        default=True,
    )
    bpy.types.Scene.wardrobe_export_selected = bpy.props.BoolProperty(
        name="Export Selected Clothing Only",
        description="Only bake and export the clothing objects currently selected in the viewport",
        default=False,
    )
    bpy.types.Scene.wardrobe_export_exclude  = bpy.props.BoolProperty(
        name="Exclude Selected from Optimize",
        description="Selected clothing objects are baked individually and excluded from atlas/merge",
        default=False,
    )
    bpy.types.Scene.wardrobe_export_exclude_names = bpy.props.StringProperty(default="")
    bpy.types.Scene.wardrobe_export_vrchat  = bpy.props.BoolProperty(
        name="Export For VRChat",
        description="Open face.html in your browser after export for VRChat face setup",
        default=False,
    )
    bpy.types.Scene.wardrobe_export_open    = bpy.props.BoolProperty(name="Unity Export", default=False)
    bpy.types.Scene.wardrobe_debug_open     = bpy.props.BoolProperty(name="Debug", default=False)
    bpy.types.Scene.wardrobe_rig_open       = bpy.props.BoolProperty(name="Rec Room Rig", default=True)
    bpy.types.Scene.wardrobe_devextras_open = bpy.props.BoolProperty(name="Development Extras", default=False)

    bpy.types.Scene.wardrobe_face_open              = bpy.props.BoolProperty(name="Face", default=False)
    bpy.types.Scene.wardrobe_face_category          = bpy.props.EnumProperty(
        name="Face Category",
        items=[(c, c, "") for c in FACE_CATEGORIES],
        default="Eyes",
    )
    bpy.types.Scene.wardrobe_face_search            = bpy.props.StringProperty(name="Search", default="")
    bpy.types.Scene.wardrobe_selected_face_blend    = bpy.props.StringProperty(default="")
    bpy.types.Scene.wardrobe_selected_face_label    = bpy.props.StringProperty(default="")
    bpy.types.Scene.wardrobe_selected_face_category = bpy.props.StringProperty(default="")
    bpy.types.Scene.wardrobe_bean_active            = bpy.props.BoolProperty(
        name="Bean Emulator Active",
        description="Classic Bean Emulator has been applied",
        default=False,
    )
    bpy.types.Scene.wardrobe_quick_shader = bpy.props.EnumProperty(
        name="Quick Setup Shader",
        items=[("RGBA_AVATAR", "RGBA", ""), ("SOLID_AVATAR", "Solid", "")],
        default="RGBA_AVATAR",
    )
    bpy.types.Scene.wardrobe_quick_mat_path = bpy.props.StringProperty(default="")




def unregister():
    global PREVIEW_COLL, INDEX_CACHE, INDEX_ERROR, INDEX_LOADING
    global FACE_CACHE, FACE_ERROR, FACE_LOADING
    INDEX_CACHE = None; INDEX_ERROR = ""; INDEX_LOADING = False
    FACE_CACHE  = None; FACE_ERROR  = ""; FACE_LOADING  = False
    _reset_previews()
    _unload_custom_icons()
    _unload_rig_ui()
    for cls in reversed(classes):
        try: bpy.utils.unregister_class(cls)
        except: pass
    for a in ["wardrobe_enabled","wardrobe_category","wardrobe_search",
              "wardrobe_selected_blend","wardrobe_selected_label","wardrobe_open_groups",
              "wardrobe_export_body","wardrobe_bake_device","wardrobe_export_optimize",
              "wardrobe_export_exclude_hair",
              "wardrobe_export_selected","wardrobe_export_exclude","wardrobe_export_exclude_names",
              "wardrobe_export_vrchat","wardrobe_export_open",
              "wardrobe_debug_open","wardrobe_browser_open",
              "wardrobe_rig_open","wardrobe_devextras_open",
              "wardrobe_props_open","wardrobe_prop_category","wardrobe_prop_search","wardrobe_selected_prop_blend",
              "wardrobe_selected_prop_label","wardrobe_open_prop_groups",
              "wardrobe_face_open","wardrobe_face_category","wardrobe_face_search",
              "wardrobe_selected_face_blend","wardrobe_selected_face_label",
              "wardrobe_selected_face_category",
              "wardrobe_bean_active",
              "wardrobe_quick_shader","wardrobe_quick_mat_path",
]:
        try: delattr(bpy.types.Scene, a)
        except: pass

if __name__ == "__main__": register()
