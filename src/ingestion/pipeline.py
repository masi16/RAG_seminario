"""
ROL 3 — Datos y Búsqueda Semántica
Responsable: Maximiliano Orellana

Este script hace tres cosas en orden:
  1. Lee los PDFs y .txt de data/raw/ y los fragmenta
     (avisa de los documentos sin texto, que necesitan OCR)
  2. Guarda cada fragmento en SQLite vía crud.py (fuente de verdad)
  3. Genera embeddings y los carga en ChromaDB

También expone procesar_un_documento() para reindexar un solo archivo;
lo llama el endpoint /reindexar desde n8n.

Ejecutar con (desde la raíz del proyecto):
    python -m src.ingestion.pipeline

Dependencias:
    pip install chromadb langchain langchain-community
                sentence-transformers pypdf
"""
import hashlib
import importlib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from langchain_community.document_loaders import PyPDFLoader, TextLoader

from src.database.crud import (
    DB_PATH,
    eliminar_por_documento,
    inicializar_db,
    insertar_fragmento,
)

try:
  splitter_module = importlib.import_module("langchain_text_splitters")
except ModuleNotFoundError:
  splitter_module = importlib.import_module("langchain.text_splitter")

RecursiveCharacterTextSplitter = splitter_module.RecursiveCharacterTextSplitter

# Rutas estándar del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CARPETA_DOCS = BASE_DIR / "data" / "raw"
CARPETA_CHROMA = BASE_DIR / "data" / "chroma_db"
DB_SQLITE = DB_PATH  # misma base que usan crud.py y el índice BM25
COLECCION = "normativas_unlar"

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
MODELO_EMBEDDINGS = "paraphrase-multilingual-MiniLM-L12-v2"

EXTENSIONES = (".pdf", ".txt")
MIN_CARACTERES = 100  # por debajo de esto se considera un escaneo sin texto

_coleccion = None


# ---------------------------------------------------------------- lectura

def listar_documentos():
  CARPETA_DOCS.mkdir(parents=True, exist_ok=True)
  return sorted(
      f for f in os.listdir(CARPETA_DOCS) if f.lower().endswith(EXTENSIONES)
  )


def cargar_paginas(ruta):
  if ruta.suffix.lower() == ".txt":
    return TextLoader(str(ruta), encoding="utf-8").load()
  return PyPDFLoader(str(ruta)).load()


def crear_splitter():
  return RecursiveCharacterTextSplitter(
      chunk_size=CHUNK_SIZE,
      chunk_overlap=CHUNK_OVERLAP,
      separators=["\n\n", "\n", ".", " "],
  )


def tiene_texto(paginas):
  return sum(len(p.page_content.strip()) for p in paginas) >= MIN_CARACTERES


def clasificar_audiencia(nombre_documento):
  palabras = ["licencia", "compra", "contratacion", "ordenanza"]
  if any(p in nombre_documento.lower() for p in palabras):
    return "administrativo"
  return "academico"


def cargar_y_fragmentar():
  splitter = crear_splitter()
  fragmentos = []
  archivos = listar_documentos()
  if not archivos:
    print(f"No hay documentos en {CARPETA_DOCS}")
    return []

  omitidos = []
  for archivo in archivos:
    try:
      paginas = cargar_paginas(CARPETA_DOCS / archivo)
      if not tiene_texto(paginas):
        print(f"⚠️ SIN TEXTO: {archivo} parece un escaneo (necesita OCR). Se omite.")
        omitidos.append(archivo)
        continue
      trozos = splitter.split_documents(paginas)
      fragmentos.extend(trozos)
      print(f"Procesado: {archivo} -> {len(trozos)} fragmentos")
    except Exception as e:
      print(f"Error al leer {archivo}: {e}")

  if omitidos:
    print(f"\n⚠️ {len(omitidos)} documento(s) omitidos por falta de texto: {omitidos}")
  return fragmentos


def fragmentar_un_archivo(ruta):
  """Igual que cargar_y_fragmentar, pero para un solo documento."""
  paginas = cargar_paginas(ruta)
  if not tiene_texto(paginas):
    raise ValueError(
        f"{ruta.name} no tiene texto extraíble (¿es un escaneo? hace falta OCR)"
    )
  return crear_splitter().split_documents(paginas)


