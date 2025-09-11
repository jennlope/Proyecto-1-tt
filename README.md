# GridDFS – Proyecto de Sistema de Archivos Distribuido

Este proyecto implementa un sistema de archivos distribuido tipo GridDFS, inspirado en HDFS, usando Python, FastAPI y Docker. Permite almacenar, recuperar y eliminar archivos de manera distribuida entre varios nodos.

---

## Arquitectura

```mermaid
flowchart TD
  subgraph Usuario
    CLI[CLI (cli.py)]
    Web[Dashboard Web]
  end

  subgraph Servidores
    NN[NameNode]
    DN1[DataNode 1]
    DN2[DataNode 2]
    DN3[DataNode 3]
  end

  CLI -- "put/get/rm/ls" --> NN
  NN -- "Asignación de bloques / Metadatos" --> CLI
  CLI -- "Envía/Recupera/Elimina bloques" --> DN1
  CLI -- "Envía/Recupera/Elimina bloques" --> DN2
  CLI -- "Envía/Recupera/Elimina bloques" --> DN3

  Web -- "Consulta archivos/metadatos" --> NN
  Web -- "Descarga bloques" --> DN1
  Web -- "Descarga bloques" --> DN2
  Web -- "Descarga bloques" --> DN3

  DN1 -- "Registro" --> NN
  DN2 -- "Registro" --> NN
  DN3 -- "Registro" --> NN
```

---

## Estructura del proyecto

```
├── client/
│   └── cli.py           # Cliente CLI para interactuar con el sistema
├── dashboard/
│   ├── main.py          # Dashboard web
│   └── templates/       # Plantillas HTML
├── datanode/
│   ├── Dockerfile
│   └── app/
│       └── main.py      # API de DataNode
├── namenode/
│   ├── Dockerfile
│   └── app/
│       ├── main.py      # API de NameNode
│       ├── models.py    # Modelos de datos
│       └── storage.py   # (opcional)
├── docker-compose.yml   # Orquestación de servicios
├── demo.txt             # Archivo de ejemplo
└── ...                  # Otros archivos y volúmenes
```

---

## Instalación y ejecución

### 1. Crear entorno virtual (opcional, para desarrollo local)

```powershell
python -m venv venv
venv\Scripts\activate
```

### 2. Instalar dependencias (desarrollo local)

```powershell
pip install -r dependencias.txt
```

### 3. Ejecución con Docker

Obviamente hay que tener Docker y Docker Compose instalados.

```powershell
docker-compose up --build
#Para eliminarlo
docker-compose down
```
Esto levantará los servicios:
- NameNode (puerto 8000)
- DataNode1 (puerto 8001)
- DataNode2 (puerto 8002)
- DataNode3 (puerto 8003)
- Dashboard (puerto 8080)

### 4. Uso básico del CLI

Subir un archivo:
```powershell
python client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 put demo.txt
```
Listar archivos:
```powershell
python client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 ls
```
Descargar archivo:
```powershell
python client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 get demo.txt
```
Eliminar archivo:
```powershell
python client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 rm demo.txt
```

### 5. Acceso al Dashboard Web

Abre tu navegador en:
```
http://localhost:8080
```
Podrás visualizar archivos, detalles y descargar bloques o archivos completos.

---

## Variables de entorno relevantes

- `BLOCK_SIZE`: Tamaño de bloque en bytes (por defecto 64MB)
- `USERS`: Usuarios permitidos (ejemplo: "alice:alicepwd,bob:bobpwd")
- `NAMENODE_URL`: URL del NameNode para los DataNodes y Dashboard
- `NODE_ID`: Identificador de cada DataNode
- `BASE_URL`: URL base de cada DataNode
- `DFS_USER` y `DFS_PASS`: Usuario y contraseña para el Dashboard

---

## Dependencias principales

- Python >= 3.11
- fastapi
- uvicorn
- requests
- aiosqlite
- pydantic[dotenv]
- python-multipart
- jinja2
- Docker
- Docker Compose

---

## Notas
- Los archivos se dividen en bloques y se distribuyen entre los DataNodes.
- El NameNode gestiona los metadatos y la asignación de bloques.
- El Dashboard permite visualizar y descargar archivos y bloques.
- El CLI permite subir, listar, descargar y eliminar archivos.

