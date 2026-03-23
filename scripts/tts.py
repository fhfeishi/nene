# tts.py

import os 
import torch 
import soundfile as sf
from loguru import logger

HUGGINGFACE_ROOT = r"E:\local_models\huggingface\cache\hub"
def get_huggingface_path(model_name: str) -> str:
    """
    hf 缓存路径需要找到 snapshots 下最新的那个 hash 目录
    model_name 格式: 'Qwen/Qwen3.5-2B'  →  目录名: 'models--Qwen--Qwen3.5-2B'
    """
    dir_name = "models--" + model_name.replace("/", "--")
    snapshots_dir = os.path.join(HUGGINGFACE_ROOT, dir_name, "snapshots")
    
    # 取 snapshots 下第一个（通常只有一个）hash 目录
    hashes = os.listdir(snapshots_dir)
    if not hashes:
        raise FileNotFoundError(f"No snapshots found in {snapshots_dir}")
    
    return os.path.normpath(os.path.join(snapshots_dir, hashes[0]))
tts_model = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"

tts_model_path = get_huggingface_path(tts_model)

if not os.path.exists(tts_model_path):
    logger.error(f"路径不存在: {tts_model_path}")
else:
    logger.info(f"正在加载模型: {tts_model_path}")
    
    try:
        from qwen_tts import Qwen3TTSModel
        # 2. 尝试加载
        model = Qwen3TTSModel.from_pretrained(
            tts_model_path,
            device_map="cpu",
            dtype=torch.float32,
            attn_implementation="sdpa",
            trust_remote_code=True # 有些模型需要这个
        )
        logger.info("模型加载成功！")
    except Exception as e:
        logger.exception(f"加载失败: {e}")


# single inference
wavs, sr = model.generate_custom_voice(
    text="其实我真的有发现，我是一个特别善于观察别人情绪的人。",
    language="Chinese", # Pass `Auto` (or omit) for auto language adaptive; if the target language is known, set it explicitly.
    speaker="Vivian",
    instruct="用特别愤怒的语气说", # Omit if not needed.
)
sf.write("output_custom_voice.wav", wavs[0], sr)
logger.info(f"single inference done.")

# batch inference
wavs, sr = model.generate_custom_voice(
    text=[
        "其实我真的有发现，我是一个特别善于观察别人情绪的人。", 
        "She said she would be here by noon."
    ],
    language=["Chinese", "English"],
    speaker=["Vivian", "Ryan"],
    instruct=["", "Very happy."]
)
sf.write("output_custom_voice_1.wav", wavs[0], sr)
logger.info(f"batch inference-1 done.")
sf.write("output_custom_voice_2.wav", wavs[1], sr)
logger.info(f"batch inference-2 done.")

