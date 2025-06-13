import bpy
import sys
import os
from mathutils import Vector
import argparse

# ─── Configuration ───────────────────────────────────────────────────────────────
# Replace these paths with your actual input/output files:
INPUT_FILE  = r"F:\AI\datasets\objaverse_result\xatlas_py\000a883519934f4383b9aeb0d535c545.glb"
OUTPUT_FILE = r"F:\AI\datasets\objaverse_result\xatlas_py\000a883519934f4383b9aeb0d535c545_baked.glb"
BLEND_SAVE_PATH = OUTPUT_FILE.replace('.glb', '_debug.blend')
BAKE_RESOLUTION = 2048  # e.g. 2048×2048 bake size
BAKE_MARGIN     = 4     # pixels
NEW_UV_NAME     = "BakedUV"
OLD_UV_NAME     = "UVMap"
MRBAKE_IMAGE_NAME = "MetallicRoughnessBake"
BAKE_IMAGE_NAME       = "BakedTexture"
NORMALBAKE_IMAGE_NAME = "NormalBake"
FINAL_MAT_NAME  = "BakedMaterial"
# ────────────────────────────────────────────────────────────────────────────────


# ─── 外部参数覆盖 ────────────────────────────────────────────────────────────────
import argparse

def get_user_args():
    argv = sys.argv
    # 情况一：在 --background … --python 后用 “--” 分隔
    if "--" in argv:
        return argv[argv.index("--")+1:]

user_args = get_user_args()
parser = argparse.ArgumentParser(description="Bake GLB with customizable parameters")
parser.add_argument('--input_file',             default=INPUT_FILE,              help='输入 GLB 文件路径')
parser.add_argument('--output_file',            default=OUTPUT_FILE,             help='输出 GLB 文件路径')
parser.add_argument('--blend_save_path',        default=None,                    help='.blend 保存路径（默认从 OUTPUT_FILE 派生）')
parser.add_argument('--bake_resolution',        type=int,    default=BAKE_RESOLUTION, help='烘焙分辨率')
parser.add_argument('--bake_margin',            type=int,    default=BAKE_MARGIN,      help='烘焙边距（像素）')
parser.add_argument('--new_uv_name',            default=NEW_UV_NAME,             help='新 UV 图层名称')
parser.add_argument('--old_uv_name',            default=OLD_UV_NAME,             help='原始 UV 图层名称')
parser.add_argument('--mr_bake_image_name',     default=MRBAKE_IMAGE_NAME,       help='金属-粗糙度 烘焙图名称')
parser.add_argument('--bake_image_name',        default=BAKE_IMAGE_NAME,         help='BaseColor 烘焙图名称')
parser.add_argument('--normalbake_image_name',  default=NORMALBAKE_IMAGE_NAME,   help='法线 烘焙图名称')
parser.add_argument('--final_mat_name',         default=FINAL_MAT_NAME,          help='最终材质名称')
parser.add_argument('--disable_export_debug', action='store_true', help='Disable final GLB export and .blend save')
args = parser.parse_args(user_args)

# 覆盖默认配置
INPUT_FILE             = args.input_file
OUTPUT_FILE            = args.output_file
BLEND_SAVE_PATH        = args.blend_save_path or OUTPUT_FILE.replace('.glb', '_debug.blend')
BAKE_RESOLUTION        = args.bake_resolution
BAKE_MARGIN            = args.bake_margin
NEW_UV_NAME            = args.new_uv_name
OLD_UV_NAME            = args.old_uv_name
MRBAKE_IMAGE_NAME      = args.mr_bake_image_name
BAKE_IMAGE_NAME        = args.bake_image_name
NORMALBAKE_IMAGE_NAME  = args.normalbake_image_name
FINAL_MAT_NAME         = args.final_mat_name
# ────────────────────────────────────────────────────────────────────────────────

prefs = bpy.context.preferences
cpref = prefs.addons['cycles'].preferences
cpref.compute_device_type = 'CUDA'
for dev in cpref.devices:
    dev.use = True
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'

# 1. Enable CUDA + GPU Compute for Cycles
prefs = bpy.context.preferences
cycles_prefs = prefs.addons['cycles'].preferences

# 1. 切换到 CUDA
cycles_prefs.compute_device_type = 'CUDA'

# 2. 刷新设备列表（Blender 3.x 以后推荐用 refresh_devices 而不是 get_devices）:contentReference[oaicite:0]{index=0}
cycles_prefs.refresh_devices()

