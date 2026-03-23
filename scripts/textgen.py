
# textgen.py

"""   pwsh中运行： 后台服务
llama-server -m "E:\local_models\huggingface\cache\hub\models--Qwen--Qwen3-1.7B-GGUF\snapshots\90862c4b9d2787eaed51d12237eafdfe7c5f6077\Qwen3-1.7B-Q8_0.gguf" --host 127.0.0.1 --port 8080
"""
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from openai import AsyncOpenAI
from loguru import logger

# 1. 初始化 FastAPI
app = FastAPI(title="Voice Chatbot API", description="LLM + (Future) TTS Backend")

# 2. 初始化 LLM 客户端，指向你本地后台运行的 llama-server (端口 8080)
llm_client = AsyncOpenAI(
    base_url="http://127.0.0.1:8080/v1",
    api_key="sk-not-needed"  # 本地服务不需要真实的 API Key
)

# 定义前端传过来的数据格式
class ChatRequest(BaseModel):
    message: str

# 核心函数：封装 LLM 推理任务
async def generate_text_reply(user_message: str) -> str:
    """调用本地 llama-server 生成回复"""
    try:
        response = await llm_client.chat.completions.create(
            model="qwen3-1.7b", # 这里填什么都可以，llama-server 只认它加载的那个本地文件
            messages=[
                {"role": "system", "content": "你是一个亲切的语音助手。请用简短、口语化的中文回复，不要使用复杂的排版，方便后续转换为语音。"},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=200
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"LLM 推理失败: {e}")
        return "抱歉，我的大脑好像短路了。"

# 3. 暴露给外部调用的 API 接口
@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    logger.info(f"收到用户输入: {request.message}")
    
    # 步骤 A: 获取大模型文字回复
    reply_text = await generate_text_reply(request.message)
    logger.info(f"LLM 文本回复: {reply_text}")
    
    # 步骤 B: 预留给后续 TTS 模型的处理位置
    # audio_file_path = await text_to_speech(reply_text)
    
    # 步骤 C: 将文字（和未来的语音文件 URL）返回给客户端
    return {
        "status": "success",
        "reply_text": reply_text,
        # "audio_url": f"/static/{audio_file_path}"  # 未来接入 TTS 后启用
    }

if __name__ == "__main__":
    logger.info("启动 FastAPI 主服务 on http://127.0.0.1:8000")
    # 让 FastAPI 跑在 8000 端口，与 Llama-server 的 8080 端口错开
    uvicorn.run(app, host="127.0.0.1", port=8000)








