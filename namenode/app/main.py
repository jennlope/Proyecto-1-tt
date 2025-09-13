import os, aiosqlite, time
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from typing import List, Dict, Any
from models import FileMetadata, BlockLocation, AllocateRequest, RegisterDN

api = FastAPI(title="GridDFS NameNode")

# -------------------------
# Config
# -------------------------
USERS = dict(u.split(":") for u in os.getenv("USERS", "alice:alicepwd").split(","))
BLOCK_SIZE = int(os.getenv("BLOCK_SIZE", 50 * 1024))
DOWN_THRESHOLD = int(os.getenv("DOWN_THRESHOLD", "15"))  # seg sin heartbeat => DOWN

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
        await db.execute(
            """CREATE TABLE IF NOT EXISTS files(
                owner TEXT,
                filename TEXT,
                size INTEGER,
                metadata TEXT,
                PRIMARY KEY(owner, filename)
            )"""
        )
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
    return meta

@api.post("/commit", tags=["files"])
async def commit(meta: FileMetadata, user: str = Depends(auth)):
    async with aiosqlite.connect("/app/data/storage.db") as db:
        await db.execute(
            "REPLACE INTO files(owner,filename,size,metadata) VALUES(?,?,?,?)",
            (meta.owner, meta.filename, meta.size, meta.json()),
        )
        await db.commit()
    return {"ok": True}

@api.get("/meta/{owner}/{filename}", response_model=FileMetadata, tags=["files"])
async def get_meta(owner: str, filename: str, user: str = Depends(auth)):
    async with aiosqlite.connect("/app/data/storage.db") as db:
        async with db.execute(
            "SELECT metadata FROM files WHERE owner=? AND filename=?",
            (owner, filename),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    # Nota: devolvemos FileMetadata tal cual (sin node_status extra)
    # para no romper el response_model. El dashboard puede consultar /datanodes
    # para pintar el estado o puedes crear /meta_ext si quieres enriquecer.
    return FileMetadata.model_validate_json(row[0])

@api.get("/ls", tags=["files"])
async def ls(user: str = Depends(auth)):
    async with aiosqlite.connect("/app/data/storage.db") as db:
        async with db.execute(
            "SELECT filename,size FROM files WHERE owner=?",
            (user,),
        ) as cur:
            rows = await cur.fetchall()
    return [{"filename": r[0], "size": r[1]} for r in rows]

@api.delete("/rm/{filename}", tags=["files"])
async def rm(filename: str, user: str = Depends(auth)):
    # borrado lógico en metadatos; el cliente puede ordenar limpieza a los DN
    async with aiosqlite.connect("/app/data/storage.db") as db:
        await db.execute(
            "DELETE FROM files WHERE owner=? AND filename=?",
            (user, filename),
        )
        await db.commit()
    return {"ok": True}
