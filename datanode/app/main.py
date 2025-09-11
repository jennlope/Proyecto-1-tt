import os, io, requests, time
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

NODE_ID = os.getenv("NODE_ID", "dnX")
NAMENODE = os.getenv("NAMENODE_URL", "http://namenode:8000")
BASE_URL = os.getenv("BASE_URL", f"http://{NODE_ID}:8001")

api = FastAPI(title=f"GridDFS DataNode {NODE_ID}")
BASE_DIR = "/app/blocks"
os.makedirs(BASE_DIR, exist_ok=True)

@api.on_event("startup")
def register():
    for i in range(10):
        try:
            r = requests.post(f"{NAMENODE}/register",
                              json={"node_id": NODE_ID, "base_url": BASE_URL},
                              timeout=5)
            print(f"[REGISTER] {NODE_ID} -> {r.status_code} {r.text}")
            if r.ok: break
        except Exception as e:
            print(f"[REGISTER-ERR] intento {i+1}: {e}")
        time.sleep(2)

@api.get("/health")
def health():
    return {"node": NODE_ID, "ok": True}

def path_for(block_id: str) -> str:
    return os.path.join(BASE_DIR, block_id.replace("/", "_"))

@api.put("/store/{block_id}")
async def store(block_id: str, part: UploadFile = File(...)):
    with open(path_for(block_id), "wb") as f:
        while True:
            chunk = await part.read(1024*1024)
            if not chunk: break
            f.write(chunk)
    return {"ok": True, "block": block_id}

@api.get("/read/{block_id}")
def read(block_id: str):
    p = path_for(block_id)
    if not os.path.exists(p): raise HTTPException(404, "missing block")
    return StreamingResponse(open(p, "rb"), media_type="application/octet-stream")

@api.delete("/delete/{block_id}")
def delete(block_id: str):
    p = path_for(block_id)
    if os.path.exists(p): os.remove(p)
    return {"ok": True}
