# app/config/config.py  # 语音RAG 系统的配置文件

from pathlib import Path
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.constants import milvusdb_root, qdrantdb_root, postgreSQLdb_root

# ===============================================================================
# 1. 基础模块配置 (BaseModel: 仅定义数据结构和默认值)
# ===============================================================================   

class LogConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    format: str = "%(asctime)s - %(levelname)s - %(filename)s[:%(lineno)d] - %(message)s"
    datefmt: str = "%Y-%m-%d %H:%M:%S"
    # 使用 pathlib.Path 管理路径更加优雅且不易出错
    file_path: Path = Path("temp/nene.log")
    file_max_size: str = "10 MB"
    file_retention: str = "7 days"
    
class LLMConfig(BaseModel):
    model: str = "Qwen/Qwen3-0.6B"  # 可替换为你的默认模型
    backend: Literal["modelscope", "huggingface"] = "huggingface"
    infer_engine: Literal["ollama", "transformers", "llama-cpp", "vllm", "cloud-openai"] = "transformers"
    load_mode: Literal["cached", "local", "cloud"] = "cached"
    device: Literal["cuda", "cpu"] = "cuda"
    # 预留多卡配置字段，默认分配 4 张卡
    device_ids: List[int] = Field(default_factory=lambda: [0, 1, 2, 3]) 
    server: str = "localhost"
    port: int = 8000
    api_key: Optional[str] = None  # 将由外层统一从 .env 注入

class EmbedConfig(BaseModel):
    model: str = "BAAI/bge-large-zh-v1.5"
    device: Literal["cuda", "cpu"] = "cuda"
    backend: Literal["modelscope", "huggingface"] = "huggingface"
    infer_engine: Literal["ollama", "transformers", "llama-cpp", "vllm", "cloud-openai"] = "transformers"
    device_ids: List[int] = Field(default_factory=lambda: [0])

class STTConfig(BaseModel):
    model: str = "SenseVoiceSmall"
    backend: Literal["modelscope", "huggingface"] = "huggingface"
    
    device: Literal["cuda", "cpu"] = "cpu"
    api_key: Optional[str] = None

class TTSConfig(BaseModel):
    model: str = "CosyVoice"
    backend: Literal["modelscope", "huggingface"] = "huggingface"
    device: Literal["cuda", "cpu"] = "cuda"
    api_key: Optional[str] = None

class ChunkConfig(BaseModel):
    chunk_size: int = 500
    chunk_overlap: int = 50
    separators: List[str] = Field(default_factory=lambda: ["\n\n", "\n", "。", "！", "？"])

class VectorDBConfig(BaseModel):
    provider: Literal["chroma", "milvus", "qdrant"] = "chroma"
    

# ==========================================
# 2. 全局根配置 (BaseSettings: 负责统合模块并读取环境变量)
# ==========================================

class NeneSettings(BaseSettings):
    """
    RAG 系统的全局配置单例类。
    所有模块的配置都会被挂载到这里。
    """
    log: LogConfig = Field(default_factory=LogConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embed: EmbedConfig = Field(default_factory=EmbedConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    chunk: ChunkConfig = Field(default_factory=ChunkConfig)
    vector_db: VectorDBConfig = Field(default_factory=VectorDBConfig)

    # pydantic-settings 配置字典
    model_config = SettingsConfigDict(
        env_file='config/.env',
        env_file_encoding='utf-8',
        # 允许忽略 .env 中多余的环境变量
        extra='ignore',
        # 核心技巧：使用双下划线作为嵌套分隔符
        env_nested_delimiter='__' 
    )

# 实例化全局配置对象，供其他文件 import 应用
settings = NeneSettings()

