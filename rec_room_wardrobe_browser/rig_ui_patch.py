"""
Patched Avatar_RigUI.py - registers once, works on any selected armature.
Injected by the Wardrobe Browser addon at rig append time.
"""
import bpy
from collections import defaultdict


def find_layer_collection(layer_col, name):
    if layer_col.name == name:
        return layer_col
    for child in layer_col.children:
        result = find_layer_collection(child, name)
        if result:
            return result
    return None


class RIG_UI_OT_toggle_collection_visibility(bpy.types.Operator):
    bl_idname = "rig_ui.toggle_collection_visibility"
    bl_label = "Toggle Collection Visibility"
    bl_description = "Toggle both viewport and render visibility of a scene collection"
    bl_options = {"REGISTER", "UNDO"}
    collection_name: bpy.props.StringProperty()

    def execute(self, context):
        col = bpy.data.collections.get(self.collection_name)
        if col is None:
            self.report({"WARNING"}, f"Collection '{self.collection_name}' not found")
            return {"CANCELLED"}
        layer_col = find_layer_collection(context.view_layer.layer_collection, self.collection_name)
        if layer_col is None:
            self.report({"WARNING"}, f"Layer collection '{self.collection_name}' not found")
            return {"CANCELLED"}
        new_hidden = not layer_col.hide_viewport
        layer_col.hide_viewport = new_hidden
        col.hide_render = new_hidden
        return {"FINISHED"}


class RIG_UI_OT_armature_configure(bpy.types.Operator):
    bl_idname = "rig_ui.armature_configure"
    bl_label = ""
    bl_description = "Options for the current armature"

    def execute(self, context): return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        obj = context.active_object
        if not obj or obj.type != "ARMATURE":
            self.layout.label(text="Select the armature to configure.", icon="INFO")
            return
        draw_bc_armature_config(context, self.layout, obj.data)


def draw_bc_armature_config(context, layout, armature_data):
    props = armature_data.rig_ui_props
    layout.box().label(text=f"Configure {context.active_object.name}")
    operator_exists = "RIG_UI_OT_bone_collection_action" in dir(bpy.types)
    if operator_exists:
        col = layout.column()
        col.label(text="Bone Collection Buttons")
        col.prop(props, "bc_button_types", text="Button Type")
    layout.separator()
    ui_col = layout.column()
    ui_col.label(text="UI Settings")
    ui_col.prop(props, "ui_button_horizontal_separation", text="Horizontal Separation", slider=True)
    ui_col.prop(props, "ui_button_vertical_separation",   text="Vertical Separation",   slider=True)
    ui_col.prop(props, "ui_groups_vertical_separation",   text="Groups Vertical Sep.",  slider=True)


