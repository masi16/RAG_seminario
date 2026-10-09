"""
ROL 3 — Datos y Búsqueda Semántica
Responsable: Maximiliano Orellana

Este script hace tres cosas en orden:
  1. Lee los PDFs de documentos_unlar/ y los fragmenta
  2. Guarda cada fragmento en SQLite (fuente de verdad)
  3. Genera embeddings y los carga en ChromaDB

Ejecutar con:
    python pipeline.py

Dependencias:
    pip install chromadb langchain langchain-community
                sentence-transformers pypdf
"""
import hashlib
import importlib
import os
from pathlib import Path
import sqlite3
import chromadb
from chromadb.utils import embedding_functions
from langchain_community.document_loaders import PyPDFLoader

try:
  splitter_module = importlib.import_module("langchain_text_splitters")
except ModuleNotFoundError:
  splitter_module = importlib.import_module("langchain.text_splitter")

RecursiveCharacterTextSplitter = splitter_module.RecursiveCharacterTextSplitter

# Rutas estándar del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CARPETA_DOCS = BASE_DIR / "data" / "raw"
DB_SQLITE = BASE_DIR / "data" / "sqlite" / "corpus.db"
CARPETA_CHROMA = BASE_DIR / "data" / "chroma_db"
COLECCION = "normativas_unlar"

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
MODELO_EMBEDDINGS = "paraphrase-multilingual-MiniLM-L12-v2"


def cargar_y_fragmentar():
  splitter = RecursiveCharacterTextSplitter(
      chunk_size=CHUNK_SIZE,
      chunk_overlap=CHUNK_OVERLAP,
      separators=["\n\n", "\n", ".", " "],
  )
  fragmentos = []
  if not CARPETA_DOCS.exists():
    CARPETA_DOCS.mkdir(parents=True, exist_ok=True)

  archivos = [f for f in os.listdir(CARPETA_DOCS) if f.endswith(".pdf")]
  if not archivos:
    print(f"No hay PDFs en {CARPETA_DOCS}")
    return []

  for archivo in archivos:
    ruta = CARPETA_DOCS / archivo
    try:
      loader = PyPDFLoader(str(ruta))
      paginas = loader.load()
      trozos = splitter.split_documents(paginas)
      fragmentos.extend(trozos)
      print(f"Procesado: {archivo} -> {len(trozos)} fragmentos")
    except Exception as e:
      print(f"Error al leer {archivo}: {e}")
  return fragmentos


def guardar_en_sqlite(fragmentos):
  DB_SQLITE.parent.mkdir(parents=True, exist_ok=True)
  conexion = sqlite3.connect(DB_SQLITE)
  conexion.execute("""
        CREATE TABLE IF NOT EXISTS fragmentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hash TEXT UNIQUE,
            texto TEXT NOT NULL,
            documento TEXT NOT NULL,
            pagina TEXT NOT NULL,
            articulo TEXT DEFAULT '',
            audiencia TEXT DEFAULT 'general'
        )
    """)
  conexion.commit()

  fragmentos_nuevos = []
  for frag in fragmentos:
    texto = frag.page_content.strip()
    fuente = os.path.basename(frag.metadata.get("source", "desconocido"))
    pagina = str(frag.metadata.get("page", "N/A"))
    audiencia = (
        "administrativo"
        if any(
            p in fuente.lower()
            for p in ["licencia", "compra", "contratacion", "ordenanza"]
        )
        else "academico"
    )
    hash_texto = hashlib.md5(texto.encode()).hexdigest()

    try:
      conexion.execute(
          """
                INSERT INTO fragmentos (hash, texto, documento, pagina, articulo, audiencia)
                VALUES (?, ?, ?, ?, '', ?)
            """,
          (hash_texto, texto, fuente, pagina, audiencia),
      )
      fragmentos_nuevos.append({
          "hash": hash_texto,
          "texto": texto,
          "documento": fuente,
          "pagina": pagina,
          "articulo": "",
          "audiencia": audiencia,
      })
    except sqlite3.IntegrityError:
      pass

  conexion.commit()
  conexion.close()
  return fragmentos_nuevos


def cargar_en_chromadb(fragmentos_nuevos):
  if not fragmentos_nuevos:
    print("Sin fragmentos nuevos para indexar en Chroma.")
    return

  CARPETA_CHROMA.mkdir(parents=True, exist_ok=True)
  emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
      model_name=MODELO_EMBEDDINGS
  )
  cliente = chromadb.PersistentClient(path=str(CARPETA_CHROMA))
  coleccion = cliente.get_or_create_collection(
      name=COLECCION,
      embedding_function=emb_fn,
      metadata={"hnsw:space": "cosine"},
  )

  textos = [f["texto"] for f in fragmentos_nuevos]
  ids = [f["hash"] for f in fragmentos_nuevos]
  metadatos = [{
      "documento": f["documento"],
      "pagina": f["pagina"],
      "articulo": f["articulo"],
      "audiencia": f["audiencia"],
  } for f in fragmentos_nuevos]

  LOTE = 50
  for i in range(0, len(textos), LOTE):
    fin = min(i + LOTE, len(textos))
    coleccion.add(
        documents=textos[i:fin], ids=ids[i:fin], metadatas=metadatos[i:fin]
    )


def main():
  frags = cargar_y_fragmentar()
  if frags:
    nuevos = guardar_en_sqlite(frags)
    cargar_en_chromadb(nuevos)
    print("Ingesta e indexación completadas con éxito.")


if __name__ == "__main__":
  main()