---

## Créditos
Proyecto desarrollado para la materia de Telemática.
# Proyecto 1 – Grid DFS (FastAPI + Docker)

Sistema distribuido simple tipo DFS (estilo HDFS) con:
- **NameNode (FastAPI)**: catálogo, metadatos y asignación de bloques.
- **DataNodes (3 × FastAPI)**: guardan físicamente los bloques.
- **Cliente CLI (Python)**: `put`, `ls`, `get`, `rm`.
- **Dashboard (FastAPI + Jinja2)**: UI para ver archivos, bloques y descargar por bloque o reconstruido.

---

## 🧱 Arquitectura (resumen)

- El **cliente** sube un archivo → el **NameNode** lo parte en bloques → asigna cada bloque a un **DataNode** → el cliente envía cada bloque al nodo correspondiente.
- Al descargar, el cliente (o el dashboard) pide los bloques en orden y reconstruye el archivo.
- El **dashboard** muestra los archivos, sus bloques y a qué DataNode fue cada uno. Permite descargar cada bloque o el archivo reconstruido.

---

## 📦 Requisitos previos

- **Docker** y **Docker Compose**
- **Python 3.11+**
- (Opcional) **WSL** si estás en Windows

---

## 🗂️ Estructura del proyecto (esperada)

```
Proyecto 1/
├─ docker-compose.yml
├─ .gitignore
├─ client/
│  └─ cli.py
├─ namenode/
│  ├─ Dockerfile
│  ├─ requirements.txt
│  └─ app/
│     ├─ main.py
│     └─ (otros .py)
├─ datanode/
│  ├─ Dockerfile
│  ├─ requirements.txt
│  └─ app/
│     └─ main.py
└─ dashboard/
   ├─ Dockerfile
   ├─ requirements.txt
   ├─ main.py
   └─ templates/
      ├─ index.html
      └─ file.html
```

---

## 🔧 1) Crear entorno virtual

```bash
# dentro de la carpeta del proyecto
python3 -m venv .venv
source .venv/bin/activate        # Windows (PowerShell):  .\.venv\Scripts\Activate.ps1

# instala dependencias para usar el cliente localmente
pip install -r namenode/requirements.txt             -r datanode/requirements.txt             -r dashboard/requirements.txt
```

> El cliente usa solo `requests`. Ya está incluido en los requirements de datanode/dashboard.

---

## 🐳 2) Ejecutar con Docker Compose

### Variables y puertos
- NameNode: `8000`
- DataNodes: `8001`, `8002`, `8003`
- Dashboard: `8080`

### `docker-compose.yml` (ejemplo mínimo)

```yaml
name: proyecto1

services:
  namenode:
    build: ./namenode
    container_name: namenode
    environment:
      BLOCK_SIZE: "67108864"             # por defecto
      USERS: "alice:alicepwd,bob:bobpwd" # usuarios
      BASE_URL: "http://namenode:8000"
    ports:
      - "8000:8000"
    volumes:
      - nn_data:/app/data

  datanode1:
    build: ./datanode
    container_name: datanode1
    environment:
      NODE_ID: dn1
      NAMENODE_URL: http://namenode:8000
      BASE_URL: http://localhost:8001
    ports:
      - "8001:8001"
    volumes:
      - dn1_data:/app/blocks
    depends_on:
      - namenode

  datanode2:
    build: ./datanode
    container_name: datanode2
    environment:
      NODE_ID: dn2
      NAMENODE_URL: http://namenode:8000
      BASE_URL: http://localhost:8002
    ports:
      - "8002:8001"
    volumes:
      - dn2_data:/app/blocks
    depends_on:
      - namenode

  datanode3:
    build: ./datanode
    container_name: datanode3
    environment:
      NODE_ID: dn3
      NAMENODE_URL: http://namenode:8000
      BASE_URL: http://localhost:8003
    ports:
      - "8003:8001"
    volumes:
      - dn3_data:/app/blocks
    depends_on:
      - namenode

  dashboard:
    build: ./dashboard
    container_name: dashboard
    environment:
      NAMENODE_URL: http://namenode:8000
      DFS_USER: alice
      DFS_PASS: alicepwd
    ports:
      - "8080:8080"
    depends_on:
      - namenode

volumes:
  nn_data:
  dn1_data:
  dn2_data:
  dn3_data:
```