# 3. 勾选所有 CUDA 设备:contentReference[oaicite:1]{index=1}
for dev in cycles_prefs.devices:
    dev.use = True

# 4. 把场景渲染设备设为 GPU
bpy.context.scene.cycles.device = 'GPU'

# 2. Clear existing objects
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# 3. Import GLB
bpy.ops.import_scene.gltf(filepath=INPUT_FILE)

# 4. Gather mesh objects
meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
if not meshes:
    print("Error: no mesh objects found in imported file.")
    sys.exit(1)

# 5. Keep only the first UV layer on each mesh (create one if missing)
for obj in meshes:
    uv_layers = obj.data.uv_layers
    # Add a UV layer if none exist
    if len(uv_layers) == 0:
        uv_layers.new(name=OLD_UV_NAME)
    elif len(uv_layers) > 1:
        # Remove extra UV layers by index in reverse order (no errors)
        for idx in range(len(uv_layers) - 1, 0, -1):
            uv_layers.remove(uv_layers[idx])
    # Rename the remaining (first) UV layer
    uv_layers[0].name = OLD_UV_NAME

# 6. Rename all original UV to a common name
for obj in meshes:
    obj.data.uv_layers[0].name = OLD_UV_NAME

# Ensure each mesh has a vertex color layer named "Col" so join preserves per-vertex colors
for obj in meshes:
    if hasattr(obj.data, "color_attributes"):
        # Remove extra layers, keep one
        for layer in list(obj.data.color_attributes)[1:]:
            obj.data.color_attributes.remove(layer)
        # Rename or create
        if obj.data.color_attributes:
            obj.data.color_attributes[0].name = "Col"
        else:
            layer = obj.data.color_attributes.new(name="Col", type='FLOAT_COLOR', domain='CORNER')
            for poly in obj.data.polygons:
                for li in poly.loop_indices:
                    layer.data[li].color = (1.0, 1.0, 1.0, 1.0)
    else:
        # Fallback for older versions
        vcols = obj.data.vertex_colors
        for layer in list(vcols)[1:]:
            obj.data.vertex_colors.remove(layer)
        if vcols:
            vcols[0].name = "Col"
        else:
            layer = obj.data.vertex_colors.new(name="Col")
            for poly in obj.data.polygons:
                for li in poly.loop_indices:
                    layer.data[li].color = (1.0, 1.0, 1.0, 1.0)


# 7. Join all meshes into one
bpy.ops.object.select_all(action='DESELECT')
for obj in meshes:
    obj.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.join()

# 8. 新建 UVMap，并切到它（bake 用的是 active_index）
merged = bpy.context.view_layer.objects.active
merged.data.uv_layers.new(name=NEW_UV_NAME)
idx = merged.data.uv_layers.find(NEW_UV_NAME)
merged.data.uv_layers.active_index = idx
print(f"[Debug] Active UV layer for bake: {merged.data.uv_layers.active.name}")

# After joining meshes
if "Col" not in merged.data.color_attributes:
    merged.data.color_attributes.new(name="Col", type='FLOAT_COLOR', domain='CORNER')
col_layer = merged.data.color_attributes["Col"]
for poly in merged.data.polygons:
    for li in poly.loop_indices:
        col_layer.data[li].color = (1.0, 1.0, 1.0, 1.0)

# 9. 进入 Edit 模式，选中所有面 → 智能展开 → 两次打包岛屿
bpy.ops.object.mode_set(mode='EDIT')

# 9.1 全选所有面
bpy.ops.mesh.select_all(action='SELECT')

# 9.2 智能展开（angle_limit 和 island_margin 用默认值 66°, 0.02）
bpy.ops.uv.smart_project()
print(f"[Debug] smart_project used angle_limit=66°, island_margin=0.02")

# 9.3 Pack 第一次（确保 UV 全选）
bpy.ops.uv.select_all(action='SELECT')
bpy.ops.uv.pack_islands(margin=0)
print(f"[Debug] pack_islands #1 margin=0")

# 9.4 Pack 第二次（同样先全选 UV）
bpy.ops.uv.select_all(action='SELECT')
bpy.ops.uv.pack_islands(margin=0)
print(f"[Debug] pack_islands #2 margin=0")

# 9.5 回 Object 模式
bpy.ops.object.mode_set(mode='OBJECT')

