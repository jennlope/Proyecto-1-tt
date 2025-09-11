import argparse, os, requests
from requests.auth import HTTPBasicAuth

def auth(args): return HTTPBasicAuth(args.user, args.password)
def nn(args): return args.namenode.rstrip("/")

def cmd_ls(args):
    r = requests.get(f"{nn(args)}/ls", auth=auth(args)); r.raise_for_status()
    for f in r.json():
        print(f"{f['filename']}\t{f['size']}")

def cmd_put(args):
    fname = os.path.basename(args.path)
    size = os.path.getsize(args.path)
    block_size = int(args.block_size)
    # 1) pedir asignación
    alloc = requests.post(f"{nn(args)}/allocate",
                          json={"owner": args.user, "filename": fname, "size": size, "block_size": block_size},
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
    # 3) commit de metadatos
    requests.post(f"{nn(args)}/commit", json=alloc, auth=auth(args)).raise_for_status()
    print("commit ok")

def cmd_get(args):
    meta = requests.get(f"{nn(args)}/meta/{args.user}/{args.filename}", auth=auth(args)).json()
    out = args.output or args.filename
    with open(out, "wb") as w:
        for blk in meta["blocks"]:
            dn = blk["datanode"].rstrip("/")
            url = f"{dn}/read/{blk['block_id']}"
            with requests.get(url, stream=True) as r:
                if r.status_code != 200:
                    raise SystemExit(f"Bloque faltante: {blk['block_id']} en {dn}")
                for chunk in r.iter_content(1024*1024):
                    w.write(chunk)
    print(f"recuperado -> {out}")

def cmd_rm(args):
    # fetch meta para borrar físicamente
    meta = requests.get(f"{nn(args)}/meta/{args.user}/{args.filename}", auth=auth(args))
    if meta.status_code == 200:
        for blk in meta.json()["blocks"]:
            try:
                requests.delete(f"{blk['datanode'].rstrip('/')}/delete/{blk['block_id']}").raise_for_status()
            except Exception:
                print(f"warning: no pude borrar {blk['block_id']}")
    requests.delete(f"{nn(args)}/rm/{args.filename}", auth=auth(args)).raise_for_status()
    print("borrado")

def main():
    p = argparse.ArgumentParser(prog="griddfs")
    p.add_argument("--namenode", default="http://localhost:8000")
    p.add_argument("--user", default="alice")
    p.add_argument("--password", default="alicepwd")

    sub = p.add_subparsers(dest="cmd", required=True)
    s_ls = sub.add_parser("ls"); s_ls.set_defaults(func=cmd_ls)

    s_put = sub.add_parser("put")
    s_put.add_argument("path")
    s_put.add_argument("--block-size", default=os.getenv("BLOCK_SIZE", 50*1024))
    s_put.set_defaults(func=cmd_put)

    s_get = sub.add_parser("get")
    s_get.add_argument("filename")
    s_get.add_argument("--output")
    s_get.set_defaults(func=cmd_get)

    s_rm = sub.add_parser("rm")
    s_rm.add_argument("filename")
    s_rm.set_defaults(func=cmd_rm)

    args = p.parse_args(); args.func(args)

if __name__ == "__main__":
    main()
