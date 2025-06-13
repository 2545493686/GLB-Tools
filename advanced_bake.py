# bake_uv_script.py
# 所有参数在脚本中集中配置，支持GPU烘焙，并在烘焙完成后导出 .blend 文件
import bpy
import mathutils
import math

# === 配置区域 ===
INPUT_GLB = r"F:\AI\datasets\objaverse_result\batch_test_baked\00c2112c133a4b548a3ef3b01b009286_baked.glb"
OUTPUT_IMAGE = r"F:\AI\datasets\objaverse_result\batch_test_output\baked.png"
OUTPUT_BLEND = r"F:\AI\datasets\objaverse_result\batch_test_output\result.blend"
RESOLUTION = 1024       # 纹理分辨率
PADDING = 16            # UV 边缘填充像素
SUN_STRENGTH = 5.0       # 环境光强度，防止烘烤全黑（不再用于实际烘焙光源）
AREA_POWER = 1500.0      # 面积光强度，单位瓦特
AREA_SIZE_X = 0.08       # 面积光 X 维度（米）
AREA_SIZE_Y = 0.06       # 面积光 Y 维度（米）
AREA_COLOR = (1.0, 0.937, 0.882)  # 面积光颜色 (R, G, B)
HDR_IMAGE = r"F:\AI\datasets\objaverse_result\abandoned_church_1k.hdr"  # 新增：指定 HDR 环境贴图路径
OFFSET_RATIO = 1.0      # 相机位置偏移比例

# === 功能函数 ===
def clear_scene():
    bpy.ops.wm.read_homefile(use_empty=True)


def enable_gpu():
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


def import_model(path):
    bpy.ops.import_scene.gltf(filepath=path)
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if not meshes:
        raise RuntimeError(f"No mesh found in {path}")
    return meshes[0]


def compute_bounding_sphere(obj):
    verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    min_co = mathutils.Vector((min(v[i] for v in verts) for i in range(3)))
    max_co = mathutils.Vector((max(v[i] for v in verts) for i in range(3)))
    center = (min_co + max_co) * 0.5
    radius = max((v - center).length for v in verts)
    return center, radius


def setup_camera(center, radius):
    cam_data = bpy.data.cameras.new("BakeCam")
    cam = bpy.data.objects.new("BakeCam", cam_data)
    bpy.context.collection.objects.link(cam)

    # 根据相机 FOV 和包围球半径计算最小距离
    fov = cam_data.angle  # 摄像机水平视角（弧度）
    cam_d = radius / math.sin(fov / 2) * (1 + OFFSET_RATIO)

    # 以 Blender 视口常用的斜上方视角放置相机
    direction = mathutils.Vector((0, -1, 1)).normalized()
    cam.location = center + direction * cam_d

    # 设置相机旋转以对准中心
    direction = center - cam.location
    cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

    # 设置场景的活动摄像机
    bpy.context.scene.camera = cam
    return cam


def add_sun_light(center, radius, strength):
    light_data = bpy.data.lights.new(name="BakeSun", type='SUN')
    light_data.energy = strength
    light = bpy.data.objects.new(name="BakeSun", object_data=light_data)
    bpy.context.collection.objects.link(light)
    light.location = center + mathutils.Vector((0, -radius * 2, radius * 2))
    light.rotation_euler = (center - light.location).to_track_quat('-Z', 'Y').to_euler()


def create_bake_image(resolution):
    return bpy.data.images.new("BakeImage", width=resolution, height=resolution)


