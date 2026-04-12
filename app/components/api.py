# app/components/api.py
import os
import logging
import time
import pyaudio 
import asyncio 
from typing import Dict 
from contextlib import asynccontextmanager
from fastapi import FastAPI 


from app.components.component_llm import LlamaCppServerLLMcpu
from app.components.component_tts import EdgeTTS, KokoroTTS, QwenTTS

# 全局实例化
llm_engine = LlamaCppServerLLMcpu()
tts_engine = EdgeTTS()


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await llm_engine.startup()
    await tts_engine.start_up()
    
    yield 
    
    await llm_engine.teardown()
    await tts_engine.teardown()

app = FastAPI(lifespan=lifespan)

