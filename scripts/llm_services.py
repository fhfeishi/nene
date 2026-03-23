import os, torch
from fastapi import FastAPI
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline

# ── 路径配置 ──────────────────────────────────────────────
MODELSCOPE_ROOT = r"E:\local_models\modelscope\models"
HUGGINGFACE_ROOT = r"E:\local_models\huggingface\cache\hub"

def get_modelscope_path(model_name: str) -> str:
    """modelscope 路径直接拼接即可，如 'Qwen/Qwen3.5-2B'"""
    return os.path.normpath(os.path.join(MODELSCOPE_ROOT, model_name))

def get_huggingface_path(model_name: str) -> str:
    """
    hf 缓存路径需要找到 snapshots 下最新的那个 hash 目录
    model_name 格式: 'Qwen/Qwen3.5-2B'  →  目录名: 'models--Qwen--Qwen3.5-2B'
    """
    dir_name = "models--" + model_name.replace("/", "--")
    snapshots_dir = os.path.join(HUGGINGFACE_ROOT, dir_name, "snapshots")
    
    # 取 snapshots 下第一个（通常只有一个）hash 目录
    hashes = os.listdir(snapshots_dir)
    if not hashes:
        raise FileNotFoundError(f"No snapshots found in {snapshots_dir}")
    
    return os.path.normpath(os.path.join(snapshots_dir, hashes[0]))

# ── 选择你要用的路径 ──────────────────────────────────────
llm_path = get_modelscope_path("Qwen/Qwen3.5-2B")
# llm_path = get_huggingface_path("Qwen/Qwen3.5-2B")

print(f"Loading model from: {llm_path}")

# ── 加载模型（CPU 模式，去掉 device_map）────────────────────
tokenizer = AutoTokenizer.from_pretrained(llm_path)

model = AutoModelForCausalLM.from_pretrained(
    llm_path,
    dtype=torch.float32,  
    device_map="cpu",    
    low_cpu_mem_usage=True,     # 减少加载时的峰值内存占用
)
# # CPU 环境下不需要 device_map，直接确保模型在 cpu 上
# model = model.to("cpu")
# model.eval()
print("model loaded down!")

pipe = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer,
    max_new_tokens=256,
    do_sample=True,
    temperature=0.7,
)
print("model pipeline set.")

# # ── FastAPI ───────────────────────────────────────────────
# app = FastAPI()

# class ChatRequest(BaseModel):
#     messages: list[dict]

# class ChatResponse(BaseModel):
#     content: str

# @app.post("/v1/chat", response_model=ChatResponse)
# def chat(req: ChatRequest):
#     prompt = tokenizer.apply_chat_template(
#         req.messages,
#         tokenize=False,
#         add_generation_prompt=True,
#     )
#     output = pipe(prompt)
#     generated = output[0]["generated_text"][len(prompt):]
#     return ChatResponse(content=generated.strip())

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8001)