#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import logging
from tqdm import tqdm

# ─── 配置 ────────────────────────────────────────────────────────────────
# A 文件夹路径（存放待烘培的 .glb）
INPUT_DIR = r"F:\AI\datasets\objaverse_result\batch_1_filter_glbs"
# B 文件夹路径（输出烘培后的 .glb）
OUTPUT_DIR = r"F:\AI\datasets\objaverse_result\batch_1_filter_glbs_baked"
# Blender 可执行文件
BLENDER_EXE = "blender"
# bake_glb.py 脚本路径（假设与本脚本同目录）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BAKE_SCRIPT = os.path.join(SCRIPT_DIR, "bake_glb.py")
# 日志文件保存到脚本同目录
LOG_FILE = os.path.join(SCRIPT_DIR, "bake_glb.log")
# 断点续传状态文件
STATE_FILE = os.path.join(SCRIPT_DIR, "bake_state.txt")
# ─────────────────────────────────────────────────────────────────────────────

def setup_logging():
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.ERROR,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

def read_start_index():
    """从状态文件读取上次中断的索引，如果不存在则返回 0"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                idx = int(f.read().strip())
            return idx
        except Exception:
            return 0
    return 0

def write_current_index(idx):
    """将当前处理的索引写入状态文件"""
    try:
        with open(STATE_FILE, 'w') as f:
            f.write(str(idx))
    except Exception:
        logging.exception("写入状态文件失败: %s", STATE_FILE)

def bake_file(glb_path):
    """调用 Blender 执行烘培脚本，返回 (success: bool, returncode: int, stderr: str)"""
    name_no_ext = os.path.splitext(os.path.basename(glb_path))[0]
    output_glb = os.path.join(OUTPUT_DIR, f"{name_no_ext}_baked.glb")

    cmd = [
        BLENDER_EXE,
        "--background",
        "--python", BAKE_SCRIPT,
        "--",  # 分隔 Blender 参数和脚本参数
        "--disable_export_debug",
        "--input_file", glb_path,
        "--output_file", output_glb
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode == 0, proc.returncode, proc.stderr

def main():
    setup_logging()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 收集并排序所有 .glb 文件
    files = sorted([f for f in os.listdir(INPUT_DIR) if f.lower().endswith('.glb')])
    total = len(files)

    # 读取上次中断索引
    start_idx = read_start_index()

    # 使用 tqdm 进度条并显示 ETA
    pbar = tqdm(total=total, initial=start_idx, desc="烘焙进度", unit="file")
    for idx, fname in enumerate(files):
        if idx < start_idx:
            continue
        full_input = os.path.join(INPUT_DIR, fname)
        try:
            success, code, stderr = bake_file(full_input)
            if not success:
                logging.error("❌ 失败：%s 退出码=%d\n%s", fname, code, stderr.strip())
        except Exception as e:
            logging.exception("💥 崩溃：%s 异常信息：%s", fname, e)
        finally:
            # 更新状态文件
            write_current_index(idx + 1)
            pbar.update(1)
    pbar.close()

if __name__ == "__main__":
    main()
