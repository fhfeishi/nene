# app/components/llm/llm_api.py

import logging
from app.components.llm.component import QwenLLM
# from app.components.llm.component import OtherLLM
from abc import ABC, abstractmethod 
from typing import Literal
 

logger = logging.getLogger(__name__)


class LLMInterfaceBase(ABC):
    def __init__(self, mode: Literal["local", "cloud"] = "local"):
        self.mode = mode 
        
    @abstractmethod
    def _init_model(self):
        
        
        
        
        pass 
        

    pass 

class LLMInterface:
    """ 
    LLM 的统一入口（工厂类）。
    负责根据全局配置，返回对应的 LLM 实例。
    """
    
    @staticmethod
    def get_instance(cfg):
        """
        根据 cfg.llm.model_id_or_path 判断返回哪个具体的实现类。
        """
        model_name = cfg.llm.model_id.lower()
        
        if "qwen" in model_name:
            logger.info("Routing to QwenLLM wrapper.")
            return QwenLLM(cfg)
        
        # 预留其他模型的扩展空间
        # elif "llama" in model_name:
        #     return LlamaLLM(cfg)
        
        else:
            # 默认 fallback 或抛出异常
            logger.warning(f"No specific wrapper found for {model_name}, using default QwenLLM fallback.")
            return QwenLLM(cfg)

# ====================================================================
# 使用示例 (伪代码，展示如何在 FastAPI 或主程序中调用)
# ====================================================================
"""
from config.config import settings
from app.components.llm.llm_api import LLMInterface

# 1. 获取统一的 LLM 实例
llm = LLMInterface.get_instance(settings)

# 2. 在 FastAPI 的异步路由中调用
@app.post("/chat")
async def chat_endpoint(request: Request):
    user_text = await request.json()
    prompt = user_text.get("prompt")
    
    # 3. 将 llm.astream_chat 返回的异步生成器传递给 StreamingResponse
    from fastapi.responses import StreamingResponse
    return StreamingResponse(llm.astream_chat(prompt), media_type="text/event-stream")
"""