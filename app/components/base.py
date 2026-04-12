# app/components/base.py

from typing import Callable, Optional, AsyncGenerator, List, Dict, Any, TypeVar, Generic
from abc import ABC, abstractmethod 
from config.config import (EmbedConfig, LLMConfig, STTConfig, TTSConfig, VectorDBConfig)
from pydantic import BaseModel, Field
import logging 

logger = logging.getLogger(__name__)

class Document(ABC):
    """向量库的最小检索单元"""
    __slots__ = ("content", "metadata", "score")

    def __init__(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        score: Optional[float] = None,
    ) -> None:
        self.content = content
        self.metadata: Dict[str, Any] = metadata or {}
        self.score = score

    def __repr__(self) -> str:
        return f"Document(score={self.score:.4f}, content={self.content[:40]!r})"


# ─────────────────────────────────────────────
# 泛型约束：让 BaseComponent 知道自己持有哪种 config
# ─────────────────────────────────────────────

# 用 TypeVar 约束：config 必须来自你的 config.py 里的具体类型之一
_ConfigT = TypeVar(
    "_ConfigT",
    LLMConfig,
    EmbedConfig,
    STTConfig,
    TTSConfig,
    VectorDBConfig,
)

class AudioConfig(BaseModel):
    """音频格式约定，STT / TTS 共用"""
    sample_rate: int = 16000
    channels: int = 1
    bit_depth: int = 16                    # PCM位深
    fmt: str = "wav"                       # wav / pcm / ogg