# ----------------------------------------------------------------- SQLite

def guardar_en_sqlite(fragmentos):
  """Inserta vía crud.py. Devuelve solo los fragmentos que eran nuevos."""
  inicializar_db()
  nuevos = []
  for frag in fragmentos:
    texto = frag.page_content.strip()
    if not texto:
      continue
    fuente = os.path.basename(frag.metadata.get("source", "desconocido"))
    pagina = str(frag.metadata.get("page", "N/A"))
    audiencia = clasificar_audiencia(fuente)
    hash_texto = hashlib.md5(texto.encode()).hexdigest()

    if insertar_fragmento(hash_texto, texto, fuente, pagina, "", audiencia) is not None:
      nuevos.append({
          "hash": hash_texto,
          "texto": texto,
          "documento": fuente,
          "pagina": pagina,
          "articulo": "",
          "audiencia": audiencia,
      })
  return nuevos


def crear_tabla_documentos(conexion):
  conexion.execute("""
        CREATE TABLE IF NOT EXISTS documentos (
            nombre TEXT PRIMARY KEY,
            hash TEXT NOT NULL,
            fecha_actualizacion TEXT NOT NULL
        )
    """)
  conexion.commit()


def calcular_hash_archivo(ruta):
  with open(ruta, "rb") as f:
    return hashlib.sha256(f.read()).hexdigest()


def guardar_hash_documento(conexion, ruta, nombre_archivo):
  conexion.execute(
      """INSERT INTO documentos (nombre, hash, fecha_actualizacion)
             VALUES (?, ?, ?)
             ON CONFLICT(nombre) DO UPDATE SET
                 hash = excluded.hash,
                 fecha_actualizacion = excluded.fecha_actualizacion""",
      (nombre_archivo, calcular_hash_archivo(ruta),
       datetime.now(timezone.utc).isoformat()),
  )
  conexion.commit()


def registrar_hashes(nombres):
  conexion = sqlite3.connect(DB_SQLITE)
  try:
    crear_tabla_documentos(conexion)
    for nombre in nombres:
      guardar_hash_documento(conexion, CARPETA_DOCS / nombre, nombre)
  finally:
    conexion.close()


# --------------------------------------------------------------- ChromaDB

def obtener_coleccion():
  global _coleccion
  if _coleccion is None:
    CARPETA_CHROMA.mkdir(parents=True, exist_ok=True)
    emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=MODELO_EMBEDDINGS
    )
    cliente = chromadb.PersistentClient(path=str(CARPETA_CHROMA))
    _coleccion = cliente.get_or_create_collection(
        name=COLECCION,
        embedding_function=emb_fn,
        metadata={"hnsw:space": "cosine"},
    )
  return _coleccion


def cargar_en_chromadb(fragmentos_nuevos):
  if not fragmentos_nuevos:
    print("Sin fragmentos nuevos para indexar en Chroma.")
    return

  coleccion = obtener_coleccion()
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


# ------------------------------------------------------------ re-ingesta

def procesar_un_documento(nombre_archivo):
  """
  Reprocesa un único documento: borra sus fragmentos viejos (SQLite + Chroma)
  e inserta los nuevos. Lo llama /reindexar desde n8n.
  Devuelve la cantidad de fragmentos nuevos indexados.
  """
  ruta = CARPETA_DOCS / nombre_archivo
  if not ruta.exists():
    raise FileNotFoundError(f"No existe {ruta}")

  # Fragmentar primero: si no tiene texto, falla antes de borrar nada
  trozos = fragmentar_un_archivo(ruta)

  inicializar_db()
  coleccion = obtener_coleccion()
  eliminar_por_documento(nombre_archivo)
  coleccion.delete(where={"documento": nombre_archivo})

  nuevos = guardar_en_sqlite(trozos)
  cargar_en_chromadb(nuevos)
  registrar_hashes([nombre_archivo])
  return len(nuevos)


# ------------------------------------------------------------------- main

def main():
  inicializar_db()
  frags = cargar_y_fragmentar()
  if frags:
    nuevos = guardar_en_sqlite(frags)
    cargar_en_chromadb(nuevos)

  # Hash de cada documento, para que n8n detecte cambios futuros
  registrar_hashes(listar_documentos())
  print("Ingesta e indexación completadas.")


if __name__ == "__main__":
  main()