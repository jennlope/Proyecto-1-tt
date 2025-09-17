from pydantic import BaseModel
from typing import List, Dict
from typing import Optional

class BlockLocation(BaseModel):
    block_id: str
    datanode: str   # URL base del datanode

class FileMetadata(BaseModel):
    owner: str
    filename: str
    size: int
    hash: Optional[str] = None
    blocks: List[BlockLocation]
    directory_id: int = 1

class AllocateRequest(BaseModel):
    owner: str
    filename: str
    size: int
    block_size: int
    hash: Optional[str] = None

class RegisterDN(BaseModel):
    node_id: str
    base_url: str