#!/usr/bin/env python3
import argparse
import os
import requests
from requests.auth import HTTPBasicAuth
import hashlib
import json
import sys

# ---------------------------
# Helpers
# ---------------------------
def auth(args):
    return HTTPBasicAuth(args.user, args.password)

def nn(args):
    return args.namenode.rstrip("/")

def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def normalize_meta(raw):
    """
    Acepta varias formas de metadata (dict, string JSON, wrapper)
    y devuelve un dict con la estructura esperada.
    """
    if raw is None:
        return None
    # Si es un string que contiene JSON
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return None
    # Si es un dict pero contiene "metadata" como string o dict -> desempaquetar
    if isinstance(raw, dict):
        if "blocks" in raw:
            return raw
        if "metadata" in raw:
            m = raw["metadata"]
            if isinstance(m, str):
                try:
                    return json.loads(m)
                except Exception:
                    return None
            if isinstance(m, dict):
                return m
    return None

# ---------------------------
# Comandos
# ---------------------------
def cmd_ls(args):
    try:
        r = requests.get(f"{nn(args)}/ls/{args.dir}", auth=auth(args), timeout=5)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print("[ERROR] ls:", e)
        return

    directories = data.get("directories", [])
    files = data.get("files", [])

    print("📂 Carpetas:")
    if directories:
        for d in directories:
            print(f"  [{d['id']}] {d['name']}/")
    else:
        print("  (ninguna)")

    print("\n📄 Archivos:")
    if files:
        for f in files:
            size = f.get("size", "?")
            print(f"  [{f['id']}] {f['filename']} ({size} bytes)")
    else:
        print("  (ninguno)")

def cmd_put(args):
    if not os.path.exists(args.path):
        print("[ERROR] File not found:", args.path); return

    fname = os.path.basename(args.path)
    size = os.path.getsize(args.path)
    try:
        block_size = int(args.block_size)
    except Exception:
        print("[ERROR] invalid block-size"); return

    file_digest = file_hash(args.path)

    # 1) pedir asignación al NameNode
    try:
        r = requests.post(
            f"{nn(args)}/allocate",
            json={
                "owner": args.user,
                "filename": fname,
                "size": size,
                "block_size": block_size,
                "hash": file_digest
            },
            auth=auth(args),
            timeout=8,
        )
        r.raise_for_status()
        alloc_raw = r.json()
    except Exception as e:
        print("[ERROR] allocate:", e)
        return

    alloc = normalize_meta(alloc_raw) or alloc_raw  # si viene envuelto, normalizar

    if not isinstance(alloc, dict) or "blocks" not in alloc:
        print("[ERROR] allocate returned unexpected payload:", alloc_raw)
        return

    # 2) enviar bloques a sus DataNodes
    try:
        with open(args.path, "rb") as f:
            for i, blk in enumerate(alloc["blocks"]):
                data = f.read(block_size)
                dn = blk.get("datanode", "").rstrip("/")
                block_id = blk.get("block_id")
                if not dn or not block_id:
                    print("[WARN] invalid block allocation entry:", blk)
                    continue
                url = f"{dn}/store/{block_id}"
                rr = requests.put(url, files={"part": ("block", data)}, timeout=15)
                rr.raise_for_status()
                print(f"[OK] {block_id} -> {dn}")
    except Exception as e:
        print("[ERROR] uploading blocks:", e)
        return

    # 3) completar commit con directory_id si se da
    if isinstance(alloc, dict):
        alloc["directory_id"] = args.dir

    try:
        rc = requests.post(f"{nn(args)}/commit", json=alloc, auth=auth(args), timeout=8)
        rc.raise_for_status()
        print("commit ok")
    except Exception as e:
        print("[ERROR] commit:", e)

