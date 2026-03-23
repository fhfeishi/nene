import os, torch
from fastapi import FastAPI
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline

from app.components.utils_model_load import get_huggingface_path, get_modelscope_path

# ── 选择你要用的路径 ──────────────────────────────────────
# llm_path = get_modelscope_path("Qwen/Qwen3.5-2B")
llm_path = get_huggingface_path("Qwen/Qwen3.5-2B")

print(f"Loading model from: {llm_path}")

# ── 加载模型（CPU 模式，去掉 device_map）────────────────────
tokenizer = AutoTokenizer.from_pretrained(llm_path)

model = AutoModelForCausalLM.from_pretrained(
    llm_path,
    torch_dtype=torch.float32,  # 注意是 torch_dtype，不是 dtype
    low_cpu_mem_usage=True,     # 减少加载时的峰值内存占用
)
# CPU 环境下不需要 device_map，直接确保模型在 cpu 上
model = model.to("cpu")
model.eval()

pipe = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer,
    max_new_tokens=256,
    do_sample=True,
    temperature=0.7,
)

# ── FastAPI ───────────────────────────────────────────────
app = FastAPI()

class ChatRequest(BaseModel):
    messages: list[dict]

class ChatResponse(BaseModel):
    content: str

@app.post("/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    prompt = tokenizer.apply_chat_template(
        req.messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    output = pipe(prompt)
    generated = output[0]["generated_text"][len(prompt):]
    return ChatResponse(content=generated.strip())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)