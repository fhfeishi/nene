# grpc_server.py
import grpc
from concurrent import futures
import tts_pb2
import tts_pb2_grpc
from loguru import logger 

class TTSService(tts_pb2_grpc.TTSServiceServicer):
    def Synthesize(self, request, context):
        logger.info(f"[gRPC Server] 收到要合成的文本: {request.text}")
        
        # 这里在未来会替换成你真实的 TTS 推理代码 (比如 VITS, Edge-TTS 等)
        # 假设我们生成了一段 8 字节的模拟音频
        fake_wav_bytes = b"WAV_DATA:" + request.text.encode('utf-8')
        
        logger.info("[gRPC Server] 合成完毕，返回二进制流...")
        return tts_pb2.TTSResponse(audio_data=fake_wav_bytes)

def serve():
    # 创建 gRPC 服务器，允许最多 10 个并发工作线程
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    tts_pb2_grpc.add_TTSServiceServicer_to_server(TTSService(), server)
    
    # 绑定 50051 端口
    server.add_insecure_port('[::]:50051')
    server.start()
    logger.info("🚀 gRPC TTS 微服务已启动，监听 50051 端口...")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()