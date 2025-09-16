#!/usr/bin/env python3
import sqlite3, os

DB_PATH = "storage.db"

# Remove existing DB? comentarlo si no quieres sobreescribir
# if os.path.exists(DB_PATH):
#     os.remove(DB_PATH)

os.makedirs(".", exist_ok=True)
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Tablas mínimas compatibles con tus snippets
c.execute("""
CREATE TABLE IF NOT EXISTS directories(
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id INTEGER,
    owner TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS files(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT,
    filename TEXT,
    size INTEGER,
    hash TEXT,
    metadata TEXT,
    directory_id INTEGER
)
""")

# Asegurar existencia del root (id = 1)
cur = c.execute("SELECT id FROM directories WHERE id = 1")
if cur.fetchone() is None:
    c.execute("INSERT INTO directories(id, name, parent_id, owner) VALUES (?, ?, ?, ?)",
              (1, '/', None, 'root'))
    print("Inserted root directory id=1 '/'")
else:
    print("Root directory already exists")

conn.commit()
conn.close()
print("DB created/updated at:", os.path.abspath(DB_PATH))
