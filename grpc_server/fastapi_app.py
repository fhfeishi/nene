# fastapi - client

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import grpc 
import base64 
import tts_pb2, tts_pb2_grpc
from loguru import logger 


app = FastAPI(title="nene API Gateway")


class TextInput(BaseModel):
    text: str 
    
    
@app.post("/api/stream-tts")
async def generate_speech(input_data: TextInput):
    # 作为客户端，连接到 grpc 服务器
    try:
        with grpc.insecure_channel("localhost:50051") as channel:
            # 创建一个用于调用的存根 Stub
            stub = tts_pb2_grpc.TTSServiceStub(channel)
            
            # 打包请求消息 
            grpc_request = tts_pb2.TTSRequest(text=input_data.text)
            
            logger.info(f"FastAPI 正在通过 gRPC 呼叫服务...")
            # 发起同步调用（生产环境可以用 grpc.aio 实现异步调用）
            grpc_response = stub.Synthesize(grpc_request)
            
            # 拿到底层的二进制数据后，可以转成 base64 返回给前端
            # 或者直接作为 FileResponse 返回
            audio_b64 = base64.b64encode(grpc_response.audio_data).decode('utf-8')
            
            
            return {
                "message": "TTS 转换成功",
                "audio_base64": audio_b64
            }
    except grpc.RpcError as e:
        raise HTTPException(status_code=500, detail=f"gRPC 服务连接失败: {e.details()}")



