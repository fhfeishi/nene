# app/notebookdoc/doc_pieces.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum
import uuid 
import hashlib


# ===========================================================
# 情况1：纯文本知识库分块TextChunk
# ===========================================================
""" 关于如何设计TextChunks的一些思考
# 需要注意：
#   - TextChunk必须包含绝对有效、绝对有用的词条
#   - 提升效率方面：关键词摘要 + 正文，检索和生成解耦，检索关键词摘要、参考正文进行生成  ⭐这个方案是否可行⭐
#   - 记录TextChunk在原文中的结构： ChunkIndex_ChunkID 
#   - 适当强化一下边缘信息（因为无法避免的边缘信息碎片化）：⭐这个问题还不知如何解决⭐
#   - 向量数据库有多种，如何适配。如chromadb, milvus, faissdb, qdrant, postgresql
#   - ⭐知识库整理成多个QA的形式作为补充信息，这是否是必要的呢⭐
#   - ⭐多个正文source_file.txt，以及 QA_collections.txt，算是异构的数据吧，要如何一起处理呢。
#     因为QA_collections.txt应该只需要分块就行，而不需要整理摘要这些东西



"""

class ChunkType(str, Enum):
    RAW_TEXT = "raw_text"   # 普通的正文切片
    QA_PAIR = "qa_pair"     # 预生成的QA对

@dataclass
class TextChunk:
    """
    统一知识分块模型：适配正文切片与QA对
    设计目标：检索时用精简信息（低延迟），生成时用丰富上下文
    """
    # === 基础标识 ===
    chunk_id: str                   # 全局唯一ID
    source_file: str                # 来源文件名
    chunk_type: ChunkType           # 类型：正文还是QA
    
    # === 核心内容 (生成用) ===
    content: str                    # 给LLM看的：正文片段 OR Answer部分
    
    # === 检索增强 (向量化用) ===
    # 对于QA对，这里放Question；对于正文，这里放“摘要+关键词+标题”
    search_text: str                
    
    # === 上下文关联 (解决边缘信息丢失) ===  只是一个简单的尝试、
    # 记录前后文ID，检索到当前块时，可顺藤摸瓜获取完整语境
    pre_chunk_id: Optional[str] = None
    next_chunk_id: Optional[str] = None
    
    # === 元数据 (过滤用) ===
    title: str = "未知标题"
    metadata: Dict[str, Any] = field(default_factory=dict) # 弹性扩展：放作者、年份、关键词列表等
    create_time: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    @staticmethod
    def generate_id(source_str: str, index: int) -> str:
        """生成确定性ID，方便幂等处理"""
        prefix = hashlib.md5(source_str.encode()).hexdigest()[:8]
        return f"{prefix}_{str(index).zfill(4)}"

    def to_vector_store_payload(self) -> dict:
        """
        转换为写入向量库的Payload (适配 Chroma/Milvus)
        注意：Milvus不支持嵌套Dict，通常需要扁平化处理
        """
        return {
            "chunk_id": self.chunk_id,
            "source_file": self.source_file,
            "chunk_type": self.chunk_type.value,
            "content": self.content, # 原始内容存入Payload，检索后直接取出，无需回查数据库
            "pre_id": self.pre_chunk_id or "",
            "next_id": self.next_chunk_id or "",
            "title": self.title,
            # 将metadata扁平化展开，方便做 filter
            **self.metadata 
        }

    def get_embedding_content(self) -> str:
        """
        核心逻辑：决定什么内容被向量化
        """
        if self.chunk_type == ChunkType.QA_PAIR:
            # QA对的精髓：只Embedding问题（Q），或者 Q + A摘要
            # 这样用户问类似问题时，匹配度极高
            return f"{self.search_text}" 
        else:
            # 正文：标题 + 摘要 + 核心内容（截断）
            return f"主题：{self.title}\n内容：{self.search_text}"
        
        
        
