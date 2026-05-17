# app/components/rag/component.py

import logging
from typing import List, Dict, Any, Optional, AsyncGenerator

from app.components.base import (
    BaseRAG,
    BaseLLM,
    BaseRetriever,
    BaseEmbed,
    BaseSTT,
    BaseTTS,
    Document,
)
from app.components.rag.prompts import DEFAULT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class RAGPipeline(BaseRAG):
    """标准 RAG 编排器实现"""

    def __init__(
        self,
        llm: BaseLLM,
        retriever: BaseRetriever,
        *,
        embed: Optional[BaseEmbed] = None,
        stt: Optional[BaseSTT] = None,
        tts: Optional[BaseTTS] = None,
    ):
        super().__init__(llm, retriever, embed=embed, stt=stt, tts=tts)

    # ── Prompt 组装 ────────────────────────────

    def _build_prompt(
        self,
        query: str,
        documents: List[Document],
        history: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        context = "\n\n---\n\n".join(
            f"[{d.metadata.get('source', 'unknown')}]\n{d.content}"
            for d in documents
        )
        system_msg = DEFAULT_SYSTEM_PROMPT.format(context=context)
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_msg}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": query})
        return messages

    # ── 标准问答 ───────────────────────────────

    async def query(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        history = history or []
        documents = await self.retriever.retrieve(query)
        if not documents:
            return "抱歉，未检索到相关内容。"
        messages = self._build_prompt(query, documents, history)
        return await self.llm.chat(messages)

    async def query_stream(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[str, None]:
        history = history or []
        documents = await self.retriever.retrieve(query)
        if not documents:
            yield "抱歉，未检索到相关内容。"
            return
        messages = self._build_prompt(query, documents, history)
        async for token in self.llm.chat_stream(messages):
            yield token

    # ── 语音 RAG：对讲机模式 (Hold-to-Talk) ─────

    async def voice_query_stream(
        self,
        audio_data: bytes,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[bytes, None]:
        if not self.stt or not self.tts:
            raise RuntimeError("voice_query_stream requires STT and TTS components")

        history = history or []
        query_text = await self.stt.transcribe(audio_data)
        self._log_stt_result(query_text)

        async for audio_chunk in self.tts.synthesize_stream(
            self.query_stream(query_text, history)
        ):
            yield audio_chunk

    # ── 语音 RAG：实时双工 (Full-Duplex) ────────

    async def voice_realtime_stream(
        self,
        audio_stream: AsyncGenerator[bytes, None],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[bytes, None]:
        if not self.stt or not self.tts:
            raise RuntimeError("voice_realtime_stream requires STT and TTS components")

        import asyncio

        history = history or []
        current_task: Optional[asyncio.Task] = None

        async def _generate_and_speak(text: str):
            async for audio in self.tts.synthesize_stream(
                self.query_stream(text, history)
            ):
                yield audio

        async for text_fragment in self.stt.transcribe_stream(audio_stream):
            final_text = await self.stt.force_finalize()
            if final_text:
                history.append({"role": "user", "content": final_text})
                self._log_stt_result(final_text)

                # cancel previous AI speech if user interrupts
                if current_task and not current_task.done():
                    current_task.cancel()
                    yield b"__INTERRUPT__"

                async def _run_tts_pipeline():
                    async for audio in self.tts.synthesize_stream(
                        self.query_stream(final_text, history)
                    ):
                        yield audio

                # In real implementation, this would be a proper async task
                async for audio in self.tts.synthesize_stream(
                    self.query_stream(final_text, history)
                ):
                    yield audio
