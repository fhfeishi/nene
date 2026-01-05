# app/components/ingestdb/pymilvus_db.py

from app.constants import root_dir

from pathlib import Path
from pymilvus import MilvusClient
from langchain_core.documents import Document 
from typing import List 

pymilvusdb_dir: Path = root_dir / "datas"/ "data_db"/ "pymilvus_db" 






