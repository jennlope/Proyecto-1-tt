import os, aiosqlite, time
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from typing import List, Dict, Any
from models import FileMetadata, BlockLocation, AllocateRequest, RegisterDN

# os → manejar rutas/carpetas
# aiosqlite → BD SQLite asíncrona
# HTTPBasic → Autenticación básica (usuario/contraseña)
# typing → tipado

api = FastAPI(title="GridDFS NameNode")

USERS = dict(u.split(":") for u in os.getenv("USERS","alice:alicepwd").split(","))
BLOCK_SIZE = int(os.getenv("BLOCK_SIZE", 50*1024))
DOWN_THRESHOLD = int(os.getenv("DOWN_THRESHOLD", "15"))

security = HTTPBasic()

# -------------------------
# Estado de DataNodes
# DATANODES: node_id -> {"base_url": str, "last_seen": int}
# -------------------------
DATANODES: Dict[str, Dict[str, Any]] = {}
RR_STATE = 0  # round-robin

# -------------------------
# DB init
# -------------------------
async def init_db():
    async with aiosqlite.connect("/app/data/storage.db") as db:
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
#alertas
class AlertReq(BaseModel):
    user: str
    filename: str
    down_nodes: List[str]        # puede ser lista de node_id o base_url
    missing_blocks: List[str]    # ej. ["alice:demo.txt:0", ...]
    reason: str = "download_failed_due_to_down_nodes"
    ts: int = int(time.time())

ALERTS: List[AlertReq] = []

@api.post("/alerts", tags=["alerts"])
def post_alert(alert: AlertReq):
    """
    Registra una alerta cuando falla la reconstrucción (nodos caídos o bloques ausentes).
    No requiere auth para simplificar la demo; añade Depends(auth) si quieres protegerlo.
    """
    ALERTS.append(alert)
    print(f"[ALERT] {alert.ts} {alert.user}:{alert.filename} "
          f"DOWN={alert.down_nodes} MISSING={alert.missing_blocks} REASON={alert.reason}")
    return {"ok": True}

@api.get("/alerts", tags=["alerts"])
def list_alerts():
    """Lista las alertas acumuladas en memoria."""
    return [a.dict() for a in ALERTS]
# -------------------------
# Auth
# -------------------------
def auth(credentials: HTTPBasicCredentials = Depends(security)):
    user = credentials.username
    if USERS.get(user) != credentials.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user

# -------------------------
# Modelos para heartbeat/alertas (locales a este archivo)
# -------------------------
class HeartbeatReq(BaseModel):
    node_id: str
    base_url: str
    ts: int

# -------------------------
# Datanodes: registro + heartbeat + listado con estado
# -------------------------
@api.post("/register", tags=["datanodes"])
def register_dn(req: RegisterDN):
    """Registro inicial de un DataNode."""
    DATANODES[req.node_id] = {
        "base_url": req.base_url.rstrip("/"),
        "last_seen": int(time.time()),
    }
    return {"ok": True, "nodes": DATANODES}

@api.post("/heartbeat", tags=["datanodes"])
def heartbeat(req: HeartbeatReq):
    """Actualización periódica de liveness del DataNode."""
    DATANODES[req.node_id] = {
        "base_url": req.base_url.rstrip("/"),
        "last_seen": req.ts,
    }
    return {"ok": True}

@api.get("/datanodes", tags=["datanodes"])
def list_dns():
    """Lista nodos con estado UP/DOWN según last_seen y DOWN_THRESHOLD."""
    now = int(time.time())
    out = {}
    for nid, info in DATANODES.items():
        last = info.get("last_seen", 0)
        status = "UP" if (now - last) < DOWN_THRESHOLD else "DOWN"
        out[nid] = {
            "base_url": info["base_url"],
            "last_seen": last,
            "status": status,
        }
    return out

def _up_base_urls() -> List[str]:
    """Devuelve base_urls de nodos UP (según DOWN_THRESHOLD)."""
    now = int(time.time())
    return [
        info["base_url"]
        for info in DATANODES.values()
        if (now - info.get("last_seen", 0)) < DOWN_THRESHOLD
    ]

# -------------------------
# Asignación de bloques (preferir nodos UP)
# -------------------------
def pick_nodes(n_blocks: int) -> List[str]:
    global RR_STATE
    nodes_up = _up_base_urls()
    nodes = nodes_up if nodes_up else [info["base_url"] for info in DATANODES.values()]
    if not nodes:
        raise HTTPException(503, "No DataNodes registered")

    # Si no hay UP pero sí registrados, permitimos continuar (degradado),
    # pero idealmente el cliente fallará al subir; lo dejamos a decisión.
    result = []
    for i in range(n_blocks):
        result.append(nodes[(RR_STATE + i) % len(nodes)])
    RR_STATE = (RR_STATE + n_blocks) % len(nodes)
    return result

# -------------------------
# Endpoints de archivos
# -------------------------
@api.post("/allocate", response_model=FileMetadata, tags=["files"])
async def allocate(req: AllocateRequest, user: str = Depends(auth)):
    if user != req.owner:
        raise HTTPException(403, "Owner mismatch")
    # tamaño y número de bloques
    block_size = req.block_size or BLOCK_SIZE
    n_blocks = (req.size + block_size - 1) // block_size

    nodes = pick_nodes(n_blocks)
    blocks = [
        BlockLocation(
            block_id=f"{req.owner}:{req.filename}:{i}",
            datanode=nodes[i],
        )
        for i in range(n_blocks)
    ]
    meta = FileMetadata(owner=req.owner, filename=req.filename, size=req.size, blocks=blocks)
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
    import json
    async with aiosqlite.connect("/app/data/storage.db") as db:
        async with db.execute("SELECT metadata, owner FROM files WHERE id=?", (file_id,)) as cur:
            row = await cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Not found")

    metadata_raw, owner = row

    if owner != user and owner != "root":
        raise HTTPException(status_code=403, detail="Acceso denegado")

    # Normalizar metadata: si es string JSON, parsear; si ya es dict, usarlo.
    try:
        if isinstance(metadata_raw, str):
            metadata = json.loads(metadata_raw)
        else:
            metadata = metadata_raw
    except Exception:
        raise HTTPException(status_code=500, detail="Invalid metadata stored")

    # Si por alguna razón la metadata no tiene 'blocks', intenta transformar o fallar claro
    if "blocks" not in metadata:
        # opción: devolver un error informativo para que el cliente lo sepa
        raise HTTPException(status_code=500, detail="Metadata stored is missing 'blocks'")

    return metadata

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