class RIG_UI_PT_Universal(bpy.types.Panel):
    """Rec Room Rig UI — works on whichever armature is active"""
    bl_label       = ""
    bl_idname      = "RIG_UI_PT_Universal"
    bl_space_type  = "VIEW_3D"
    bl_region_type = "UI"
    bl_category    = "RR Archive"
    bl_order       = 1

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None
                and obj.type == "ARMATURE"
                and hasattr(obj.data, "rig_ui_props"))

    def draw_header(self, context):
        self.layout.label(text="Rec Room Rig UI")
        row = self.layout.row(align=True)
        row.active = False
        row.operator("rig_ui.armature_configure", text="", icon="PREFERENCES", emboss=False)

    def draw(self, context):
        layout   = self.layout
        # Always use context.active_object — never cache armature reference
        armature = context.active_object
        if not armature or armature.type != "ARMATURE" or not hasattr(armature.data, "rig_ui_props"):
            layout.label(text="Select a Rec Room rig armature", icon="INFO"); return

        # Force a label showing which rig is active so we can verify it's correct
        layout.label(text=armature.name, icon="ARMATURE_DATA")

        props           = armature.data.rig_ui_props
        grp_v_sep       = props.ui_groups_vertical_separation   * 3
        btn_h_sep       = props.ui_button_horizontal_separation * 3
        btn_v_sep       = props.ui_button_vertical_separation   * 1.5
        operator_exists = "RIG_UI_OT_bone_collection_action" in dir(bpy.types)
        is_pose         = armature.mode == "POSE"
        active_pb       = context.active_pose_bone
        selected_pb     = context.selected_pose_bones
        is_v41          = bpy.app.version >= (4, 1, 0)

        self.draw_bone_collections(layout, armature, grp_v_sep, btn_h_sep, btn_v_sep,
                                   operator_exists, is_pose, active_pb, selected_pb, is_v41)
        self.draw_body_toggle(layout, context)

        cp_container = layout.box()
        cp_sub       = cp_container.column(align=True)
        group_order  = {g.unique_id: i for i, g in enumerate(armature.data.custom_properties_ui_groups)}
        grouped_props = defaultdict(lambda: defaultdict(list))
        for prop in armature.data.custom_properties:
            if prop.cp_pin_state:
                grouped_props[prop.group_id][prop.cp_row_int].append((prop.cp_priority_int, prop))

        for gid in sorted(grouped_props.keys(), key=lambda x: group_order.get(x, -1)):
            grp = self.get_group_by_id(armature, gid, "custom_properties_ui_groups")
            if grp:
                if group_order.get(gid, -1) > 1:
                    cp_sub.separator(factor=grp_v_sep)
                self.draw_group(cp_sub, grp, grouped_props[gid], armature, self.draw_custom_property)

    @staticmethod
    def draw_body_toggle(layout, context):
        """FullBody / BeanBody visibility toggles — searches all nested collections."""
        COLLECTIONS = ["FullBody", "BeanBody"]
        box = layout.box()
        row = box.row(align=True)
        for col_name in COLLECTIONS:
            lc      = find_layer_collection(context.view_layer.layer_collection, col_name)
            visible = lc is not None and not lc.hide_viewport
            op      = row.operator("rig_ui.toggle_collection_visibility",
                                   text=col_name,
                                   icon="HIDE_OFF" if visible else "HIDE_ON",
                                   depress=visible)
            op.collection_name = col_name

    def draw_bone_collections(self, layout, armature, grp_v_sep, btn_h_sep, btn_v_sep,
                               operator_exists, is_pose, active_pb, selected_pb, is_v41):
        bc_container = layout.box()
        bc_sub       = bc_container.column(align=True)
        colls_all    = getattr(armature.data, "collections_all", armature.data.collections)
        group_idx_map = {g.unique_id: i for i, g in enumerate(
            getattr(armature.data, "bone_collections_ui_groups", []))}
        grouped = defaultdict(lambda: defaultdict(list))
        for col in colls_all.values():
            if col.get("rig_ui_pin", False):
                gid = col.get("group_id")
                if gid in group_idx_map:
                    grouped[group_idx_map[gid]][col.get("rig_ui_row", 0)].append(col)

        groups_dict = {g.unique_id: g for g in getattr(armature.data, "bone_collections_ui_groups", [])}
        for gi in sorted(grouped.keys()):
            if gi > 1: bc_sub.separator(factor=grp_v_sep)
            uid   = next((k for k, v in group_idx_map.items() if v == gi), None)
            grp   = groups_dict.get(uid)
            if grp:
                gb = bc_sub.column()
                self.draw_group_header_main_ui(gb, grp)
                if grp.toggle:
                    inner = gb.column(align=True)
                    for ri in sorted(grouped[gi].keys()):
                        inner.separator(factor=btn_v_sep)
                        rl = inner.row(align=True)
                        for col in sorted(grouped[gi][ri], key=lambda x: (x.get("rig_ui_priority", 0), x.name)):
                            if col["rig_ui_priority"] > 1: rl.separator(factor=btn_h_sep)
                            self.draw_collection(armature, rl, col, operator_exists,
                                                 is_pose, active_pb, selected_pb, is_v41, btn_h_sep)
                    inner.separator(factor=btn_v_sep)

        ungrouped = [c for c in colls_all.values()
                     if c.get("rig_ui_pin") and c.get("group_id") not in group_idx_map]
        if ungrouped:
            bc_sub.label(text="Ungrouped Pinned Bone Collections")
            ub = bc_sub.box().column(align=True)
            by_row = defaultdict(list)
            for c in ungrouped: by_row[c.get("rig_ui_row", 0)].append(c)
            for ri, cols in sorted(by_row.items()):
                rl = ub.row(align=True)
                for c in cols:
                    if c["rig_ui_priority"] > 1: rl.separator(factor=btn_h_sep)
                    self.draw_collection(armature, rl, c, operator_exists,
                                         is_pose, active_pb, selected_pb, is_v41, btn_h_sep)

    def draw_group_header_main_ui(self, layout, group_item):
        arm  = group_item.id_data
        dt   = group_item.display_type
        lbl  = (group_item.name
                if arm.rig_ui_props.group_headers_customProperties or not group_item.toggle
                else " ")
        icon = ("TRIA_DOWN" if group_item.toggle else "TRIA_RIGHT") if dt == "HEADER_BOX" \
               else ("DOWNARROW_HLT" if group_item.toggle else "RIGHTARROW")
        col  = layout.column()
        box  = col.box() if dt == "HEADER_BOX" else col
        if dt in ("HEADER", "HEADER_BOX"):
            box.prop(group_item, "toggle", text=lbl, emboss=False, icon=icon)
        elif dt in ("LABEL", "LABEL_BOX", "BOX"):
            box.label(text=lbl)
        box.scale_y = 0.5 if dt == "HEADER_BOX" else 0.8

    def draw_group(self, layout, grp, grouped_props, armature, draw_func):
        dt = grp.display_type
        if dt in ("HEADER", "HEADER_BOX"):
            self.draw_group_header_main_ui(layout, grp)
            if grp.toggle:
                self.draw_properties_group(layout.box(), grp, grouped_props, armature, draw_func)
        elif dt in ("LABEL", "LABEL_BOX", "BOX"):
            self.draw_group_with_label(layout, grp, grouped_props, armature, draw_func)
        elif dt == "NONE":
            self.draw_properties_group(layout, grp, grouped_props, armature, draw_func)

    def draw_properties_group(self, layout, grp, grouped_props, armature, draw_func):
        props = armature.data.rig_ui_props
        vs    = props.ui_button_vertical_separation
        hs    = props.ui_button_horizontal_separation
        col   = layout.column(align=True)
        for rn in sorted(grouped_props.keys()):
            col.separator(factor=vs)
            rl = col.row(align=True)
            for item in sorted(grouped_props[rn],
                               key=lambda x: (x[0], x[1].cp_priority_int,
                                              x[1].cp_bone_name.lower(), x[1].cp_prop_name.lower())):
                draw_func(armature, rl, item[1], hs)
            col.separator(factor=vs)

    def draw_group_with_label(self, layout, grp, grouped_props, armature, draw_func):
        arm  = armature.data
        cont = layout.box() if grp.display_type in ("LABEL_BOX", "BOX") else layout
        if arm.rig_ui_props.group_headers_customProperties and grp.display_type in ("LABEL", "LABEL_BOX"):
            cont.row().label(text=grp.name)
        self.draw_properties_group(cont, grp, grouped_props, armature, draw_func)

    def get_group_by_id(self, armature, gid, list_name):
        for g in getattr(armature.data, list_name):
            if g.unique_id == gid: return g
        return None

    @staticmethod
    def draw_custom_property(armature, layout, prop_item, hs=0.2):
        bone = armature.pose.bones.get(prop_item.cp_bone_name)
        if not bone or prop_item.cp_prop_name not in bone.keys(): return
        val   = bone[prop_item.cp_prop_name]
        name  = prop_item.cp_prop_custom_name or prop_item.cp_prop_name
        row   = layout.row(align=False)
        btnr  = row.row(align=True)
        btnr.scale_x = prop_item.button_factor
        if prop_item.get("cp_priority_int", 0) > 1: btnr.separator(factor=hs * 3)
        if type(val) == bool:
            if prop_item.cp_name_inside:
                btnr.prop(bone, f'["{prop_item.cp_prop_name}"]', text=name, toggle=True)
            else:
                btnr.label(text=name)
                btnr.prop(bone, f'["{prop_item.cp_prop_name}"]', text="",
                          icon="CHECKBOX_HLT" if val else "CHECKBOX_DEHLT")
        elif type(val) in (int, float):
            sl = type(val) == float
            if prop_item.cp_name_inside:
                btnr.prop(bone, f'["{prop_item.cp_prop_name}"]', text=name, slider=sl)
            else:
                btnr.label(text=name)
                btnr.prop(bone, f'["{prop_item.cp_prop_name}"]', text="", slider=sl)

    @staticmethod
    def draw_collection(armature, layout, collection, operator_exists, is_pose,
                        active_pb, selected_pb, is_v41, hs=0.2):
        props    = armature.data.rig_ui_props
        colls_all = getattr(armature.data, "collections_all", armature.data.collections)
        in_col   = (is_pose and active_pb and selected_pb
                    and active_pb in selected_pb and active_pb.name in collection.bones)
        visible  = collection.is_visible
        is_solo  = collection.is_solo if is_v41 else False
        solo_on  = any(c.is_solo for c in colls_all.values()) if is_v41 else False
        btn      = layout.row(align=False)
        btn.active = is_solo if solo_on else visible
        if collection.get("display_name", False): btn.scale_x = collection["button_factor"]
        icon = ("SOLO_ON" if is_solo
                else ("NONE" if collection.get("icon_name", "BLANK1") == "BLANK1"
                      else collection.get("icon_name")))
        text = collection.name if collection.get("display_name", False) else ""
        if props.bc_button_types == "SPECIAL" and operator_exists:
            op = btn.operator("rig_ui.bone_collection_action", text=text, icon=icon,
                              emboss=True, depress=(in_col or is_solo))
            op.collection_name = collection.name
        else:
            btn.prop(collection, "is_visible", text=text, icon=icon, toggle=True)


