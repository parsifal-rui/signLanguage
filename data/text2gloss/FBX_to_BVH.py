# -*- coding: utf-8 -*-
# Run with Blender: blender --background --python data/text2gloss/FBX_to_BVH.py
# Reads mapping.json (gloss -> fbx filename), imports each FBX, exports BVH to same dir.

import bpy
import json
import os

script_dir = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))
mapping_path = os.path.join(script_dir, "mapping.json")

with open(mapping_path, "r", encoding="utf-8") as f:
    mapping = json.load(f)

for gloss, fbx_name in mapping.items():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    fbx_path = os.path.join(script_dir, fbx_name)
    if not os.path.isfile(fbx_path):
        print("Skip (not found):", fbx_path)
        continue

    bpy.ops.import_scene.fbx(filepath=fbx_path)
    armature = next((o for o in bpy.context.scene.objects if o.type == "ARMATURE"), None)
    if not armature:
        print("No armature in", fbx_path)
        continue

    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature

    frame_start = int(bpy.context.scene.frame_start)
    frame_end = int(bpy.context.scene.frame_end)
    if armature.animation_data and armature.animation_data.action:
        frame_start = int(armature.animation_data.action.frame_range[0])
        frame_end = int(armature.animation_data.action.frame_range[1])

    out_name = os.path.splitext(fbx_name)[0] + ".bvh"
    out_path = os.path.join(script_dir, out_name)
    bpy.ops.export_anim.bvh(
        filepath=out_path,
        frame_start=frame_start,
        frame_end=frame_end,
        global_scale=1.0,
    )
    print("Exported:", out_path)

print("Done.")
