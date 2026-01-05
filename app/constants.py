from pathlib import Path

root_dir: Path = Path(__file__).parents[1]
# path/to/ChatRAG

# db_dir
chromadb_root: Path = root_dir / "datas/data_db/chromadb"
faissdb_root: Path = root_dir / "datas/data_db/faissdb"
pymilvusdb_root: Path = root_dir / "datas/data_db/pymilvusdb"
