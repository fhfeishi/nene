from app.components.base import (
    Document,
    BaseComponent,
    BaseLLM,
    BaseEmbed,
    BaseSTT,
    BaseTTS,
    BaseVectorStore,
    BaseRetriever,
    BaseRAG,
    AudioConfig,
)


def __getattr__(name: str):
    """Lazy import for sub-packages to avoid failing when optional deps are missing."""
    _imports = {
        # LLM
        "LlamaCppLLM": "app.components.llm",
        "VllmLLM": "app.components.llm",
        "CloudLLM": "app.components.llm",
        "LLMFactory": "app.components.llm",
        # Embed
        "SentenceTransformerEmbed": "app.components.embed",
        "CloudEmbed": "app.components.embed",
        "EmbedFactory": "app.components.embed",
        # STT
        "FunASRSTT": "app.components.stt",
        "STTFactory": "app.components.stt",
        # TTS
        "EdgeTTS": "app.components.tts",
        "KokoroTTS": "app.components.tts",
        "QwenTTS": "app.components.tts",
        "CosyVoiceTTS": "app.components.tts",
        "CloudTTS": "app.components.tts",
        "TTSFactory": "app.components.tts",
        # VectorDB
        "ChromaVectorStore": "app.components.vectordb",
        "MilvusVectorStore": "app.components.vectordb",
        "VectorStoreFactory": "app.components.vectordb",
        # RAG
        "RAGPipeline": "app.components.rag",
    }

    if name in _imports:
        module = __import__(_imports[name], fromlist=[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
