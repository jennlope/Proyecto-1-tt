# GridDFS – Sistema de Archivos Distribuido

Este proyecto implementa un sistema de archivos distribuido tipo GridDFS, inspirado en HDFS, usando Python, FastAPI y Docker. Permite almacenar, recuperar y eliminar archivos de manera distribuida entre varios nodos, con soporte completo para directorios y subdirectorios.

---

## Características principales

- **Sistema de archivos jerárquico**: Soporte completo para carpetas y subcarpetas
- **Distribución de bloques**: Los archivos se dividen en bloques y se distribuyen entre DataNodes
- **Gestión de metadatos**: NameNode centralizado para metadatos y asignación de bloques
- **Cliente CLI**: Interfaz de línea de comandos completa para todas las operaciones
- **Dashboard web**: Interfaz gráfica para visualizar y descargar archivos
- **Persistencia**: Los datos se mantienen entre reinicios de contenedores

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

  CLI -- "put/get/rm/ls/mkdir" --> NN
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
│       ├── index.html
│       └── file.html
├── datanode/
│   ├── Dockerfile
│   └── app/
│       └── main.py      # API de DataNode
├── namenode/
│   ├── Dockerfile
│   └── app/
│       ├── main.py      # API de NameNode
│       └── models.py    # Modelos de datos
├── docker-compose.yml   # Orquestación de servicios
├── demo.txt             # Archivo de ejemplo
└── requirements.txt     # Dependencias
```

---

## Instalación y configuración

### Requisitos previos

- **Docker** y **Docker Compose**
- **Python 3.11+**
- **Sistema operativo**: Linux (Ubuntu, Debian, etc.)

### 1. Clonar y preparar el proyecto

```bash
cd ~/
git clone <tu-repositorio>
cd Proyecto-1-tt

# Crear entorno virtual (opcional, para desarrollo local)
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias para el cliente
pip install requests
```

### 2. Ejecutar con Docker Compose

```bash
# Levantar todos los servicios
docker compose up --build -d

# Verificar que todos los contenedores están corriendo
docker compose ps

# Ver logs si hay problemas
docker compose logs namenode
```

**Servicios levantados:**
- NameNode (puerto 8000)
- DataNode1 (puerto 8001) 
- DataNode2 (puerto 8002)
- DataNode3 (puerto 8003)
- Dashboard (puerto 8080)

### 3. Verificar instalación

```bash
# Verificar nodos registrados
curl -s http://localhost:8000/datanodes

# Debería devolver algo como:
# {"dn1":{"base_url":"http://localhost:8001","last_seen":1234567890,"status":"UP"}}
```

---

## Uso del cliente CLI

### Sintaxis básica

```bash
python3 client/cli.py --user <usuario> --password <contraseña> --namenode http://localhost:8000 <comando>
```

**Usuarios por defecto:**
- Usuario: `alice`, Contraseña: `alicepwd`
- Usuario: `bob`, Contraseña: `bobpwd`

### Comandos disponibles

#### 1. Listar contenido de directorios

```bash
# Listar directorio raíz
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 ls

# Listar directorio específico por ID
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 ls --dir 2
```

**Salida ejemplo:**
```
📂 Carpetas:
  [2] documentos/
  [3] imagenes/

📄 Archivos:
  [1] readme.txt (1024 bytes)
```

#### 2. Crear directorios

```bash
# Crear carpeta en directorio raíz (ID=1)
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 mkdir 1 documentos

# Crear subcarpeta dentro de "documentos" (supongamos ID=2)
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 mkdir 2 proyectos

# Crear carpeta anidada
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 mkdir 3 2024
```

#### 3. Subir archivos

```bash
# Subir archivo al directorio raíz
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 put demo.txt

# Subir archivo a carpeta específica
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 put documento.pdf --dir 2

# Subir con tamaño de bloque personalizado
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 put archivo_grande.zip --block-size 32768 --dir 2
```

#### 4. Descargar archivos

```bash
# Descargar por ID de archivo
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 get 1

# Descargar con nombre personalizado
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 get 1 --output mi_archivo.txt
```

#### 5. Eliminar archivos y directorios

```bash
# Eliminar archivo por ID
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 rm 1

# Eliminar directorio vacío
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 rmdir 3
```

### Ejemplo de flujo completo

```bash
# 1. Listar contenido inicial (vacío)
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 ls

# 2. Crear estructura de directorios
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 mkdir 1 documentos
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 mkdir 1 imagenes
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 mkdir 2 proyectos

# 3. Subir archivos
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 put demo.txt --dir 2
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 put imagen.jpg --dir 3

# 4. Verificar estructura
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 ls
python3 client/cli.py --user alice --password alicepwd --namenode http://localhost:8000 ls --dir 2
```

---

## Dashboard web

### Acceso

Abre tu navegador en: **http://localhost:8080**

### Funcionalidades

- **Vista de archivos**: Lista todos los archivos del sistema
- **Detalles de bloques**: Muestra cómo se distribuyen los bloques entre DataNodes
- **Descarga individual**: Descarga bloques específicos
- **Descarga completa**: Reconstruye y descarga archivos completos

---

## Gestión del sistema

### Reinicio completo y limpieza

Para limpiar completamente el sistema (eliminar todos los datos):

```bash
# 1. Detener contenedores
docker compose down

