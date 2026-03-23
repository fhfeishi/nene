# app/components/utils_model.py

import os 
import dotenv

dotenv.load_dotenv()


# ---------------  cached model load  ---------------
def get_modelscope_path(model_name: str) -> str:
    """modelscope 路径直接拼接即可，如 'Qwen/Qwen3.5-2B'"""
    return os.path.normpath(os.path.join(os.getenv("MODELSCOPE_ROOT"), model_name))

def get_huggingface_path(model_name: str) -> str:
    """
    hf 缓存路径需要找到 snapshots 下最新的那个 hash 目录
    model_name 格式: 'Qwen/Qwen3.5-2B'  →  目录名: 'models--Qwen--Qwen3.5-2B'
    """
    dir_name = "models--" + model_name.replace("/", "--")
    snapshots_dir = os.path.join(os.getenv("HUGGINGFACE_ROOT"), dir_name, "snapshots")
    
    # 取 snapshots 下第一个（通常只有一个）hash 目录
    hashes = os.listdir(snapshots_dir)
    if not hashes:
        raise FileNotFoundError(f"No snapshots found in {snapshots_dir}")
    
    return os.path.normpath(os.path.join(snapshots_dir, hashes[0]))


# -------------- local model load  ---------------  















