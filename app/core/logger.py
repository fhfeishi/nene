# app/core/logger.py 

import logging
import sys 
from app.core.config import settings 

def setup_logging():
    """全局日志初始化"""
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format=settings.LOG_FORMAT,
        datefmt="%H:%M:%S",
        # 显式指定输出到标准输出，防止容器环境日志丢失
        handlers=[logging.StreamHandler(sys.stdout)],
        # filename = temp/logs.log  # 
    )
    
    # 捕获 Python warnings (如 DeprecationWarning) 到日志
    logging.captureWarnings(True)
    
    # [可选] 压制一些过于啰嗦的第三方库日志
    # logging.getLogger("httpx").setLevel(logging.WARNING)
    # logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    # 测试一下
    logger = logging.getLogger(__name__)
    logger.info(f"Logger initialized with level: {settings.LOG_LEVEL}")


