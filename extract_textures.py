#!/usr/bin/env python3
# extract_textures_glb.py
#
# 直接基于 GLB 标准解析，提取嵌入的贴图
# 配置区 —— 在这里设置输入 GLB 路径和输出目录
INPUT_GLB   = r"F:\AI\datasets\objaverse_result\xatlas_py\000a883519934f4383b9aeb0d535c545_baked.glb"
OUTPUT_DIR  = r"F:\AI\datasets\objaverse_result\xatlas_py"

import os
import json
import struct
import base64
import sys

def parse_glb(path):
    with open(path, 'rb') as f:
        header = f.read(12)
        magic, version, length = struct.unpack('<4sII', header)
        if magic != b'glTF':
            raise ValueError("Not a valid GLB file")
        json_chunk = None
        bin_chunk = None
        offset = 12
        while offset < length:
            # 读取下一个 chunk 的头部：length (uint32) + type (4 chars)
            chunk_header = f.read(8)
            if len(chunk_header) < 8:
                break
            chunk_length, chunk_type = struct.unpack('<I4s', chunk_header)
            chunk_data = f.read(chunk_length)
            if chunk_type == b'JSON':
                json_chunk = chunk_data
            elif chunk_type.rstrip(b'\x00') == b'BIN':
                bin_chunk = chunk_data
            offset += 8 + chunk_length
        if json_chunk is None:
            raise ValueError("Missing JSON chunk in GLB")
        # binary chunk may be None if all buffers are external
        return json.loads(json_chunk.decode('utf-8')), bin_chunk

def extract_image(image_index, gltf, bin_chunk, out_base):
    img_def = gltf['images'][image_index]
    # 优先 bufferView
    if 'bufferView' in img_def:
        bv = gltf['bufferViews'][img_def['bufferView']]
        byte_offset = bv.get('byteOffset', 0)
        byte_length = bv['byteLength']
        data = bin_chunk[byte_offset:byte_offset + byte_length]
    elif 'uri' in img_def:
        uri = img_def['uri']
        if uri.startswith('data:'):
            # data URI
            header, b64 = uri.split(',', 1)
            data = base64.b64decode(b64)
        else:
            # 外部文件
            ext_path = os.path.join(os.path.dirname(INPUT_GLB), uri)
            with open(ext_path, 'rb') as ef:
                data = ef.read()
    else:
        raise ValueError(f"Image[{image_index}] 没有 bufferView 或 uri")

    # 确定文件扩展名
    mime = img_def.get('mimeType', '')
    if mime:
        ext = mime.split('/')[-1]
        if ext == 'jpeg':
            ext = 'jpg'
    else:
        # 简易魔数检测
        if data.startswith(b'\x89PNG'):
            ext = 'png'
        elif data.startswith(b'\xff\xd8'):
            ext = 'jpg'
        else:
            ext = 'bin'

    out_path = f"{out_base}.{ext}"
    with open(out_path, 'wb') as wf:
        wf.write(data)
    return out_path

def main():
    gltf, bin_chunk = parse_glb(INPUT_GLB)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    base = os.path.splitext(os.path.basename(INPUT_GLB))[0]

    # 假设只有一个材质
    mats = gltf.get('materials', [])
    if not mats:
        print("Warning: 未找到任何 material")
        return
    mat = mats[0]
    pbr = mat.get('pbrMetallicRoughness', {})

    # 提取 Albedo (BaseColor)
    bc_tex = pbr.get('baseColorTexture', {}).get('index')
    if bc_tex is not None:
        img_idx = gltf['textures'][bc_tex]['source']
        out = os.path.join(OUTPUT_DIR, f"{base}_albedo")
        saved = extract_image(img_idx, gltf, bin_chunk, out)
        print(f"Saved Albedo → {saved}")
    else:
        print("Warning: 未找到 BaseColor 贴图")

    # 提取 Normal
    normal_tex = mat.get('normalTexture', {}).get('index')
    if normal_tex is not None:
        img_idx = gltf['textures'][normal_tex]['source']
        out = os.path.join(OUTPUT_DIR, f"{base}_normal")
        saved = extract_image(img_idx, gltf, bin_chunk, out)
        print(f"Saved Normal → {saved}")
    else:
        print("Warning: 未找到 Normal 贴图")

    # 提取 Metallic-Roughness
    mr_tex = pbr.get('metallicRoughnessTexture', {}).get('index')
    if mr_tex is not None:
        img_idx = gltf['textures'][mr_tex]['source']
        out = os.path.join(OUTPUT_DIR, f"{base}_mr")
        saved = extract_image(img_idx, gltf, bin_chunk, out)
        print(f"Saved Metallic-Roughness → {saved}")
    else:
        print("Warning: 未找到 Metallic-Roughness 贴图")

if __name__ == "__main__":
    main()
