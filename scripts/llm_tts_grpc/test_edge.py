# test_edge.py  (在 tts_server.py 同目录运行)
import asyncio, sys
sys.path.insert(0, "generated")
import tts_pb2, tts_pb2_grpc
from grpc import aio as grpc_aio

async def main():
    channel = grpc_aio.insecure_channel("localhost:50051")
    stub = tts_pb2_grpc.TTSServiceStub(channel)

    print("测试 EdgeTTS（需要网络）...")
    chunks = []
    async for chunk in stub.Synthesize(tts_pb2.SynthesizeRequest(
        text="今天天气真不错", engine="edge"
    )):
        chunks.append(chunk)
    
    print(f"EdgeTTS 返回 {len(chunks)} 块" if chunks else "❌ 没有返回数据，代理可能有问题")
    await channel.close()

asyncio.run(main())