## 后续可以参考看看。
# # 附上权重、更加鲁棒的版本   --不够实用、不够好用
# class KnowledgeDomainEnum(str, Enum):
#     """
#     知识领域枚举（宏观分类，适配多向量库的分类过滤）
#     可根据湖北文化场景扩展,
#     人为设置
#     """
#     JING_CHU_CULTURE = "荆楚文化"          # 核心领域
#     MUSEUM_ARTIFACT = "博物馆与文物"       # 博物馆相关
#     FOLK_CUSTOM = "民俗风情"              # 湖北民俗
#     HISTORICAL_EVENT = "历史事件"          # 湖北历史
#     GEOGRAPHICAL_CULTURE = "地域文化"      # 各地市文化
#     NON_MATERIAL_HERITAGE = "非物质文化遗产" # 非遗相关
#     OTHERS = "其他文化信息"                # 兜底分类
# class KnowledgePriorityEnum(int, Enum):
#     """
#     检索优先级枚举（适配qdrant/milvus的排序召回）
#     确保核心知识优先被召回
#     """
#     HIGH = 5       # 核心知识（必召回）
#     MEDIUM_HIGH = 4 # 重要知识
#     MEDIUM = 3     # 常规知识
#     MEDIUM_LOW = 2  # 次要知识
#     LOW = 1        # 补充知识
# @dataclass
# class HubeiCulturalKnowledge:
#     """
#     湖北文化知识片段结构化定义（适配chromadb/pymilvus/qdrant/postgresql等多向量数据库）
#     字段设计原则：
#     1. 兼容性：字段类型为通用类型（str/int/bool/list/datetime），适配所有向量库元数据存储
#     2. 实用性：关键词分层设计，强化检索相关性；补充优先级/有效性等字段，支持精准召回
#     3. 可管理性：覆盖知识片段全生命周期（创建/更新/软删除/溯源）
#     """
#     # 1. 唯一标识（跨库唯一，建议采用「业务前缀-日期-自增ID」格式，避免冲突）
#     # 适配：所有向量库的主键/唯一索引字段
#     knowledge_id: str

#     # 2. 知识领域（宏观分类，枚举类型保证一致性，适配多库分类过滤）
#     # 适配：milvus的分区键、chromadb的元数据过滤、postgresql的枚举字段
#     domain: KnowledgeDomainEnum

#     # 3. 内容类型（细分类型，比domain更具体，辅助精准过滤）
#     # 示例：博物馆简介、镇馆之宝、藏品出借规则、楚剧唱腔、武当武术等
#     # 适配：所有向量库的元数据过滤字段
#     content_type: str

#     # 4. 核心内容（知识主体，预处理后文本，确保信息完整无冗余）
#     # 要求：单片段字符数控制在500-2000字（适配Qwen3-embedding-0.6B上下文窗口）
#     # 适配：所有向量库的文本存储字段（对应embedding编码源）
#     core_content: str

#     # 5. 来源信息（完整溯源，便于更新/校验/审计）
#     # 5.1 源文件名称
#     source_file: str
#     # 5.2 源文件完整路径（批量处理时精准溯源，适配多目录场景）
#     source_file_path: str
#     # 5.3 片段在源文件中的位置索引（大文件拆分时的片段编号，适配批量处理）
#     source_chunk_index: int

#     # 6. 分层关键词（核心优化：提升检索精准度，适配多库关键词过滤/权重排序）
#     # 6.1 核心实体关键词（必填，聚焦业务核心实体，如“曾侯乙编钟”“越王勾践剑”）
#     # 作用：用于精准匹配检索，提升召回命中率
#     core_entity_keywords: List[str]
#     # 6.2 属性描述关键词（可选，补充实体特征/属性，如“战国早期”“天下第一剑”）
#     # 作用：用于模糊检索/属性过滤，丰富召回维度
#     attribute_keywords: List[str]
#     # 6.3 关键词权重（可选，适配milvus/qdrant的权重排序，提升核心关键词优先级）
#     # 格式：[(关键词, 权重值(1-10)), ...]，权重越高，检索优先级越高
#     keyword_weights: List[Tuple[str, int]] = field(default_factory=list)