### Construir y levantar

```bash
docker compose up --build -d
docker compose ps
```

**Verifica nodos registrados:**
```bash
curl -s http://localhost:8000/datanodes
# {"dn1":"http://localhost:8001","dn2":"http://localhost:8002","dn3":"http://localhost:8003"}
```

**Dashboard:**  
👉 http://localhost:8080

---

## 💻 3) Uso del cliente (CLI)

Autenticación: `--user alice --password alicepwd --namenode http://localhost:8000`

### Subir archivo
```bash
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 put ./Prueba.pdf --block-size 32768
```

### Listar archivos
```bash
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 ls
```

### Descargar archivo
```bash
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 get Prueba.pdf --output ./Prueba_descargada.pdf
```

### Eliminar archivo
```bash
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 rm Prueba.pdf
```

---

## 🧪 4) Demo de sharding (visual)

### Crear archivo de prueba
```bash
printf 'a%.0s' {1..100} > demo.txt
printf 'b%.0s' {1..100} >> demo.txt
printf 'c%.0s' {1..100} >> demo.txt
wc -c demo.txt   # 300
```

### Subirlo en 3 bloques
```bash
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 put ./demo.txt --block-size 100
```

**Ejemplo de salida:**
```
[OK] alice:demo.txt:0 -> http://localhost:8003
[OK] alice:demo.txt:1 -> http://localhost:8001
[OK] alice:demo.txt:2 -> http://localhost:8002
commit ok
```

### Ver en el Dashboard
- Abre `http://localhost:8080` → demo.txt
- Bloques listados con nodo asignado
- Botones:
  - “⬇️ Bloque i” → descarga fragmento
  - “⬇️ Descargar reconstruido” → baja los 300 bytes unidos

### Verificar por terminal
```bash
curl -s http://localhost:8080/block/demo.txt/0 | wc -c   # 100
curl -s http://localhost:8080/block/demo.txt/1 | wc -c   # 100
curl -s http://localhost:8080/block/demo.txt/2 | wc -c   # 100
curl -s http://localhost:8080/file/demo.txt/download | wc -c   # 300
```

---

## 🩺 5) Endpoints útiles

**NameNode**
- `GET /datanodes` → nodos registrados
- `GET /ls` (auth) → lista de archivos
- `GET /meta/{user}/{filename}` (auth) → metadatos
- `POST /register` → registrar datanode

**DataNode**
- `PUT /store/{block_id}` → guardar bloque
- `GET /read/{block_id}` → leer bloque
- `GET /health` → salud

**Dashboard**
- `/` → lista de archivos
- `/file/{filename}` → detalle de bloques
- `/block/{filename}/{i}` → descarga bloque
- `/file/{filename}/download` → reconstrucción completa

---

## 🛠️ 6) Solución de problemas

- **Connection refused en DataNodes**: revisa `docker compose ps` y logs (`docker compose logs datanode1`).
- **Error `python-multipart`**: asegúrate de que está en `requirements.txt` del datanode.
- **`/datanodes` vacío**: los nodos no se registraron → revisa `BASE_URL` en `docker-compose.yml`.

---

## 🧾 7) Dependencias

### `namenode/requirements.txt`
```
fastapi
uvicorn[standard]
aiosqlite
pydantic[dotenv]
python-multipart
requests
```

### `datanode/requirements.txt`
```
fastapi
uvicorn[standard]
requests
python-multipart
```

### `dashboard/requirements.txt`
```
fastapi
uvicorn[standard]
requests
jinja2
```

---

## 🧹 8) .gitignore recomendado

```
__pycache__/
*.pyc
*.pyo
*.pyd
*.log

# entornos
.venv/
.env

# IDEs
.vscode/
.idea/

# datos locales
*.sqlite3
*.db

# Docker
*.pid
```

---

## ✅ 9) Flujo típico

1. `docker compose up --build -d`  
2. Ver nodos → `curl http://localhost:8000/datanodes`  
3. Subir archivo → `client/cli.py put archivo --block-size N`  
4. Ver UI → `http://localhost:8080`  
5. Descargar bloques o reconstruido → dashboard o `cli.py get`  
6. Eliminar archivo → `cli.py rm archivo`