class RIG_UI_PG_groups_ListItem_export(bpy.types.PropertyGroup):
    unique_id:    bpy.props.StringProperty(default="",        override={"LIBRARY_OVERRIDABLE"})
    name:         bpy.props.StringProperty(default="Unnamed", override={"LIBRARY_OVERRIDABLE"})
    toggle:       bpy.props.BoolProperty(default=True,        override={"LIBRARY_OVERRIDABLE"})
    display_type: bpy.props.EnumProperty(
        items=[("BOX","Box",""),("LABEL","Label",""),("LABEL_BOX","Box with Label",""),
               ("HEADER","Toggleable header",""),("HEADER_BOX","Toggleable header Box",""),
               ("NONE","No style","")],
        default="BOX", override={"LIBRARY_OVERRIDABLE"})


class RIG_UI_PG_CustomProperties_Item(bpy.types.PropertyGroup):
    is_moving:           bpy.props.BoolProperty(default=False)
    active_section:      bpy.props.StringProperty(default="")
    cp_pin_state:        bpy.props.BoolProperty(name="Pin", default=False)
    icon_name:           bpy.props.StringProperty(name="Icon", default="BLANK1")
    cp_bone_name:        bpy.props.StringProperty(name="Bone Name")
    cp_prop_name:        bpy.props.StringProperty(name="Property Name")
    cp_prop_custom_name: bpy.props.StringProperty(name="Custom Name", default="")
    cp_name_inside:      bpy.props.BoolProperty(name="Name Inside", default=True)
    button_factor:       bpy.props.FloatProperty(name="Button Factor", default=1, min=1, max=4)
    group_id:            bpy.props.StringProperty(name="Group ID")
    cp_group_int:        bpy.props.IntProperty(name="Group",    default=0)
    cp_row_int:          bpy.props.IntProperty(name="Row",      default=1)
    cp_priority_int:     bpy.props.IntProperty(name="Priority", default=1)


