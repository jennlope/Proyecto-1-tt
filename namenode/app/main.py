import os, aiosqlite, secrets, time
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from typing import List, Dict
from models import FileMetadata, BlockLocation, AllocateRequest, RegisterDN

# os → manejar rutas/carpetas
# aiosqlite → BD SQLite asíncrona
# HTTPBasic → Autenticación básica (usuario/contraseña)
# typing → tipado

api = FastAPI(title="GridDFS NameNode")

USERS = dict(u.split(":") for u in os.getenv("USERS","alice:alicepwd").split(","))
BLOCK_SIZE = int(os.getenv("BLOCK_SIZE", 50*1024)) # tamaño del bloque por defecto 50 KB

security = HTTPBasic()

DN_REGISTRY: Dict[str, str] = {}  # node_id -> base_url
RR_STATE = 0

async def init_db():
    async with aiosqlite.connect("/app/data/storage.db") as db:
        # Nuevo
        await db.execute("""
        CREATE TABLE IF NOT EXISTS directories(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner TEXT NOT NULL,
            name TEXT NOT NULL,
            parent_id INTEGER,
            FOREIGN KEY(parent_id) REFERENCES directories(id)
        )
        """)
        # Modificado
        await db.execute("""
        CREATE TABLE IF NOT EXISTS files(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner TEXT NOT NULL,
            filename TEXT NOT NULL,
            size INTEGER,
            hash TEXT,
            metadata TEXT,
            directory_id INTEGER,
            FOREIGN KEY(directory_id) REFERENCES directories(id)
        )
        """)
        await db.commit()

@api.on_event("startup")
async def startup():
    os.makedirs("/app/data", exist_ok=True)
    await init_db()

    # Nuevo
    async with aiosqlite.connect("/app/data/storage.db") as db:
        async with db.execute("SELECT id FROM directories WHERE parent_id IS NULL") as root:
            row = await root.fetchone()
        if not row:
            await db.execute("INSERT INTO directories(owner, name, parent_id) VALUES(?,?,?)", ("root", "/", None))
            await db.commit()



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

    meta = FileMetadata(
        owner = req.owner,
        filename = req.filename,
        size = req.size,
        blocks = blocks,
        hash = req.hash
    )
    return meta

@api.post("/commit", tags=["files"])
async def commit(meta: FileMetadata, user: str = Depends(auth)):
    if not meta.hash:
        raise HTTPException(400, "Missing file hash")

    async with aiosqlite.connect("/app/data/storage.db") as db:
        await db.execute("""
        REPLACE INTO files(owner, filename, size, hash, metadata, directory_id) VALUES(?,?,?,?,?,?)""", (meta.owner, meta.filename, meta.size, meta.hash, meta.json(), meta.directory_id))
        await db.commit()
    return {"status": "commit"}

@api.get("/meta/{file_id}", tags=["files"])
async def get_meta(file_id: int, user: str = Depends(auth)):
    async with aiosqlite.connect("/app/data/storage.db") as db:
        async with db.execute("SELECT metadata, owner FROM files WHERE id=?", (file_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    
    metadata, owner = row

    if owner != user and owner != "root":
        raise HTTPException(status_code = 403, detail = "Acceso denegado")

    return FileMetadata.model_validate_json(metadata)

# Modificado
@api.get("/ls/{directory_id}", tags=["directories"])
async def ls(directory_id: int, user: str = Depends(auth)):
    async with aiosqlite.connect("/app/data/storage.db") as db:
        async with db.execute("SELECT id, name FROM directories WHERE parent_id=? AND owner=?", (directory_id, user)) as cur:
            dirs = await cur.fetchall()
        async with db.execute("SELECT id, filename, size FROM files WHERE directory_id=? AND owner=?", (directory_id, user)) as cur:
            files = await cur.fetchall()
    return {
        "directories": [{"id": d[0], "name": d[1]} for d in dirs],
        "files": [{"id": f[0], "filename": f[1], "size": f[2]} for f in files]
    }

@api.delete("/rm/{file_id}", tags=["files"])
async def rm(file_id: int, user: str = Depends(auth)):
    async with aiosqlite.connect("/app/data/storage.db") as db:
        async with db.execute("SELECT owner FROM files WHERE id=?", (file_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Archivo no encontrado")
        owner, = row
        if owner != user and owner != "root":
            raise HTTPException(403, "Acceso denegado")

        await db.execute("DELETE FROM files WHERE id=?", (file_id,))
        await db.commit()

    return {"status": "deleted"}

# Nuevo
@api.post("/mkdir/{parent_id}/{dirname}", tags=["directories"])
async def mkdir(parent_id: int, dirname: str, user: str = Depends(auth)):
    print("######")
    print(parent_id)
    print(dirname)
    print(user)
    async with aiosqlite.connect("/app/data/storage.db") as db:
        async with db.execute("SELECT id FROM directories WHERE id=?", (parent_id,)) as cur:
            parent = await cur.fetchone()
        if not parent:
            raise HTTPException(404, "Parent directory not found")
        await db.execute("INSERT INTO directories(owner, name, parent_id) VALUES(?,?,?)", (user, dirname, parent_id))
        await db.commit()
    return {"status": "created", "dirname": dirname}

# Nuevo
@api.delete("/rmdir/{directory_id}", tags=["directories"])
async def rmdir(directory_id: int, user: str = Depends(auth)):
    async with aiosqlite.connect("/app/data/storage.db") as db:
        async with db.execute("SELECT 1 FROM directories WHERE parent_id=?", (directory_id,)) as cur:
            if await cur.fetchone():
                raise HTTPException(400, "Directory no empty")
        async with db.execute("SELECT 1 FROM files WHERE directory_id=?", (directory_id,)) as cur:
            if await cur.fetchone():
                raise HTTPException(400, "Directory no empty")
        await db.execute("DELETE FROM directories WHERE id=? AND owner=?", (directory_id, user))
        await db.commit()
    return {"status": "deleted", "id": directory_id}

# Nuevo
@api.get("/directories", tags=["directories"])
async def get_all_directories(user: str = Depends(auth)):
    async with aiosqlite.connect("/app/data/storage.db") as db:
        async with db.execute("SELECT id, name FROM directories WHERE owner=? OR owner='root'", (user,)) as cur:
            directories = await cur.fetchall()
    dir = [{"id": d[0], "name": d[1]} for d in directories]
    print("##################")
    print("main.py")
    print(dir)
    return dir