def cmd_get(args):
    # 1) Pedir metadatos
    try:
        r = requests.get(f"{nn(args)}/meta/{args.file_id}", auth=auth(args), timeout=8)
        r.raise_for_status()
        meta_raw = r.json()
    except Exception as e:
        print("[ERROR] getting metadata:", e)
        return

    meta = normalize_meta(meta_raw) or meta_raw

    if "blocks" not in meta:
        print("[ERROR] meta returned without 'blocks':", meta)
        return

    out = args.output or meta.get("filename", f"file_{args.file_id}")

    # 2) Reconstruir archivo (opción best_effort)
    best_effort = bool(args.best_effort)
    missing_blocks = []
    try:
        with open(out, "wb") as w:
            for blk in meta["blocks"]:
                dn = blk.get("datanode", "").rstrip("/")
                block_id = blk.get("block_id")
                if not dn or not block_id:
                    print("[WARN] invalid block entry:", blk)
                    missing_blocks.append(block_id or "<unknown>")
                    if not best_effort:
                        raise SystemExit("invalid block entry and not best_effort")
                    else:
                        continue

                url = f"{dn}/read/{block_id}"
                try:
                    rr = requests.get(url, stream=True, timeout=10)
                    if rr.status_code != 200:
                        raise Exception(f"status {rr.status_code}")
                    for chunk in rr.iter_content(1024 * 1024):
                        if chunk:
                            w.write(chunk)
                except Exception as e:
                    print(f"[WARN] could not fetch block {block_id} from {dn}: {e}")
                    missing_blocks.append(block_id)
                    if not best_effort:
                        print("Stopping because best_effort=0")
                        # remove partial file to avoid confusion
                        try:
                            w.close()
                            os.remove(out)
                        except Exception:
                            pass
                        return
                    # else continue with next block
    except Exception as e:
        print("[ERROR] reconstructing file:", e)
        return

    print(f"recuperado -> {out}")
    if missing_blocks:
        print("[INFO] missing blocks:", missing_blocks)

    # 3) Calcular hash local y compararlo (si hay hash)
    try:
        local_hash = file_hash(out)
    except Exception as e:
        print("[WARN] could not hash output file:", e)
        local_hash = None

    remote_hash = meta.get("hash")
    if remote_hash and local_hash:
        if local_hash == remote_hash:
            print("[OK] Trusted file (hash match)")
        else:
            print("[ERROR] Untrusted file (hash mismatch)")
    else:
        print("[WARNING] No remote hash to verify against")

def cmd_rm(args):
    try:
        r = requests.get(f"{nn(args)}/meta/{args.file_id}", auth=auth(args), timeout=6)
        if r.status_code == 200:
            meta = normalize_meta(r.json()) or r.json()
            for blk in meta.get("blocks", []):
                dn = blk.get("datanode", "").rstrip("/")
                block_id = blk.get("block_id")
                if dn and block_id:
                    try:
                        requests.delete(f"{dn}/delete/{block_id}", timeout=6)
                    except Exception:
                        print(f"warning: no pude borrar {block_id} en {dn}")
    except Exception:
        pass

    try:
        r2 = requests.delete(f"{nn(args)}/rm/{args.file_id}", auth=auth(args), timeout=6)
        r2.raise_for_status()
        print("eliminado")
    except Exception as e:
        print("[ERROR] rm:", e)

def cmd_mkdir(args):
    url = f"{nn(args)}/mkdir/{args.parent}/{args.name}"
    try:
        resp = requests.post(url, auth=auth(args), timeout=6)
        print("STATUS:", resp.status_code)
        print("TEXT:", resp.text)
    except Exception as e:
        print("[ERROR] mkdir:", e)

def cmd_rmdir(args):
    try:
        r = requests.delete(f"{nn(args)}/rmdir/{args.directory_id}", auth=auth(args), timeout=6)
        r.raise_for_status()
        print(f"Directorio {args.directory_id} eliminado correctamente")
    except Exception as e:
        print("[ERROR] rmdir:", e)

# ---------------------------
# Argparse / CLI
# ---------------------------
def main():
    p = argparse.ArgumentParser(prog="griddfs")
    p.add_argument("--namenode", default="http://localhost:8000")
    p.add_argument("--user", default="alice")
    p.add_argument("--password", default="alicepwd")

    sub = p.add_subparsers(dest="cmd", required=True)

    # ls
    s_ls = sub.add_parser("ls")
    s_ls.add_argument("--dir", type=int, default=1, help="ID del directorio a listar (por defecto root=1)")
    s_ls.set_defaults(func=cmd_ls)

    # put 
    s_put = sub.add_parser("put")
    s_put.add_argument("path")
    s_put.add_argument("--block-size", default=os.getenv("BLOCK_SIZE", 50*1024))
    s_put.add_argument("--dir", type=int, default=1, help="ID del directorio destino (por defecto root=1)")
    s_put.set_defaults(func=cmd_put)

    # get
    s_get = sub.add_parser("get")
    s_get.add_argument("file_id", type=int)
    s_get.add_argument("--output")
    s_get.add_argument("--best-effort", action="store_true", help="Si se pierden bloques, reconstruir lo posible")
    s_get.set_defaults(func=cmd_get)

    # rm
    s_rm = sub.add_parser("rm")
    s_rm.add_argument("file_id", type=int)
    s_rm.set_defaults(func=cmd_rm)

    # mkdir 
    s_mkdir = sub.add_parser("mkdir")
    s_mkdir.add_argument("parent", type=int, help="ID del directorio padre")
    s_mkdir.add_argument("name", help="Nombre del nuevo directorio")
    s_mkdir.set_defaults(func=cmd_mkdir)

    # rmdir
    s_rmdir = sub.add_parser("rmdir")
    s_rmdir.add_argument("directory_id", type=int, help="ID del directorio a eliminar")
    s_rmdir.set_defaults(func=cmd_rmdir)

    args = p.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