# 2. Limpiar datos del NameNode
sudo rm -rf namenode/data/*

# 3. Eliminar volúmenes de DataNodes
docker volume rm proyecto1_dn1_data proyecto1_dn2_data proyecto1_dn3_data

# 4. Reiniciar sistema
docker compose up -d
```

### Verificar estado del sistema

```bash
# Estado de contenedores
docker compose ps

# Logs de servicios
docker compose logs namenode
docker compose logs datanode1

# Estado de DataNodes
curl -s http://localhost:8000/datanodes
```

### Variables de entorno

Puedes personalizar el comportamiento editando `docker-compose.yml`:

- `BLOCK_SIZE`: Tamaño de bloque en bytes (por defecto 51200)
- `USERS`: Usuarios permitidos ("alice:alicepwd,bob:bobpwd")
- `NAMENODE_URL`: URL del NameNode
- `NODE_ID`: Identificador único de cada DataNode

---

## Arquitectura técnica

### NameNode (Puerto 8000)
- **Base de datos**: SQLite para metadatos y estructura de directorios
- **Endpoints principales**:
  - `GET /ls/{directory_id}` → Listar contenido de directorio
  - `POST /mkdir/{parent_id}/{dirname}` → Crear directorio
  - `POST /allocate` → Asignar bloques para archivo
  - `GET /meta/{file_id}` → Obtener metadatos de archivo

### DataNodes (Puertos 8001-8003)
- **Almacenamiento**: Archivos de bloques en sistema de archivos local
- **Endpoints principales**:
  - `PUT /store/{block_id}` → Guardar bloque
  - `GET /read/{block_id}` → Leer bloque
  - `DELETE /delete/{block_id}` → Eliminar bloque

### Dashboard (Puerto 8080)
- **Framework**: FastAPI + Jinja2
- **Funciones**: Visualización y descarga de archivos

---

## Solución de problemas

### Error: "Parent directory not found"
- **Causa**: El directorio padre no existe o ID incorrecto
- **Solución**: Usar `ls` para verificar IDs correctos de directorios

### Error: "Connection refused"
- **Causa**: Contenedores no iniciados correctamente
- **Solución**: 
  ```bash
  docker compose ps
  docker compose logs <servicio>
  docker compose restart <servicio>
  ```

### Error: "Permission denied" al eliminar archivos
- **Causa**: Permisos de archivos creados por Docker
- **Solución**: `sudo rm -rf namenode/data/*`

### DataNodes no se registran
- **Causa**: Problemas de red entre contenedores
- **Solución**: Verificar `docker-compose.yml` y reiniciar servicios

---

## Dependencias técnicas

### Python
```
fastapi
uvicorn[standard]
aiosqlite
pydantic
requests
python-multipart
jinja2
```

### Contenedores
- **Base**: Python 3.11
- **Red**: Red interna de Docker Compose
- **Volúmenes**: Persistencia de datos entre reinicios

---

## Créditos

Proyecto desarrollado para la materia de Telemática.
Sistema distribuido GridDFS implementado con Docker, FastAPI y Python.
# Proyecto 1 – Grid DFS (FastAPI + Docker)

Sistema distribuido simple tipo DFS (estilo HDFS) con:
- **NameNode (FastAPI)**: catálogo, metadatos y asignación de bloques.
- **DataNodes (3 × FastAPI)**: guardan físicamente los bloques.
- **Cliente CLI (Python)**: `put`, `ls`, `get`, `rm`.
- **Dashboard (FastAPI + Jinja2)**: UI para ver archivos, bloques y descargar por bloque o reconstruido.

---

## Arquitectura (resumen)

- El **cliente** sube un archivo → el **NameNode** lo parte en bloques → asigna cada bloque a un **DataNode** → el cliente envía cada bloque al nodo correspondiente.
- Al descargar, el cliente (o el dashboard) pide los bloques en orden y reconstruye el archivo.
- El **dashboard** muestra los archivos, sus bloques y a qué DataNode fue cada uno. Permite descargar cada bloque o el archivo reconstruido.

---

## Requisitos previos

- **Docker** y **Docker Compose**
- **Python 3.11+**
- (Opcional) **WSL** si estás en Windows

---

## Estructura del proyecto (esperada)

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

## 1) Crear entorno virtual

```bash
# dentro de la carpeta del proyecto
python3 -m venv .venv
source .venv/bin/activate        # Windows (PowerShell):  .\.venv\Scripts\Activate.ps1

# instala dependencias para usar el cliente localmente
pip install -r namenode/requirements.txt             -r datanode/requirements.txt             -r dashboard/requirements.txt
```

> El cliente usa solo `requests`. Ya está incluido en los requirements de datanode/dashboard.

---

## 2) Ejecutar con Docker Compose

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
 http://localhost:8080

---

## 3) Uso del cliente (CLI)

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

## 4) Demo de sharding (visual)

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
  - “ Bloque i” → descarga fragmento
  - “ Descargar reconstruido” → baja los 300 bytes unidos

### Verificar por terminal
```bash
curl -s http://localhost:8080/block/demo.txt/0 | wc -c   # 100
curl -s http://localhost:8080/block/demo.txt/1 | wc -c   # 100
curl -s http://localhost:8080/block/demo.txt/2 | wc -c   # 100
curl -s http://localhost:8080/file/demo.txt/download | wc -c   # 300
```

---

## 5) Endpoints útiles

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

## 6) Solución de problemas

- **Connection refused en DataNodes**: revisa `docker compose ps` y logs (`docker compose logs datanode1`).
- **Error `python-multipart`**: asegúrate de que está en `requirements.txt` del datanode.
- **`/datanodes` vacío**: los nodos no se registraron → revisa `BASE_URL` en `docker-compose.yml`.

---

## 7) Dependencias

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

## 8) .gitignore recomendado

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

## 9) Flujo típico

1. `docker compose up --build -d`  
2. Ver nodos → `curl http://localhost:8000/datanodes`  
3. Subir archivo → `client/cli.py put archivo --block-size N`  
4. Ver UI → `http://localhost:8080`  
5. Descargar bloques o reconstruido → dashboard o `cli.py get`  
6. Eliminar archivo → `cli.py rm archivo`
