# 测试一下新的模型和环境依赖

from loguru import logger 
import os 
# modelscope 封装代码  太老旧了， 建议舍弃。 用 transformers

# 解析 huggingface cached model
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

# --------------- llm test  ----------------------------------------
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
import torch 

model_name = "Qwen/Qwen3-1.7B"
llm_path = get_huggingface_path(model_name)
logger.info(f"Loading {model_name} model from: {llm_path}")

# ── 加载模型（CPU 模式，去掉 device_map）────────────────────
tokenizer = AutoTokenizer.from_pretrained(llm_path)

model = AutoModelForCausalLM.from_pretrained(
    llm_path,
    dtype=torch.float32,   # torch_dtype dtype
    device_map="cpu",    
    low_cpu_mem_usage=True,     # 减少加载时的峰值内存占用
)
# # CPU 环境下不需要 device_map，直接确保模型在 cpu 上
# model = model.to("cpu")
# model.eval()
logger.info(f"{model_name} model loaded down!")

pipe = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer,
    max_new_tokens=256,
    do_sample=True,
    temperature=0.7,
)
logger.info(f"{model_name} model pipeline set.")

# ----------------  embed  -----------------------------------
from transformers import AutoTokenizer, AutoModel
import torch.nn.functional as F
# 不建议使用modelscope的封装

model_id = "iic/nlp_gte_sentence-embedding_chinese-base"
embed_model_path = get_modelscope_path(model_id)
tokenizer_se = AutoTokenizer.from_pretrained(embed_model_path)
model_se = AutoModel.from_pretrained(embed_model_path)
model_se.eval()

logger.info(f"embed model loaded down!")

def pipeline_se_mimic(input_dict):
    """
    自己实现一个轻量级的 pipeline，完全复刻 ModelScope 的行为和输出格式
    """
    source_sentences = input_dict.get("source_sentence", [])
    compare_sentences = input_dict.get("sentences_to_compare", [])
    
    # 把所有句子拼起来一起算，提高计算效率
    all_sentences = source_sentences + compare_sentences
    if not all_sentences:
        return {"text_embedding": [], "scores": []}

    # Tokenize
    encoded_input = tokenizer_se(all_sentences, padding=True, truncation=True, max_length=512, return_tensors='pt')

    # 计算 token embeddings
    with torch.no_grad():
        model_output = model_se(**encoded_input)

    # 执行 Mean Pooling (GTE 模型的标准池化方式)
    token_embeddings = model_output.last_hidden_state
    attention_mask = encoded_input['attention_mask']
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    
    sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
    sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
    embeddings = sum_embeddings / sum_mask

    # 结果组装
    result = {
        # 转成 numpy 数组，和 ModelScope 保持一致
        "text_embedding": embeddings.numpy() 
    }

    # 如果存在 compare 句子，计算相似度 Score
    scores = []
    if source_sentences and compare_sentences:
        # 取出 source 的向量 (假设 source_sentence 只有一个句子)
        source_emb = embeddings[0]
        # 取出 compare 的向量
        compare_embs = embeddings[len(source_sentences):]
        
        # 计算余弦相似度 (Cosine Similarity)
        cos_sim = F.cosine_similarity(source_emb.unsqueeze(0), compare_embs)
        # 将分数转为 list，和 ModelScope 保持一致
        scores = cos_sim.tolist()
        
    result["scores"] = scores
    return result

# 当输入包含“soure_sentence”与“sentences_to_compare”时，会输出source_sentence中首个句子与sentences_to_compare中每个句子的向量表示，以及source_sentence中首个句子与sentences_to_compare中每个句子的相似度。
inputs = {
        "source_sentence": ["吃完海鲜可以喝牛奶吗?"],
        "sentences_to_compare": [
            "不可以，早晨喝牛奶不科学",
            "吃了海鲜后是不能再喝牛奶的，因为牛奶中含得有维生素C，如果海鲜喝牛奶一起服用会对人体造成一定的伤害",
            "吃海鲜是不能同时喝牛奶吃水果，这个至少间隔6小时以上才可以。",
            "吃海鲜是不可以吃柠檬的因为其中的维生素C会和海鲜中的矿物质形成砷"
        ]
    }

result = pipeline_se_mimic(input_dict=inputs)
print (result)
'''
{'text_embedding': array([[ 1.6415151e-04,  2.2334497e-02, -2.4202393e-02, ...,
         2.7710509e-02,  2.5980933e-02, -3.1285528e-02],
       [-9.9107623e-03,  1.3627578e-03, -2.1072682e-02, ...,
         2.6786461e-02,  3.5029035e-03, -1.5877936e-02],
       [ 1.9877627e-03,  2.2191243e-02, -2.7656069e-02, ...,
         2.2540951e-02,  2.1780970e-02, -3.0861111e-02],
       [ 3.8688166e-05,  1.3409532e-02, -2.9691193e-02, ...,
         2.9900728e-02,  2.1570563e-02, -2.0719109e-02],
       [ 1.4484422e-03,  8.5943500e-03, -1.6661938e-02, ...,
         2.0832840e-02,  2.3828523e-02, -1.1581291e-02]], dtype=float32), 'scores': [0.8859604597091675, 0.9830712080001831, 0.966042160987854, 0.891857922077179]}
'''

# 当输入仅含有soure_sentence时，会输出source_sentence中每个句子的向量表示。
inputs2 = {
        "source_sentence": [
            "不可以，早晨喝牛奶不科学",
            "吃了海鲜后是不能再喝牛奶的，因为牛奶中含得有维生素C，如果海鲜喝牛奶一起服用会对人体造成一定的伤害",
            "吃海鲜是不能同时喝牛奶吃水果，这个至少间隔6小时以上才可以。",
            "吃海鲜是不可以吃柠檬的因为其中的维生素C会和海鲜中的矿物质形成砷"
        ]
}
result = pipeline_se_mimic(input_dict=inputs2)
print (result)
'''
{'text_embedding': array([[-9.9107623e-03,  1.3627578e-03, -2.1072682e-02, ...,
         2.6786461e-02,  3.5029035e-03, -1.5877936e-02],
       [ 1.9877627e-03,  2.2191243e-02, -2.7656069e-02, ...,
         2.2540951e-02,  2.1780970e-02, -3.0861111e-02],
       [ 3.8688166e-05,  1.3409532e-02, -2.9691193e-02, ...,
         2.9900728e-02,  2.1570563e-02, -2.0719109e-02],
       [ 1.4484422e-03,  8.5943500e-03, -1.6661938e-02, ...,
         2.0832840e-02,  2.3828523e-02, -1.1581291e-02]], dtype=float32), 'scores': []}
'''

##  ----------------------- text-generator task ------------------------------
gguf_llm_name = "Qwen/Qwen3-GGUF"
logger.info(f"llm: {gguf_llm_name} model set.")
gguf_llm_path = get_huggingface_path(gguf_llm_name)
logger.info(f"Loading {gguf_llm_name} model from: {gguf_llm_path}")