#     # 7. 检索优先级（枚举类型，适配qdrant/milvus的排序召回，确保核心知识优先返回）
#     # 适配：qdrant的payload排序、milvus的自定义排序、postgresql的排序字段
#     priority: KnowledgePriorityEnum = KnowledgePriorityEnum.MEDIUM

#     # 8. 版本与状态管理（全生命周期管控，适配多库的版本追溯/软删除）
#     # 8.1 创建时间（首次入库时间，不可修改）
#     create_time: datetime = field(default_factory=datetime.now)
#     # 8.2 更新时间（知识片段更新时间，用于版本追溯）
#     update_time: datetime = field(default_factory=datetime.now)
#     # 8.3 是否有效（软删除标识，避免直接删除向量导致索引重建，适配所有向量库）
#     is_valid: bool = True
#     # 8.4 嵌入模型标识（记录生成向量的模型，避免不同模型向量混用，适配多模型场景）
#     embedding_model: str = "Qwen/Qwen3-embedding-0.6B"

#     # 9. 补充元数据（可选，用于扩展场景，如文本长度、审核状态等）
#     # 适配：所有向量库的自定义元数据字段
#     extra_metadata: Optional[dict] = field(default_factory=dict)

#     def to_text(self, with_weight: bool = False) -> str:
#         """
#         转换为embedding编码文本（优化版：支持权重显式注入，提升检索相关性）
#         适配Qwen3-embedding-0.6B及其他主流embedding模型
#         :param with_weight: 是否在文本中注入关键词权重（强化核心关键词语义）
#         :return: 可直接编码的文本字符串
#         """
#         # 基础文本拼接
#         text_parts = [
#             f"知识领域：{self.domain.value}",
#             f"内容类型：{self.content_type}",
#             f"核心实体：{','.join(self.core_entity_keywords)}"
#         ]

#         # 可选：注入属性关键词
#         if self.attribute_keywords:
#             text_parts.append(f"属性描述：{','.join(self.attribute_keywords)}")

#         # 可选：注入关键词权重（强化核心关键词的语义表征）
#         if with_weight and self.keyword_weights:
#             weight_str = ",".join([f"{kw[0]}({kw[1]}级)" for kw in self.keyword_weights])
#             text_parts.append(f"核心关键词权重：{weight_str}")

#         # 拼接核心内容
#         text_parts.append(f"知识详情：{self.core_content}")

#         return "\n".join(text_parts)

#     def to_metadata_dict(self) -> dict:
#         """
#         转换为向量库元数据字典（适配所有向量库的元数据存储/过滤/排序）
#         自动处理枚举类型、datetime类型的序列化，避免跨库兼容性问题
#         """
#         return {
#             "knowledge_id": self.knowledge_id,
#             "domain": self.domain.value,
#             "content_type": self.content_type,
#             "source_file": self.source_file,
#             "source_file_path": self.source_file_path,
#             "source_chunk_index": self.source_chunk_index,
#             "core_entity_keywords": ",".join(self.core_entity_keywords),  # 列表转字符串，适配部分库的元数据限制
#             "attribute_keywords": ",".join(self.attribute_keywords),
#             "keyword_weights": str(self.keyword_weights),  # 元组列表转字符串，便于存储
#             "priority": self.priority.value,
#             "create_time": self.create_time.strftime("%Y-%m-%d %H:%M:%S"),
#             "update_time": self.update_time.strftime("%Y-%m-%d %H:%M:%S"),
#             "is_valid": self.is_valid,
#             "embedding_model": self.embedding_model,
#             "extra_metadata": str(self.extra_metadata) if self.extra_metadata else "{}"
#         }