# ─────────────────────────────────────────────
# 根基类
# ─────────────────────────────────────────────
class BaseComponent(ABC, Generic[_ConfigT]):
    """
    所有模型组件的公共基类。
    泛型参数 _ConfigT 绑定到具体的 config 类型，
    让子类的 self.config 有精确的类型提示。

    例：
        class LocalLLM(BaseLLM):          # BaseLLM 已绑定 LLMConfig
            async def setup(self):
                self.config.infer_engine  # IDE 可以自动补全
    """

    def __init__(self, config: _ConfigT) -> None:
        self.config = config
        self._ready: bool = False
        self.logger = logging.getLogger(
            f"{self.__class__.__module__}.{self.__class__.__name__}"
        )

    @property
    def ready(self) -> bool:
        """只读属性：组件是否已就绪"""
        return self._is_ready
    
    # ── 生命周期 ────────────────────────────────
    @abstractmethod
    async def startup(self) -> None:
        """
        异步初始化：加载模型权重、建立连接。
        由 FastAPI lifespan 在服务启动时调用。
        实现时最后要设置 self._ready = True。
        """
        ...

    @abstractmethod
    async def teardown(self) -> None:
        """
        释放资源：卸载模型、关闭连接、清理缓存。
        由 FastAPI lifespan 在服务关闭时调用。
        """
        ...

    # ── 可选重写 ────────────────────────────────
    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查，供 GET /health 端点调用。
        子类重写时建议调用 super() 再追加自己的指标。
        """
        return {
            "component": self.__class__.__name__,
            "ready": self._ready,
            "device": getattr(self.config, "device", "unknown"),
        }


# ─────────────────────────────────────────────
# AI 组件基类 (LLM, Embed, TTS, STT)
# ─────────────────────────

# base class: llm
class BaseLLM(BaseComponent[LLMConfig]):
    """
    大语言模型推理基类，泛型已绑定 LLMConfig。
    """

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> str:
        """
        一次性返回完整回复。
        messages 遵循 OpenAI 格式：[{"role": "user", "content": "..."}]
        """
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """流式返回，每次 yield 一个 token 或文本片段。"""
        ...


# base class:  embeding 
class BaseEmbed(BaseComponent[EmbedConfig]):
    """文本向量化基类，泛型已绑定 EmbedConfig。"""

    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """
        批量向量化，返回与输入等长的向量列表。
        实现时应支持 normalize_embeddings，便于余弦相似度计算。
        """
        ...

    async def embed_one(self, text: str) -> List[float]:
        """单条便捷方法，默认复用 embed()，子类可按需重写提升效率。"""
        return (await self.embed([text]))[0]



# base class: TTS system
class BaseSTT(BaseComponent[STTConfig]):
    """语音转文字基类，泛型已绑定 STTConfig。"""

    @abstractmethod
    async def transcribe(self, audio_data: bytes) -> str:
        """一次性识别整段音频，适用于录音上传场景。"""
        ...

    @abstractmethod
    async def transcribe_stream(
        self,
        audio_stream: AsyncGenerator[bytes, None],
    ) -> AsyncGenerator[str, None]:
        """
        流式识别：边接收音频帧边输出文本片段。
        适用于实时通话场景，yield 的片段不保证是完整句子。
        """
        ...

    @abstractmethod
    async def force_finalize(self) -> str:
        """
        VAD 静默触发：强制断句，返回缓冲区全部文本并清空。
        仅在流式模式下有意义。
        """
        ...



# base class: tts
class BaseTTS(BaseComponent[TTSConfig]):
    """文字转语音基类，泛型已绑定 TTSConfig。"""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """一次性合成完整音频，适用于普通对话场景。"""
        ...

    @abstractmethod
    async def synthesize_stream(
        self,
        text_stream: AsyncGenerator[str, None],
    ) -> AsyncGenerator[bytes, None]:
        """
        流式合成：LLM 每生成一段文本立刻转为音频 yield 出去。
        用于降低语音回复的首包延迟。
        """
        ...




# base class : vector store
class BaseVectorStore(BaseComponent[VectorDBConfig]):
    """向量数据库基类，屏蔽 Chroma / Milvus / Qdrant 底层差异。"""

    @abstractmethod
    async def add(
        self,
        documents: List[Document],
        embeddings: List[List[float]],
    ) -> List[str]:
        """存入文档及对应向量，返回各文档在库中的 ID。"""
        ...

    @abstractmethod
    async def search(
        self,
        query_embedding: List[float],
        top_k: Optional[int] = None,        # None 则使用 config.top_k
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        """
        向量相似度检索，返回 Document 列表（含 score）。
        filters 对应 config 里的 metadata_filter 逻辑。
        """
        ...

    @abstractmethod
    async def delete(self, ids: List[str]) -> None:
        """按 ID 删除文档"""
        ...

    @abstractmethod
    async def count(self) -> int:
        """返回当前集合的文档总数"""
        ...




# base class: retriever 
class BaseRetriever(BaseComponent[VectorDBConfig]):
    """
    检索器基类，持有 VectorDBConfig（含 top_k、similarity、threshold 等）。
    与 BaseVectorStore 分离的原因：
    检索策略多样（纯向量 / 关键词 / 混合 / 重排），不一定都需要向量库。
    """

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        """
        检索相关文档。
        top_k 默认取 self.config.top_k。
        filters 默认取 self.config.metadata_filter。
        """
        ...



# ─────────────────────────────────────────────
# RAG 编排器基类
# ─────────────────────────────────────────────
# base class: RAG sys
class BaseRAG(ABC):
    """
    RAG 系统编排基类，不继承 BaseComponent。
    它是调度器，不是模型，通过依赖注入组合各组件。
    """

    def __init__(
        self,
        llm: BaseLLM,
        retriever: BaseRetriever,
        *,
        embed: Optional[BaseEmbed] = None,
        stt: Optional[BaseSTT] = None,
        tts: Optional[BaseTTS] = None,
    ) -> None:
        self.llm = llm
        self.retriever = retriever
        self.embed = embed
        self.stt = stt
        self.tts = tts

    # ── 子类必须实现 ────────────────────────────

    @abstractmethod
    def _build_prompt(
        self,
        query: str,
        documents: List[Document],
        history: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """
        将检索到的文档和对话历史拼装成 LLM messages。
        Prompt 工程集中在这里管理。
        """
        ...

    @abstractmethod
    async def query(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """标准问答，返回完整回复字符串。"""
        ...

    @abstractmethod
    async def query_stream(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[str, None]:
        """流式问答，逐 token yield 回复文本。"""
        ...

    # ── 模式一：对讲机模式 (Hold-to-Talk) ────────────
    
    @abstractmethod
    async def voice_query_stream(
        self,
        audio_data: bytes,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[bytes, None]:
        """
        完整语音 RAG 流程：“按住说话 -> 松开发送”的单工模式。
        数据流向：整段音频 → STT → 检索+LLM流式生成 → TTS流式合成 → 音频输出流
        
        具体实现契约：
        1. 必须检验 stt 和 tts 依赖是否已注入。
        2. 调用 STT 的一次性识别接口（如 transcribe）。
        3. 组装历史记录，调用自身的 query_stream 获取文本流。
        4. 将文本流送入 TTS 的 synthesize_stream，并逐块 yield 音频帧。
        """
        ...

    # ── 模式二：实时双工通话模式 (Full-Duplex) ────────────
    
    @abstractmethod
    async def voice_realtime_stream(
        self,
        audio_stream: AsyncGenerator[bytes, None],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[bytes, None]:
        """
        完整语音 RAG 流程：实时语音双工通话 (Full-Duplex)。
        特征：流式输入，流式输出，支持边听边发声，支持用户插话打断 (Barge-in)。
        
        具体实现契约：
        1. 必须异步消费 audio_stream 传入的麦克风音频帧。
        2. 结合流式 STT (send_audio_frame) 和 VAD 机制进行断句。
        3. 断句后启动独立的后台任务（Task）执行 LLM + TTS 流水线。
        4. 必须实现打断机制：当 AI 正在输出音频时，若检测到用户重新开始说话，
           需立即 cancel() 当前的生成任务，并 yield 中断控制帧（如 b"__INTERRUPT__"）。
        """
        ...


    def _log_stt_result(self, text: str) -> None:
        logger.info(
            "[%s] STT result: %s",
            self.__class__.__name__,
            text[:100] + ("..." if len(text) > 100 else ""),
        )
    
    