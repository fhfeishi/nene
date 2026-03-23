from pathlib import Path

root_dir: Path = Path(__file__).parents[1]
# path/to/project_root

# db_dir
chromadb_root: Path = root_dir / "datas/data_db/chromadb"
faissdb_root: Path = root_dir / "datas/data_db/faissdb"        # 仅仅存向量
pymilvusdb_root: Path = root_dir / "datas/data_db/pymilvusdb"  # py-lite 版本不支持windows吧。
milvusdb_root: Path = root_dir / "datas/data_db/milvusdb"
qdrantdb_root: Path = root_dir / "datas/data_db/qdrant_db"
postgreSQLdb_root: Path = root_dir / "datas/data_db/postgreSQL_db"

# local cache model root 
## cli: modelscope/hf download model-xx
MODELSCOPE_ROOT = r"E:\local_models\modelscope\models"
HUGGINGFACE_ROOT = r"E:\local_models\huggingface\cache\hub"



