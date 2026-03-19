# settings 

from dataclasses import dataclass

@dataclass
class EmbeddingConfig:
    model_name: str
    model_path: str
    model_type: str
    model_params: dict

@dataclass
class EmbeddingModel:
    model_name: str
    model_path: str
    model_type: str
    model_params: dict

