from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, StreamingResponse
import requests, os, mimetypes

NAMENODE = os.getenv("NAMENODE_URL", "http://localhost:8000")
USER = os.getenv("DFS_USER", "alice")
PASS = os.getenv("DFS_PASS", "alicepwd")

app = FastAPI(title="GridDFS Dashboard")
templates = Jinja2Templates(directory="templates")

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
    r = requests.get(f"{NAMENODE}/datanodes", timeout=5)
    if r.status_code != 200:
        return {}
    return r.json()

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    files = ls_files()
    return templates.TemplateResponse("index.html", {"request": request, "files": files})

@app.get("/file/{filename}", response_class=HTMLResponse)
def file_detail(request: Request, filename: str):
    meta = get_meta(filename)
    nodes = get_datanodes()
    # meta esperado: {"filename": "...", "size": N, "blocks": [{"block_id":"alice:fn:0","datanode":"http://.."}, ...]}
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
    Nombramos el archivo como <nombre>.block<idx><ext> para que quede claro
    que es un fragmento, pero con la extensión original al final.
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

    url = f"{dn}/read/{block_id}"
    stem, ext = os.path.splitext(filename)  # e.g. ("Prueba", ".pdf")
    download_name = f"{stem}.block{index}{ext or ''}"

    def stream():
        # Convertir localhost a host.docker.internal para acceso desde contenedor
        datanode_url = dn.replace("http://localhost:", "http://host.docker.internal:")
        with requests.get(f"{datanode_url}/read/{block_id}", stream=True, timeout=10) as r:
            r.raise_for_status()
            for chunk in r.iter_content(64 * 1024):
                if chunk:
                    yield chunk

    # sigue siendo binario (no es un PDF completo)
    headers = {"Content-Disposition": f'attachment; filename="{download_name}"'}
    return StreamingResponse(stream(), media_type="application/octet-stream", headers=headers)


@app.get("/file/{filename}/download")
def download_reconstructed(filename: str):
    """
    Descarga reconstruida (une los bloques en orden).
    Damos Content-Type según extensión para que el navegador lo abra (PDF inline).
    """
    meta = get_meta(filename)
    blocks = meta.get("blocks", [])
    if not blocks:
        raise HTTPException(404, "no blocks")

    mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type:
        mime_type = "application/octet-stream"

    def stream_all():
        for b in blocks:
            block_id = b.get("block_id")
            dn = b.get("datanode")
            if not block_id or not dn:
                raise HTTPException(500, "invalid meta for block")
            # Convertir localhost a host.docker.internal para acceso desde contenedor
            datanode_url = dn.replace("http://localhost:", "http://host.docker.internal:")
            with requests.get(f"{datanode_url}/read/{block_id}", stream=True, timeout=10) as r:
                r.raise_for_status()
                for chunk in r.iter_content(64 * 1024):
                    if chunk:
                        yield chunk

    # usa 'inline' para que el PDF se abra en el visor del navegador
    headers = {"Content-Disposition": f'inline; filename="{filename}"'}
    return StreamingResponse(stream_all(), media_type=mime_type, headers=headers)