def attach_texture_node(obj, img, cam):
    print(obj)
    mat = obj.data.materials[0]
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # 1) Texture image node
    tex_node = nodes.new(type='ShaderNodeTexImage')
    tex_node.image = img
    nodes.active = tex_node

    # 2) Three Value nodes for camera X, Y, Z
    vx = nodes.new(type='ShaderNodeValue'); vx.name = 'CamX'; vx.label = 'CamX'
    vx.outputs[0].default_value = cam.location.x
    vy = nodes.new(type='ShaderNodeValue'); vy.name = 'CamY'; vy.label = 'CamY'
    vy.outputs[0].default_value = cam.location.y
    vz = nodes.new(type='ShaderNodeValue'); vz.name = 'CamZ'; vz.label = 'CamZ'
    vz.outputs[0].default_value = cam.location.z

    # 3) Combine XYZ into camera position vector
    combine = nodes.new(type='ShaderNodeCombineXYZ')
    links.new(vx.outputs[0], combine.inputs['X'])
    links.new(vy.outputs[0], combine.inputs['Y'])
    links.new(vz.outputs[0], combine.inputs['Z'])

    # 4) Geometry node for mesh Position & Normal
    geo = nodes.new(type='ShaderNodeNewGeometry')

    # 5) Compute view vector = camera_pos - world_pos
    subtract = nodes.new(type='ShaderNodeVectorMath'); subtract.operation = 'SUBTRACT'
    links.new(combine.outputs['Vector'], subtract.inputs[0])
    links.new(geo.outputs['Position'], subtract.inputs[1])

    # 6) Normalize the view vector
    norm = nodes.new(type='ShaderNodeVectorMath'); norm.operation = 'NORMALIZE'
    links.new(subtract.outputs[0], norm.inputs[0])

    # 7) Dot product with surface normal
    dot = nodes.new(type='ShaderNodeVectorMath'); dot.operation = 'DOT_PRODUCT'

    links.new(norm.outputs[0], dot.inputs[0])
    links.new(geo.outputs['Normal'], dot.inputs[1])

    # 8) Clamp negatives: Max(dot, 0)
    maxn = nodes.new(type='ShaderNodeMath'); maxn.operation = 'MAXIMUM'
    maxn.inputs[1].default_value = 0.0
    links.new(dot.outputs["Value"], maxn.inputs[0])

    # 9) Greater-than threshold (0)
    gt = nodes.new(type='ShaderNodeMath'); gt.operation = 'GREATER_THAN'
    gt.inputs[1].default_value = 0.0
    links.new(maxn.outputs[0], gt.inputs[0])

    # 10) Mix Shader: Emission(black) vs original BSDF
    mix = nodes.new(type='ShaderNodeMixShader')
    emit = nodes.new(type='ShaderNodeEmission')
    emit.inputs['Color'].default_value = (0.0, 0.0, 0.0, 1.0)
    bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    links.new(emit.outputs['Emission'], mix.inputs[1])
    links.new(bsdf.outputs['BSDF'],   mix.inputs[2])
    links.new(gt.outputs[0],          mix.inputs['Fac'])

    # 11) Hook up to Material Output
    out = next(n for n in nodes if n.type == 'OUTPUT_MATERIAL')
    links.new(mix.outputs['Shader'], out.inputs['Surface'])


def bake_to_image(obj, cam, padding):
    scene = bpy.context.scene
    # Bake 设置：Combined，从Active Camera视图
    scene.render.bake.view_from = 'ACTIVE_CAMERA'
    scene.render.engine = 'CYCLES'
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.bake(type='COMBINED', margin=padding, use_cage=False)


def save_image(img, path):
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()


def save_blend(path):
    bpy.ops.wm.save_mainfile(filepath=path)


def setup_hdr_environment(hdr_path):
    """将指定的 HDR 文件加载为世界环境贴图。"""
    # 确保场景有 World
    scene = bpy.context.scene
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world
    # 启用节点系统
    world.use_nodes = True
    nt = world.node_tree
    nodes = nt.nodes
    links = nt.links
    # 清空已有节点
    nodes.clear()
    # 创建环境贴图节点
    env_tex = nodes.new(type='ShaderNodeTexEnvironment')
    env_tex.image = bpy.data.images.load(hdr_path)
    # 创建背景节点
    bg_node = nodes.new(type='ShaderNodeBackground')
    # 创建输出节点
    output = nodes.new(type='ShaderNodeOutputWorld')
    # 连接：Environment → Background → World Output
    links.new(env_tex.outputs['Color'], bg_node.inputs['Color'])
    links.new(bg_node.outputs['Background'], output.inputs['Surface'])

def add_area_light(scene, camera, power, size_x, size_y, color):
    # 在摄像机位置创建矩形面积光
    light_data = bpy.data.lights.new(name="CameraAreaLight", type='AREA')
    light_data.energy = power
    light_data.shape = 'RECTANGLE'
    light_data.size = size_x
    light_data.size_y = size_y
    light_data.color = color
    light_obj = bpy.data.objects.new(name="CameraAreaLight", object_data=light_data)
    scene.collection.objects.link(light_obj)
    # 同步相机位置与方向
    light_obj.location = camera.location
    light_obj.rotation_euler = camera.rotation_euler
    return light_obj

