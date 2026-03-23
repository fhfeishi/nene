# settings 

from pydantic import BaseModel

class EmbeddingConfig(BaseModel):
    model_name: str
    model_path: str
    model_type: str
    model_params: dict


class EmbeddingModel(BaseModel):
    model_name: str
    model_path: str
    model_type: str
    model_params: dict

