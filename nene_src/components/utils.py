# app/components/utils.py

import os
import re
import logging
from typing import Literal, AsyncGenerator

import dotenv

dotenv.load_dotenv()
logger = logging.getLogger(__name__)

# ── 标点分句 ────────────────────────────────

SENTENCE_ENDINGS = re.compile(r'([。？！；\?\!;]+)')


async def sentence_buffer(text_stream: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
    """
    接收 LLM 逐字输出的文本流，按标点符号组装成完整的句子再 yield，
    保证 TTS 引擎能读出正常的语调。
    """
    buffer = ""
    async for chunk in text_stream:
        buffer += chunk
        parts = SENTENCE_ENDINGS.split(buffer)
        if len(parts) > 1:
            buffer = parts.pop()
            for i in range(0, len(parts), 2):
                if i + 1 < len(parts):
                    sentence = parts[i] + parts[i + 1]
                    if sentence.strip():
                        yield sentence.strip()

    if buffer.strip():
        yield buffer.strip()


# ── 模型路径解析 ────────────────────────────

def get_modelscope_path(model_name: str, mode: Literal["local", "cached"] = "cached") -> str:
    if mode == "cached":
        model_path = os.path.normpath(os.path.join(
            os.getenv("MODELSCOPE_CACHED_ROOT", ""), model_name
        ))
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model path {model_path} not found")
        return model_path
    elif mode == "local":
        model_path = os.path.normpath(os.path.join(
            os.getenv("MODELSCOPE_LOCAL_ROOT", ""), model_name
        ))
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model path {model_path} not found")
        return model_path
    raise ValueError(f"Unknown mode: {mode}")


def get_huggingface_path(model_name: str, mode: Literal["local", "cached"] = "cached") -> str:
    if mode == "cached":
        dir_name = "models--" + model_name.replace("/", "--")
        snapshots_dir = os.path.join(
            os.getenv("HUGGINGFACE_CACHE_ROOT", ""), dir_name, "snapshots"
        )
        hashes = os.listdir(snapshots_dir)
        if not hashes:
            raise FileNotFoundError(f"No snapshots found in {snapshots_dir}")
        model_path = os.path.normpath(os.path.join(snapshots_dir, hashes[0]))
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model path {model_path} not found")
        return model_path
    elif mode == "local":
        model_path = os.path.normpath(os.path.join(
            os.getenv("HUGGINGFACE_LOCAL_ROOT", ""), model_name
        ))
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model path {model_path} not found")
        return model_path
    raise ValueError(f"Unknown mode: {mode}")


def resolve_model_path(model_id: str, hub_backend: str) -> str:
    """根据 hub_backend 解析本地模型路径"""
    if hub_backend == "modelscope":
        try:
            return get_modelscope_path(model_id)
        except FileNotFoundError:
            return get_modelscope_path(model_id, mode="local")
    elif hub_backend == "huggingface":
        try:
            return get_huggingface_path(model_id)
        except FileNotFoundError:
            return get_huggingface_path(model_id, mode="local")
    else:
        return model_id
