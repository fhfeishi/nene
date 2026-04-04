# app/constants.py

from pathlib import Path

root_dir: Path = Path(__file__).parents[1].resolve()
# path/to/project_root

temp_dir: Path = root_dir / "temp"
temp_dir.mkdir(parents=True, exist_ok=True)

# db_dir
chromadb_root: Path = root_dir / "datas/data_db/chromadb"
milvusdb_root: Path = root_dir / "datas/data_db/milvusdb"
qdrantdb_root: Path = root_dir / "datas/data_db/qdrant_db"
postgreSQLdb_root: Path = root_dir / "datas/data_db/postgreSQL_db"

faissdb_root: Path = root_dir / "datas/data_db/faissdb"        # 仅仅存向量
pymilvusdb_root: Path = root_dir / "datas/data_db/pymilvusdb"  # py-lite 版本不支持windows吧。
chromadb_root.mkdir(parents=True, exist_ok=True)
faissdb_root.mkdir(parents=True, exist_ok=True)
pymilvusdb_root.mkdir(parents=True, exist_ok=True)
milvusdb_root.mkdir(parents=True, exist_ok=True)
qdrantdb_root.mkdir(parents=True, exist_ok=True)
postgreSQLdb_root.mkdir(parents=True, exist_ok=True)


# --没什么用，暂且放这儿 --------------
# local cache model root 
## cli: modelscope/hf download model-xx
MODELSCOPE_ROOT = r"E:\local_models\modelscope\models"
HUGGINGFACE_ROOT = r"E:\local_models\huggingface\cache\hub"
