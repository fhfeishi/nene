# app/components/utils_model_load.py

import os 
import dotenv
from typing import Literal
import logging

dotenv.load_dotenv()
logger = logging.getLogger(__name__)

# ---------------  huggingface/modelscope model path  ---------------

def get_modelscope_path(model_name: str, mode: Literal["local", "cached"] = "cached") -> str:
    """modelscope 路径直接拼接即可，如 'Qwen/Qwen3.5-2B'"""
    if mode == "cached":
        model_path = os.path.normpath(os.path.join(os.getenv("MODELSCOPE_CACHED_ROOT"), model_name))
        if not os.path.exists(model_path):
            logger.error(f"Model path {model_path} not found")   
            raise FileNotFoundError(f"Model path {model_path} not found")
        return model_path
    elif mode == "local":
        model_path = os.path.normpath(os.path.join(os.getenv("MODELSCOPE_LOCAL_ROOT"), model_name))
        if not os.path.exists(model_path):
            logger.error(f"Model path {model_path} not found")
            raise FileNotFoundError(f"Model path {model_path} not found")
        return model_path


def get_huggingface_path(model_name: str, mode: Literal["local", "cached"] = "cached") -> str:
    """
    hf 缓存路径需要找到 snapshots 下最新的那个 hash 目录
    model_name 格式: 'Qwen/Qwen3.5-2B'  →  目录名: 'models--Qwen--Qwen3.5-2B'
    """
    if mode == "cached":
        dir_name = "models--" + model_name.replace("/", "--")
        snapshots_dir = os.path.join(os.getenv("HUGGINGFACE_CACHE_ROOT"), dir_name, "snapshots")
        
        # 取 snapshots 下第一个（通常只有一个）hash 目录
        hashes = os.listdir(snapshots_dir)
        if not hashes:
            logger.error(f"No snapshots found in {snapshots_dir}")
            raise FileNotFoundError(f"No snapshots found in {snapshots_dir}")
        
        model_path = os.path.normpath(os.path.join(snapshots_dir, hashes[0]))
        if not os.path.exists(model_path):
            logger.error(f"Model path {model_path} not found")
            raise FileNotFoundError(f"Model path {model_path} not found")
        return model_path
    
    elif mode == "local":
        model_path = os.path.normpath(os.path.join(os.getenv("HUGGINGFACE_LOCAL_ROOT"), model_name))
        if not os.path.exists(model_path):
            logger.error(f"Model path {model_path} not found")
            raise FileNotFoundError(f"Model path {model_path} not found")
        return model_path


