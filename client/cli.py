import argparse, os, requests, time
from requests.auth import HTTPBasicAuth
import hashlib

def auth(args): return HTTPBasicAuth(args.user, args.password)
def nn(args): return args.namenode.rstrip("/")

def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def cmd_ls(args):
    r = requests.get(f"{nn(args)}/ls/{args.dir}", auth=auth(args))
    r.raise_for_status()
    data = r.json()
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
    fname = os.path.basename(args.path)
    size = os.path.getsize(args.path)
    block_size = int(args.block_size)

    file_digest = file_hash(args.path)

    # 1) pedir asignación
    alloc = requests.post(f"{nn(args)}/allocate",
                        json={
                            "owner": args.user,
                            "filename": fname,
                            "size": size,
                            "block_size": block_size,
                            "hash": file_digest
                        },
                        auth=auth(args)).json()
    
    # 2) enviar bloques a sus DataNodes
    with open(args.path, "rb") as f:
        for i, blk in enumerate(alloc["blocks"]):
            data = f.read(block_size)
            dn = blk["datanode"].rstrip("/")
            url = f"{dn}/store/{blk['block_id']}"
            with requests.put(url, files={"part": ("block", data)}) as rr:
                rr.raise_for_status()
            print(f"[OK] {blk['block_id']} -> {dn}")
    
    alloc["directory_id"] = args.dir
    # 3) commit con metadata
    requests.post(f"{nn(args)}/commit", json=alloc, auth=auth(args)).raise_for_status()
    print("commit ok")

def cmd_get(args):
    # 1) Pedir metadatos
    meta = requests.get(f"{nn(args)}/meta/{args.file_id}", auth=auth(args)).json()
    out = args.output or meta.get("name", f"file_{args.file_id}")

    # 2) Reconstruir archivo con tolerancia a fallos
    failed_blocks = []
    down_datanodes = []
    
    with open(out, "wb") as w:
        for blk in meta["blocks"]:
            dn = blk["datanode"].rstrip("/")
            url = f"{dn}/read/{blk['block_id']}"
            
            try:
                with requests.get(url, stream=True, timeout=10) as r:
                    if r.status_code != 200:
                        print(f"[ERROR] Bloque no encontrado: {blk['block_id']} en {dn}")
                        failed_blocks.append(blk['block_id'])
                        if dn not in down_datanodes:
                            down_datanodes.append(dn)
                        continue
                    
                    for chunk in r.iter_content(1024*1024):
                        w.write(chunk)
                    print(f"[OK] Bloque descargado: {blk['block_id']} desde {dn}")
                        
            except requests.exceptions.ConnectionError as e:
                print(f"[ERROR] DataNode caído: {dn} - No se puede descargar {blk['block_id']}")
                failed_blocks.append(blk['block_id'])
                if dn not in down_datanodes:
                    down_datanodes.append(dn)
                continue
            except requests.exceptions.Timeout:
                print(f"[ERROR] Timeout en DataNode: {dn} - {blk['block_id']}")
                failed_blocks.append(blk['block_id'])
                if dn not in down_datanodes:
                    down_datanodes.append(dn)
                continue
            except Exception as e:
                print(f"[ERROR] Error inesperado con {dn}: {str(e)}")
                failed_blocks.append(blk['block_id'])
                if dn not in down_datanodes:
                    down_datanodes.append(dn)
                continue

    # 3) Enviar alerta si hay bloques faltantes
    if failed_blocks:
        alert_data = {
            "user": args.user,
            "filename": meta.get("filename", f"file_{args.file_id}"),
            "down_nodes": down_datanodes,
            "missing_blocks": failed_blocks,
            "reason": "download_failed_due_to_down_nodes",
            "ts": int(time.time())
        }
        
        try:
            alert_response = requests.post(f"{nn(args)}/alerts", json=alert_data, timeout=5)
            if alert_response.status_code == 200:
                print(f"[ALERT] Alerta enviada al NameNode: {len(failed_blocks)} bloques faltantes")
            else:
                print(f"[WARNING] No se pudo enviar alerta: {alert_response.status_code}")
        except Exception as e:
            print(f"[WARNING] Error enviando alerta: {str(e)}")
        
        print(f"\n[RESULTADO] Descarga parcialmente fallida:")
        print(f"  - Bloques faltantes: {len(failed_blocks)}")
        print(f"  - DataNodes caídos: {down_datanodes}")
        print(f"  - Archivo puede estar incompleto: {out}")
        
        # No salir con error, solo advertir
        return
    
    print(f"recuperado -> {out}")

    # 4) Calcular hash local y compararlo (solo si descarga completa)
    local_hash = file_hash(out)
    remote_hash = meta.get("hash")

    if remote_hash:
        if local_hash == remote_hash:
            print("[OK] Trusted file")
        else:
            print("[ERROR] Untrusted file")
    else:
        print("[WARNING] It was not possible to verify reliability")

def cmd_rm(args):
    meta = requests.get(f"{nn(args)}/meta/{args.file_id}", auth=auth(args))
    if meta.status_code == 200:
        for blk in meta.json()["blocks"]:
            try:
                requests.delete(f"{blk['datanode'].rstrip('/')}/delete/{blk['block_id']}").raise_for_status()
            except Exception:
                print(f"warning: no pude borrar {blk['block_id']}")
    # borrar en el NameNode
    requests.delete(f"{nn(args)}/rm/{args.file_id}", auth=auth(args)).raise_for_status()
    print("eliminado")

def cmd_mkdir(args):
    url = f"{nn(args)}/mkdir/{args.parent}/{args.name}"
    resp = requests.post(url, auth=auth(args))
    print("STATUS:", resp.status_code)
    print("TEXT:", resp.text)

def cmd_rmdir(args):
    r = requests.delete(f"{nn(args)}/rmdir/{args.directory_id}", auth=auth(args))
    r.raise_for_status()
    print(f"Directorio {args.directory_id} eliminado correctamente")


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

    #rmdir
    s_rmdir = sub.add_parser("rmdir")
    s_rmdir.add_argument("directory_id", type=int, help="ID del directorio a eliminar")
    s_rmdir.set_defaults(func=cmd_rmdir)


    args = p.parse_args()
    args.func(args)



if __name__ == "__main__":
    main()
