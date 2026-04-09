# app/config/config.py  # 语音RAG 系统的配置文件

from pathlib import Path
from typing import Any, Callable, List, Literal, Optional, Dict 
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.constants import root_dir, temp_dir, milvusdb_root, qdrantdb_root, postgreSQLdb_root, chromadb_root

# ===============================================================================
# 1. 基础模块配置 (BaseModel: 仅定义数据结构和默认值)
# ===============================================================================   
class LogConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    fmt: str = "%(asctime)s - %(levelname)s - %(filename)s[:%(lineno)d] - %(message)s"
    datefmt: str = "%Y-%m-%d %H:%M:%S"
    file_path: Path = temp_dir / "nene.log"
    file_max_size: str = "10 MB"
    file_retention: str = "7 days"
    
    
class LLMConfig(BaseModel):
    # model id 
    model_id: str = "Qwen/Qwen3-1.7B"  
    # 模型下载来源：modelscope 或 huggingface
    hub_backend: Literal["modelscope", "huggingface"] = "modelscope"
    # 核心：推理引擎选择
    infer_engine: Literal["transformers", "llama-cpp", "vllm", "cloud-api"] = "llama-cpp"
    
    # device 配置
    device: Literal["cuda", "cpu"] = "cuda"
    device_ids: List[int] = Field(default_factory=lambda: [0])
    
    # 云端 API / 外部服务配置 (当 infer_engine 为 cloud-api 时使用)
    base_url: Optional[str] = None
    api_key: Optional[str] = None  
    
    # llama.cpp  --python   infer:
    gguf_file: Optional[str] = r"E:\local_models\huggingface\local\qwen3.5-2b-gguf\Qwen_Qwen3.5-2B-Q8_0.gguf"
    
    # vllm --python infer:
    
    
    
    # 本地服务对外暴露的端口
    server_host: str = "127.0.0.1"
    server_port: int = 8000


class EmbedConfig(BaseModel):
    # model id 
    model_id: str = "BAAI/bge-large-zh-v1.5"
    hub_backend: Literal["modelscope", "huggingface"] = "huggingface"
    # Embedding 通常用 transformers 或专门的句向量库，llama-cpp 也支持 GGUF 格式的 embedding
    infer_engine: Literal["transformers", "sentence-transformers", "llama-cpp", "cloud-api"] = "sentence-transformers"
    
    # device 配置
    device: Literal["cuda", "cpu"] = "cuda"
    device_ids: List[int] = Field(default_factory=lambda: [0])
    
    # for cloud-api
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class STTConfig(BaseModel):
    # model id 
    model_id: str = "SenseVoiceSmall"
    hub_backend: Literal["modelscope", "huggingface"] = "huggingface"
    # normal 代表使用 FunASR 等官方 SDK 直接加载
    infer_engine: Literal["normal", "cloud-api"] = "normal"
    
    # device 配置
    device: Literal["cuda", "cpu"] = "cuda"
    device_ids: List[int] = Field(default_factory=lambda: [0])
    
    # for cloud-api
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class TTSConfig(BaseModel):
    # model id 
    model_id: str = "iic/CosyVoice-300M"
    hub_backend: Literal["modelscope", "huggingface"] = "huggingface"
    # normal 代表使用 qwen_tts 等官方 SDK 直接加载
    infer_engine: Literal["normal", "cloud-api"] = "normal"
    
    # device 配置
    device: Literal["cuda", "cpu"] = "cuda"
    device_ids: List[int] = Field(default_factory=lambda: [0])
    
    # for cloud-api
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class ChunkConfig(BaseModel):
    chunk_size: int = 500
    chunk_overlap: int = 50
    separators: List[str] = Field(default_factory=lambda: ["\n\n", "\n", "。", "！", "？"])


class VectorDBConfig(BaseModel):
    provider: Literal["chroma", "milvus", "qdrant"] = "chroma"
    
    host: str = "127.0.0.1"
    port: int = 8000
    api_key: Optional[str] = None
    
    collection_name: str = "nene_collection"
    persist_directory: Optional[Path] = chromadb_root # milvusdb_root, qdrantdb_root, postgreSQLdb_root
    
    # embedding_function: Optional[Callable] = None  # 纯粹的接收 List[float] 就好了
    
    # retriever 配置
    similarity: Literal["cosine", "euclidean"] = "cosine"  # 相似度计算方式
    distance_threshold: float = 0.5  # 距离阈值
    top_k: int = 10   # 检索结果数量
    search_kwargs: Dict[str, Any] = Field(default_factory=dict)  # 检索参数
    metadata_fields: List[str] = Field(default_factory=lambda: ["source_file", "chunk_type"])  # 元数据字段，用于过滤
    metadata_filter: Optional[Dict[str, Any]] = None  # 元数据过滤，用于过滤


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

    @model_validator(mode='after')
    def validate_cloud_api(self) -> 'NeneSettings':
        """
        验证逻辑：如果某个模块使用了 cloud-api 作为引擎，最好要有 api_key。
        这里可以放置跨字段的全局校验逻辑。
        """
        modules = [self.llm, self.embed, self.stt, self.tts]
        for mod in modules:
            if getattr(mod, "infer_engine", None) == "cloud-api" and not mod.api_key:
                raise ValueError(f"{mod.__class__.__name__} 启用了 cloud-api，但未设置 api_key")
        return self
    
# 实例化全局配置对象，供其他文件 import 应用
settings = NeneSettings()



# --- 测试打印 (可删除) ---
if __name__ == "__main__":
    print(f"Project Root: {root_dir}")
    print(f"LLM Engine: {settings.llm.infer_engine}")
    print(f"TTS Model: {settings.tts.model_id}")