def create_floor():
    """创建一个地板平面并附加材质"""
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = "BakeFloor"
    mat = bpy.data.materials.new(name="FloorMat")
    mat.use_nodes = False
    # 设置地板颜色为 A4 纸张的白色
    mat.diffuse_color = (0.97, 0.97, 0.97, 1.0)
    floor.data.materials.append(mat)
    return floor

def compute_bounding_box(obj):
    """计算模型的包围盒"""
    verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    min_co = mathutils.Vector((min(v[i] for v in verts) for i in range(3)))
    max_co = mathutils.Vector((max(v[i] for v in verts) for i in range(3)))
    return min_co, max_co

# === 主流程 ===
def main():
    clear_scene()
    enable_gpu()
    # 导入 glb 模型
    obj = import_model(INPUT_GLB)
    obj.rotation_mode = 'XYZ'

    # 创建地板
    floor = create_floor()
    min_co, max_co = compute_bounding_box(obj)
    center_xy = (min_co + max_co) * 0.5
    offset = (max_co.z - min_co.z) * 0.001  # 下移 1% 高度
    floor.location = mathutils.Vector((center_xy.x, center_xy.y, min_co.z - offset))
    size_x = max_co.x - min_co.x
    size_y = max_co.y - min_co.y
    floor.scale = mathutils.Vector((size_x * 3.0, size_y * 3.0, 1.0))
    
    # 预计算包围球
    center, radius = compute_bounding_sphere(obj)
    # 创建并设置 BakeCam，避免 KeyError
    cam = setup_camera(center, radius)
    setup_hdr_environment(HDR_IMAGE)
    # 添加并绑定摄像机面积光
    area_light = add_area_light(bpy.context.scene, cam, AREA_POWER, AREA_SIZE_X, AREA_SIZE_Y, AREA_COLOR)

    # 固定相机在两个预设位置（各方案第一个点），不随旋转改变
    elevations = [math.atan(0.2), math.atan(1.0)]
    base_azim = math.radians(180)  # 初始方位角（背面）
    import random
    angle_noise = math.radians(2)  # ±2° 物体旋转微扰
    shot = 0
    for vid, elev in enumerate(elevations):
        # 计算并设置固定相机位置
        horiz = math.cos(elev)
        direction = mathutils.Vector((
            math.cos(base_azim) * horiz,
            math.sin(base_azim) * horiz,
            math.sin(elev)
        ))
        cam_d = radius / math.sin(cam.data.angle / 2) * (1 + OFFSET_RATIO)
        cam.location = center + direction * cam_d
        cam.rotation_euler = (center - cam.location).to_track_quat('-Z', 'Y').to_euler()
        bpy.context.scene.camera = cam
        # 同步面积光
        area_light.location = cam.location
        area_light.rotation_euler = cam.rotation_euler

        # 在此相机位置上，让物体自转 60° 步长，共拍摄 6 张
        for i in range(6):
            base_angle = math.radians(60 * i)
            delta = random.uniform(-angle_noise, angle_noise)
            obj.rotation_euler.z = base_angle + delta

            # 更新相机位置节点（位置不变，可选执行）
            mat = obj.data.materials[0]
            nodes = mat.node_tree.nodes
            for name, val in [('CamX', cam.location.x), ('CamY', cam.location.y), ('CamZ', cam.location.z)]:
                if name in nodes:
                    nodes[name].outputs[0].default_value = val

            # 烘焙并保存
            img = create_bake_image(RESOLUTION)
            attach_texture_node(obj, img, cam)
            bake_to_image(obj, cam, PADDING)
            out_img = OUTPUT_IMAGE.replace('.png', f'_{vid}_{i}.png')
            out_blend = OUTPUT_BLEND.replace('.blend', f'_{vid}_{i}.blend')
            save_image(img, out_img)
            save_blend(out_blend)
            print(f"[Shot {shot}] CameraIdx: {vid}, ObjRot: {obj.rotation_euler}")
            shot += 1

    print("All shots completed.")


if __name__ == '__main__':
    main()