# --- 法线贴图烘焙阶段 ---
# 10. 创建法线烘焙目标图
normal_img = bpy.data.images.new(NORMALBAKE_IMAGE_NAME,
                                 width=BAKE_RESOLUTION,
                                 height=BAKE_RESOLUTION)
normal_img.colorspace_settings.name = 'Non-Color'

# 在每个材质中添加并选中法线烘焙目标
for mat in bpy.data.materials:
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    tex_node = nodes.new(type='ShaderNodeTexImage')
    tex_node.image = normal_img
    tex_node.location = (0, -400)
    tex_node.select = True
    mat.node_tree.nodes.active = tex_node

# 设置烘焙为法线（Tangent 空间）并执行
scene.cycles.bake_type = 'NORMAL'
scene.cycles.bake_normal_space = 'TANGENT'
scene.render.bake.margin = BAKE_MARGIN
bpy.ops.object.bake(type='NORMAL')

# 烘焙完成后，恢复到 Emission 烘焙
scene.cycles.bake_type = 'EMIT'

# 10. Create a single bake target image
bake_img = bpy.data.images.new(BAKE_IMAGE_NAME,
                               width=BAKE_RESOLUTION,
                               height=BAKE_RESOLUTION)

# 11. In each material, swap Principled BSDF → Emission, add the bake image node
for mat in bpy.data.materials:
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # find nodes
    output_node = next(n for n in nodes if n.type == 'OUTPUT_MATERIAL')
    bsdf_node   = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')

    # add Emission node
    emis_node = nodes.new(type='ShaderNodeEmission')
    emis_node.location = bsdf_node.location + Vector((-200, 0))
    emis_node.inputs['Strength'].default_value = 1.0

    # reconnect Base Color → Emission.Color
    if bsdf_node.inputs['Base Color'].links:
        src = bsdf_node.inputs['Base Color'].links[0].from_socket
        links.new(src, emis_node.inputs['Color'])
    else:
        emis_node.inputs['Color'].default_value = bsdf_node.inputs['Base Color'].default_value

    # disconnect original BSDF → Output
    for link in list(bsdf_node.outputs['BSDF'].links):
        links.remove(link)
    # connect Emission → Output
    links.new(emis_node.outputs['Emission'], output_node.inputs['Surface'])

    # add Image Texture node (bake target), select it
    tex_node = nodes.new(type='ShaderNodeTexImage')
    tex_node.image = bake_img
    tex_node.location = emis_node.location + Vector((0, -200))
    tex_node.select = True
    mat.node_tree.nodes.active = tex_node

# 12. Setup Bake settings and bake
scene.cycles.bake_type = 'EMIT'
scene.render.bake.margin = BAKE_MARGIN
bpy.ops.object.bake(type='EMIT')

# --- Metallic-Roughness Bake ---
mr_img = bpy.data.images.new(MRBAKE_IMAGE_NAME,
                             width=BAKE_RESOLUTION,
                             height=BAKE_RESOLUTION)
mr_img.colorspace_settings.name = 'Non-Color'

for mat in bpy.data.materials:
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    out_node = next(n for n in nodes if n.type == 'OUTPUT_MATERIAL')
    bsdf_node = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')

    # combine Metallic & Roughness into channels: B = Metallic, G = Roughness
    combine = nodes.new(type='ShaderNodeCombineRGB')
    combine.location = bsdf_node.location + Vector((-200, 0))
    # metallic → B
    if bsdf_node.inputs['Metallic'].links:
        src_m = bsdf_node.inputs['Metallic'].links[0].from_socket
        links.new(src_m, combine.inputs['B'])
    else:
        combine.inputs['B'].default_value = bsdf_node.inputs['Metallic'].default_value
    # roughness → G
    if bsdf_node.inputs['Roughness'].links:
        src_r = bsdf_node.inputs['Roughness'].links[0].from_socket
        links.new(src_r, combine.inputs['G'])
    else:
        combine.inputs['G'].default_value = bsdf_node.inputs['Roughness'].default_value
    # output combined color as source
    src = combine.outputs['Image']

    # hook up to emission
    emis = nodes.new(type='ShaderNodeEmission')
    emis.location = bsdf_node.location + Vector((-200, 0))
    emis.inputs['Strength'].default_value = 1.0
    links.new(src, emis.inputs['Color'])
    # disconnect original BSDF output
    for link in list(bsdf_node.outputs['BSDF'].links):
        links.remove(link)
    links.new(emis.outputs['Emission'], out_node.inputs['Surface'])
    # assign bake target image
    tex = nodes.new(type='ShaderNodeTexImage')
    tex.image = mr_img
    tex.location = emis.location + Vector((0, -200))
    tex.select = True
    mat.node_tree.nodes.active = tex