class RIG_UI_PG_ArmatureProperties(bpy.types.PropertyGroup):
    group_headers_customProperties: bpy.props.BoolProperty(default=True, override={"LIBRARY_OVERRIDABLE"})
    bc_button_types: bpy.props.EnumProperty(
        items=[("SPECIAL","Pro buttons",""),("TOGGLE","Basic buttons","")],
        default="SPECIAL", override={"LIBRARY_OVERRIDABLE"})
    ui_sections_vertical_separation: bpy.props.FloatProperty(default=0.0, min=0.0, max=1.0)
    ui_groups_vertical_separation:   bpy.props.FloatProperty(default=0.0, min=0.0, max=1.0)
    ui_button_vertical_separation:   bpy.props.FloatProperty(default=0.0, min=0.0, max=1.0)
    ui_button_horizontal_separation: bpy.props.FloatProperty(default=0.0, min=0.0, max=1.0)
    ui_section_boxes:    bpy.props.BoolProperty(default=True)
    ui_section_headers:  bpy.props.BoolProperty(default=True)


_RIG_UI_CLASSES = (
    RIG_UI_OT_toggle_collection_visibility,
    RIG_UI_OT_armature_configure,
    RIG_UI_PG_groups_ListItem_export,
    RIG_UI_PG_CustomProperties_Item,
    RIG_UI_PG_ArmatureProperties,
    RIG_UI_PT_Universal,
)

def register_rig_ui():
    """Register rig UI classes — safe to call multiple times (skips if already registered)."""
    for cls in _RIG_UI_CLASSES:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            pass  # already registered — fine

    if not hasattr(bpy.types.Armature, "bone_collections_ui_groups"):
        bpy.types.Armature.bone_collections_ui_groups = bpy.props.CollectionProperty(
            type=RIG_UI_PG_groups_ListItem_export)
    if not hasattr(bpy.types.Armature, "visibility_bookmarks_ui_groups"):
        bpy.types.Armature.visibility_bookmarks_ui_groups = bpy.props.CollectionProperty(
            type=RIG_UI_PG_groups_ListItem_export)
    if not hasattr(bpy.types.Armature, "custom_properties_ui_groups"):
        bpy.types.Armature.custom_properties_ui_groups = bpy.props.CollectionProperty(
            type=RIG_UI_PG_groups_ListItem_export)
    if not hasattr(bpy.types.Armature, "custom_properties"):
        bpy.types.Armature.custom_properties = bpy.props.CollectionProperty(
            type=RIG_UI_PG_CustomProperties_Item)
    if not hasattr(bpy.types.Armature, "rig_ui_props"):
        bpy.types.Armature.rig_ui_props = bpy.props.PointerProperty(type=RIG_UI_PG_ArmatureProperties)

def unregister_rig_ui():
    for attr in ["bone_collections_ui_groups","visibility_bookmarks_ui_groups",
                 "custom_properties_ui_groups","custom_properties","rig_ui_props"]:
        try: delattr(bpy.types.Armature, attr)
        except: pass
    for cls in reversed(_RIG_UI_CLASSES):
        try: bpy.utils.unregister_class(cls)
        except: pass

# Keep __main__ compat so the original exec() path still works
if __name__ == "__main__":
    register_rig_ui()
