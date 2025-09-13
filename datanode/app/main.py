import os, io, requests, time, asyncio
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

# -------------------------------
# Variables de entorno
# -------------------------------
NODE_ID = os.getenv("NODE_ID", "dnX")
NAMENODE = os.getenv("NAMENODE_URL", "http://namenode:8000")
BASE_URL = os.getenv("BASE_URL", f"http://{NODE_ID}:8001")
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "5"))  # seg entre latidos

# -------------------------------
# Inicialización del DataNode
# -------------------------------
api = FastAPI(title=f"GridDFS DataNode {NODE_ID}")
BASE_DIR = "/app/blocks"
os.makedirs(BASE_DIR, exist_ok=True)

# -------------------------------
# Registro inicial en NameNode
# -------------------------------
@api.on_event("startup")
async def startup_event():
    # Intento de registro inicial
    for i in range(10):
        try:
            r = requests.post(
                f"{NAMENODE}/register",
                json={"node_id": NODE_ID, "base_url": BASE_URL},
                timeout=5,
            )
            print(f"[REGISTER] {NODE_ID} -> {r.status_code} {r.text}")
            if r.ok:
                break
        except Exception as e:
            print(f"[REGISTER-ERR] intento {i+1}: {e}")
        time.sleep(2)

    # Arranca loop de heartbeats
    asyncio.create_task(heartbeat_loop())

# -------------------------------
# Heartbeat periódico
# -------------------------------
async def heartbeat_loop():
    while True:
        try:
            requests.post(
                f"{NAMENODE}/heartbeat",
                json={"node_id": NODE_ID, "base_url": BASE_URL, "ts": int(time.time())},
                timeout=5,
            )
            print(f"[HEARTBEAT] {NODE_ID} OK")
        except Exception as e:
            print(f"[HEARTBEAT-ERR] {e}")
        await asyncio.sleep(HEARTBEAT_INTERVAL)

# -------------------------------
# Endpoints de servicio
# -------------------------------
@api.get("/health")
def health():
    return {"node": NODE_ID, "ok": True}

def path_for(block_id: str) -> str:
    return os.path.join(BASE_DIR, block_id.replace("/", "_"))

@api.put("/store/{block_id}")
async def store(block_id: str, part: UploadFile = File(...)):
    """Guardar bloque en disco"""
    with open(path_for(block_id), "wb") as f:
        while True:
            chunk = await part.read(1024 * 1024)  # lee de a 1 MB
            if not chunk:
                break
            f.write(chunk)
    return {"ok": True, "block": block_id}

@api.get("/read/{block_id}")
def read(block_id: str):
    """Devolver bloque en streaming"""
    p = path_for(block_id)
    if not os.path.exists(p):
        raise HTTPException(404, "missing block")
    return StreamingResponse(open(p, "rb"), media_type="application/octet-stream")

@api.delete("/delete/{block_id}")
def delete(block_id: str):
    """Borrar bloque del disco"""
    p = path_for(block_id)
    if os.path.exists(p):
        os.remove(p)
    return {"ok": True}
