from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, StreamingResponse
import requests, os, mimetypes
from typing import List, Set

NAMENODE = os.getenv("NAMENODE_URL", "http://localhost:8000")
USER = os.getenv("DFS_USER", "alice")
PASS = os.getenv("DFS_PASS", "alicepwd")

app = FastAPI(title="GridDFS Dashboard")
templates = Jinja2Templates(directory="templates")

def to_host_docker_internal(url: str) -> str:
    # El contenedor dashboard accede a los DN que se registran como http://localhost:8xxx
    return url.replace("http://localhost", "http://host.docker.internal")

def ls_files():
    try:
        r = requests.get(f"{NAMENODE}/ls", auth=(USER, PASS), timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []

def get_meta(filename: str):
    r = requests.get(f"{NAMENODE}/meta/{USER}/{filename}", auth=(USER, PASS), timeout=5)
    if r.status_code != 200:
        raise HTTPException(r.status_code, f"meta not found for {filename}")
    return r.json()

def get_datanodes():
    try:
        r = requests.get(f"{NAMENODE}/datanodes", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}

def post_alert(filename: str, missing_blocks: List[str], missing_dns: List[str]):
    # Enriquecer down_nodes con IDs si el NameNode los reporta
    down_ids: Set[str] = set()
    try:
        dnmap = get_datanodes()  # {"dn1": {"base_url": "...", "status": "UP/DOWN"}, ...}
        base_to_id = {v["base_url"]: k for k, v in dnmap.items()}
        for base in missing_dns:
            nid = base_to_id.get(base)
            if nid:
                # si no sabemos el status exacto, igual lo reportamos
                down_ids.add(nid)
    except Exception:
        pass

    payload = {
        "user": USER,
        "filename": filename,
        "down_nodes": list(down_ids) if down_ids else missing_dns,
        "missing_blocks": missing_blocks,
        "reason": "download_failed_due_to_down_nodes",
    }
    try:
        requests.post(f"{NAMENODE}/alerts", json=payload, timeout=5)
    except Exception:
        pass

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    files = ls_files()
    return templates.TemplateResponse("index.html", {"request": request, "files": files})

@app.get("/file/{filename}", response_class=HTMLResponse)
def file_detail(request: Request, filename: str):
    meta = get_meta(filename)
    nodes = get_datanodes()
    blocks = meta.get("blocks", [])
    return templates.TemplateResponse("file.html", {
        "request": request,
        "meta": meta,
        "blocks": blocks,
        "nodes": nodes,
        "user": USER,
    })

@app.get("/block/{filename}/{index}")
def download_block(filename: str, index: int):
    """
    Descarga un bloque específico desde su DataNode.
    Se nombra <nombre>.block<idx><ext> (es un fragmento binario).
    """
    meta = get_meta(filename)
    blocks = meta.get("blocks", [])
    if index < 0 or index >= len(blocks):
        raise HTTPException(404, "block index out of range")
    b = blocks[index]
    block_id = b.get("block_id")
    dn = b.get("datanode")
    if not block_id or not dn:
        raise HTTPException(500, "invalid meta for block")

    stem, ext = os.path.splitext(filename)
    download_name = f"{stem}.block{index}{ext or ''}"

    def stream():
        dn_url = to_host_docker_internal(dn)
        with requests.get(f"{dn_url}/read/{block_id}", stream=True, timeout=10) as r:
            r.raise_for_status()
            for chunk in r.iter_content(64 * 1024):
                if chunk:
                    yield chunk

    headers = {"Content-Disposition": f'attachment; filename="{download_name}"'}
    return StreamingResponse(stream(), media_type="application/octet-stream", headers=headers)

@app.get("/file/{filename}/download")
def download_reconstructed(filename: str, best_effort: int = Query(0)):
    """
    Descarga reconstruida (une los bloques en orden).
    Si best_effort=1: salta bloques que fallen y continúa con el resto,
    además envía una alerta al NameNode con los bloques/nodos faltantes.
    """
    meta = get_meta(filename)
    blocks = meta.get("blocks", [])
    if not blocks:
        raise HTTPException(404, "no blocks")

    mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type:
        mime_type = "application/octet-stream"

    missing_blocks: List[str] = []
    missing_dns: Set[str] = set()

    def stream_all():
        for b in blocks:
            block_id = b.get("block_id")
            dn = b.get("datanode")
            if not block_id or not dn:
                if best_effort:
                    missing_blocks.append(block_id or "unknown")
                    continue
                raise HTTPException(500, "invalid meta for block")

            dn_url = to_host_docker_internal(dn)
            try:
                with requests.get(f"{dn_url}/read/{block_id}", stream=True, timeout=7) as r:
                    if r.status_code == 200:
                        for chunk in r.iter_content(64 * 1024):
                            if chunk:
                                yield chunk
                    else:
                        missing_blocks.append(block_id)
                        missing_dns.add(dn)
                        if not best_effort:
                            raise HTTPException(r.status_code, f"missing block {block_id} from {dn}")
                        # en best_effort: saltar bloque
            except Exception:
                missing_blocks.append(block_id)
                missing_dns.add(dn)
                if not best_effort:
                    raise HTTPException(502, f"error reading {block_id} from {dn}")
                # en best_effort: saltar bloque

    # si hay faltantes, se manda alerta al terminar de construir la respuesta 
    # Andrea hace esto-
    def iterator():
        for chunk in stream_all():
            yield chunk
        if missing_blocks:
            post_alert(filename, missing_blocks, list(missing_dns))

    headers = {"Content-Disposition": f'inline; filename="{filename}"'}
    return StreamingResponse(iterator(), media_type=mime_type, headers=headers)