# set bake to emit and run metallic-roughness bake
scene.cycles.bake_type = 'EMIT'
scene.render.bake.margin = BAKE_MARGIN
bpy.ops.object.bake(type='EMIT')

# 13. Create final single material with Principled BSDF + baked texture
final_mat = bpy.data.materials.new(FINAL_MAT_NAME)
final_mat.use_nodes = True
nodes = final_mat.node_tree.nodes
links = final_mat.node_tree.links
nodes.clear()

# output & BSDF
out_node = nodes.new(type='ShaderNodeOutputMaterial')
out_node.location = (400, 0)
bsdf_node = nodes.new(type='ShaderNodeBsdfPrincipled')
bsdf_node.location = (0, 0)
links.new(bsdf_node.outputs['BSDF'], out_node.inputs['Surface'])

# UV Map node
uv_node = nodes.new(type='ShaderNodeUVMap')
uv_node.location = (-600, 0)
uv_node.uv_map = NEW_UV_NAME

# Base Color Texture
color_tex = nodes.new(type='ShaderNodeTexImage')
color_tex.image = bake_img
color_tex.location = (-600, 200)
links.new(uv_node.outputs['UV'], color_tex.inputs['Vector'])
links.new(color_tex.outputs['Color'], bsdf_node.inputs['Base Color'])

# Metallic-Roughness Texture (glTF exporter requires a single image node)
mr_tex = nodes.new(type='ShaderNodeTexImage')
mr_tex.name  = "MetallicRoughness"
mr_tex.label = "Metallic Roughness"
mr_tex.image = mr_img
mr_tex.location = (-600, -100)

links.new(uv_node.outputs['UV'], mr_tex.inputs['Vector'])

# Separate metallic-roughness channels
sep_node = nodes.new(type='ShaderNodeSeparateRGB')
sep_node.location = mr_tex.location + Vector((200, 0))
# Feed the combined MR texture into the Separate RGB node
links.new(mr_tex.outputs['Color'], sep_node.inputs['Image'])
# Connect G channel to Metallic, B channel to Roughness
links.new(sep_node.outputs['G'], bsdf_node.inputs['Metallic'])
links.new(sep_node.outputs['B'], bsdf_node.inputs['Roughness'])

# --- 在最终材质中接入法线贴图 ---
normal_tex = nodes.new(type='ShaderNodeTexImage')
normal_tex.image = normal_img
normal_tex.location = (-600, -300)
links.new(uv_node.outputs['UV'], normal_tex.inputs['Vector'])

normal_map_node = nodes.new(type='ShaderNodeNormalMap')
normal_map_node.location = (-400, -300)
links.new(normal_tex.outputs['Color'], normal_map_node.inputs['Color'])
links.new(normal_map_node.outputs['Normal'], bsdf_node.inputs['Normal'])

# Assign material to merged mesh
merged.data.materials.clear()
merged.data.materials.append(final_mat)

# Re-assign in Edit mode for proper slot assignment
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.object.material_slot_assign()
bpy.ops.object.mode_set(mode='OBJECT')

# Clean up old materials
for m in [m for m in bpy.data.materials if m.name != FINAL_MAT_NAME]:
    bpy.data.materials.remove(m, do_unlink=True)

# -- Remove all UV layers except the newly created one --
uv_layers = merged.data.uv_layers
for idx in range(len(uv_layers) - 1, -1, -1):
    if uv_layers[idx].name != NEW_UV_NAME:
        uv_layers.remove(uv_layers[idx])

# Export the final GLB
bpy.ops.export_scene.gltf(
    filepath=OUTPUT_FILE,
    export_format='GLB',
    export_materials='EXPORT',
    ui_tab='GENERAL',
    export_image_format='AUTO',
    export_keep_originals=False,
    export_texcoords=True,
    export_normals=True
)

# Save Blender project for inspection
if not args.disable_export_debug:
    bpy.ops.wm.save_mainfile(filepath=BLEND_SAVE_PATH)
    print(f"Saved Blender project to: {BLEND_SAVE_PATH}")

print("Done! Exported to:", OUTPUT_FILE)
