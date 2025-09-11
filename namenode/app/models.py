from pydantic import BaseModel
from typing import List, Dict

class BlockLocation(BaseModel):
    block_id: str
    datanode: str   # URL base del datanode

class FileMetadata(BaseModel):
    owner: str
    filename: str
    size: int
    blocks: List[BlockLocation]

class AllocateRequest(BaseModel):
    owner: str
    filename: str
    size: int
    block_size: int

class RegisterDN(BaseModel):
    node_id: str
    base_url: str
