import os, aiosqlite, secrets, time
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from typing import List, Dict
from models import FileMetadata, BlockLocation, AllocateRequest, RegisterDN

api = FastAPI(title="GridDFS NameNode")

USERS = dict(u.split(":") for u in os.getenv("USERS","alice:alicepwd").split(","))
BLOCK_SIZE = int(os.getenv("BLOCK_SIZE", 64*1024*1024))

security = HTTPBasic()

DN_REGISTRY: Dict[str, str] = {}  # node_id -> base_url
RR_STATE = 0

async def init_db():
    async with aiosqlite.connect("/app/data/storage.db") as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS files(
            owner TEXT, filename TEXT, size INTEGER, metadata TEXT,
            PRIMARY KEY(owner, filename))""")
        await db.commit()

@api.on_event("startup")
async def startup():
    os.makedirs("/app/data", exist_ok=True)
    await init_db()

def auth(credentials: HTTPBasicCredentials = Depends(security)):
    user = credentials.username
    if USERS.get(user) != credentials.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user

@api.post("/register", tags=["datanodes"])
def register_dn(req: RegisterDN):
    DN_REGISTRY[req.node_id] = req.base_url.rstrip("/")
    return {"ok": True, "nodes": DN_REGISTRY}

@api.get("/datanodes", tags=["datanodes"])
def list_dns():
    return DN_REGISTRY

def pick_nodes(n_blocks: int) -> List[str]:
    global RR_STATE
    nodes = list(DN_REGISTRY.values())
    if not nodes:
        raise HTTPException(503, "No DataNodes registered")
    result = []
    for i in range(n_blocks):
        result.append(nodes[(RR_STATE + i) % len(nodes)])
    RR_STATE = (RR_STATE + n_blocks) % len(nodes)
    return result

@api.post("/allocate", response_model=FileMetadata, tags=["files"])
async def allocate(req: AllocateRequest, user: str = Depends(auth)):
    if user != req.owner:
        raise HTTPException(403, "Owner mismatch")
    n_blocks = (req.size + req.block_size - 1)//req.block_size
    nodes = pick_nodes(n_blocks)
    blocks = [BlockLocation(block_id=f"{req.owner}:{req.filename}:{i}", datanode=nodes[i])
              for i in range(n_blocks)]
    meta = FileMetadata(owner=req.owner, filename=req.filename, size=req.size, blocks=blocks)
    return meta

@api.post("/commit", tags=["files"])
async def commit(meta: FileMetadata, user: str = Depends(auth)):
    async with aiosqlite.connect("/app/data/storage.db") as db:
        await db.execute("REPLACE INTO files(owner,filename,size,metadata) VALUES(?,?,?,?)",
                         (meta.owner, meta.filename, meta.size, meta.json()))
        await db.commit()
    return {"ok": True}

@api.get("/meta/{owner}/{filename}", response_model=FileMetadata, tags=["files"])
async def get_meta(owner: str, filename: str, user: str = Depends(auth)):
    async with aiosqlite.connect("/app/data/storage.db") as db:
        async with db.execute("SELECT metadata FROM files WHERE owner=? AND filename=?",
                              (owner, filename)) as cur:
            row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return FileMetadata.model_validate_json(row[0])

@api.get("/ls", tags=["files"])
async def ls(user: str = Depends(auth)):
    async with aiosqlite.connect("/app/data/storage.db") as db:
        async with db.execute("SELECT filename,size FROM files WHERE owner=?", (user,)) as cur:
            rows = await cur.fetchall()
    return [{"filename": r[0], "size": r[1]} for r in rows]

@api.delete("/rm/{filename}", tags=["files"])
async def rm(filename: str, user: str = Depends(auth)):
    # borrado lógico en metadatos; el cliente pedirá a los DN eliminar bloques
    async with aiosqlite.connect("/app/data/storage.db") as db:
        await db.execute("DELETE FROM files WHERE owner=? AND filename=?", (user, filename))
        await db.commit()
    return {"ok": True}
