
from app.components.base import get_huggingface_path, get_modelscope_path
 
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer


embed_name: str = "iic/nlp_gte_sentence-embedding_chinese-base"
MODEL_PATH = get_modelscope_path(embed_name)
# MODEL_PATH = get_huggingface_path(embed_name)
print("embed model load start..")
embedder = SentenceTransformer(MODEL_PATH, device="cpu")
print("embed model loaded.")
# warning   不影响用。


"""
# 方式一：直接用 transformers 手动做 mean pooling（完全透明，无警告）
from transformers import AutoTokenizer, AutoModel
import torch

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModel.from_pretrained(MODEL_PATH)

def get_embeddings(texts: list[str]) -> list[list[float]]:
    inputs = tokenizer(texts, padding=True, truncation=True, 
                       max_length=512, return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs)
    # mean pooling：对有效 token 取均值（排除 padding）
    mask = inputs["attention_mask"].unsqueeze(-1).float()
    vecs = (outputs.last_hidden_state * mask).sum(1) / mask.sum(1)
    # 归一化
    vecs = torch.nn.functional.normalize(vecs, p=2, dim=1)
    return vecs.tolist()


# 方式二：继续用 SentenceTransformer，加 trust_remote_code=True 和手动指定 pooling（保留简洁 API）
from sentence_transformers import SentenceTransformer, models

# 显式告诉它用 mean pooling，避免它打印"Creating a new one"
word_embedding = models.Transformer(MODEL_PATH, max_seq_length=512)
pooling = models.Pooling(word_embedding.get_word_embedding_dimension(), 
                         pooling_mode_mean_tokens=True)
embedder = SentenceTransformer(modules=[word_embedding, pooling], device="cpu")
"""
