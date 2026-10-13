#ROL 3 — Datos y Búsqueda Semántica
#Responsable: Maximiliano Orellana

#Este script hace tres cosas en orden:
#  1. Lee los PDFs y .txt de data/raw/ y los fragmenta
#     (avisa de los documentos sin texto, que necesitan OCR)
#  2. Guarda cada fragmento en SQLite vía crud.py (fuente de verdad)
#  3. Genera embeddings y los carga en ChromaDB

#También expone procesar_un_documento() para reindexar un solo archivo;
#lo llama el endpoint /reindexar desde n8n.

#Ejecutar con (desde la raíz del proyecto):
#    python -m src.ingestion.pipeline

#Dependencias:
#    pip install chromadb langchain langchain-community sentence-transformers pypdf

import hashlib
import importlib
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from langchain_community.document_loaders import PyPDFLoader, TextLoader

from src.database.crud import (
    eliminar_por_documento,
    get_connection,
    inicializar_db,
    insertar_fragmento,
)

try:
    splitter_module = importlib.import_module("langchain_text_splitters")
except ModuleNotFoundError:
    splitter_module = importlib.import_module("langchain.text_splitter")

RecursiveCharacterTextSplitter = splitter_module.RecursiveCharacterTextSplitter

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CARPETA_DOCS = BASE_DIR / "data" / "raw"
CARPETA_CHROMA = BASE_DIR / "data" / "chroma_db"
COLECCION = "normativas_unlar"
EXTENSIONES = (".pdf", ".txt")

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
MODELO_EMBEDDINGS = "paraphrase-multilingual-MiniLM-L12-v2"
LOTE = 50
PALABRAS_ADMINISTRATIVAS = ["licencia", "compra", "contratacion"]


def listar_archivos():
    CARPETA_DOCS.mkdir(parents=True, exist_ok=True)
    return sorted(
        f.name for f in CARPETA_DOCS.iterdir() if f.suffix.lower() in EXTENSIONES
    )


def clasificar_audiencia(nombre_archivo):
    nombre = nombre_archivo.lower()
    if any(palabra in nombre for palabra in PALABRAS_ADMINISTRATIVAS):
        return "administrativo"
    return "academico"


def crear_tabla_documentos(conexion):
    conexion.execute(
        """
        CREATE TABLE IF NOT EXISTS documentos (
            nombre TEXT PRIMARY KEY,
            hash TEXT NOT NULL,
            fecha_actualizacion TEXT NOT NULL
        )
        """
    )
    conexion.commit()


def calcular_hash_archivo(ruta):
    with open(ruta, "rb") as archivo:
        return hashlib.sha256(archivo.read()).hexdigest()


def guardar_hash_documento(nombre_archivo, ruta):
    with closing(get_connection()) as conexion:
        crear_tabla_documentos(conexion)
        conexion.execute(
            """
            INSERT INTO documentos (nombre, hash, fecha_actualizacion)
            VALUES (?, ?, ?)
            ON CONFLICT(nombre) DO UPDATE SET
                hash = excluded.hash,
                fecha_actualizacion = excluded.fecha_actualizacion
            """,
            (
                nombre_archivo,
                calcular_hash_archivo(ruta),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conexion.commit()


def documento_sin_cambios(nombre_archivo, ruta):
    with closing(get_connection()) as conexion:
        crear_tabla_documentos(conexion)
        fila = conexion.execute(
            "SELECT hash FROM documentos WHERE nombre = ?", (nombre_archivo,)
        ).fetchone()
        tiene_fragmentos = conexion.execute(
            "SELECT 1 FROM fragmentos WHERE documento = ? LIMIT 1", (nombre_archivo,)
        ).fetchone()
    return bool(fila and tiene_fragmentos and fila["hash"] == calcular_hash_archivo(ruta))


def fragmentar_un_archivo(ruta):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " "],
    )
    if Path(ruta).suffix.lower() == ".pdf":
        paginas = PyPDFLoader(str(ruta)).load()
    else:
        paginas = TextLoader(str(ruta), encoding="utf-8").load()
    return splitter.split_documents(paginas)


def obtener_coleccion():
    CARPETA_CHROMA.mkdir(parents=True, exist_ok=True)
    emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=MODELO_EMBEDDINGS
    )
    cliente = chromadb.PersistentClient(path=str(CARPETA_CHROMA))
    return cliente.get_or_create_collection(
        name=COLECCION,
        embedding_function=emb_fn,
        metadata={"hnsw:space": "cosine"},
    )


def guardar_en_sqlite(trozos, nombre_archivo):
    audiencia = clasificar_audiencia(nombre_archivo)
    nuevos = []
    for trozo in trozos:
        texto = trozo.page_content.strip()
        if not texto:
            continue
        pagina = str(trozo.metadata.get("page", "N/A"))
        hash_texto = hashlib.md5(texto.encode()).hexdigest()
        insertado = insertar_fragmento(
            hash_id=hash_texto,
            texto=texto,
            documento=nombre_archivo,
            pagina=pagina,
            articulo="",
            audiencia=audiencia,
        )
        if insertado is not None:
            nuevos.append(
                {
                    "hash": hash_texto,
                    "texto": texto,
                    "documento": nombre_archivo,
                    "pagina": pagina,
                    "articulo": "",
                    "audiencia": audiencia,
                }
            )
    return nuevos


def cargar_en_chromadb(coleccion, fragmentos_nuevos):
    for inicio in range(0, len(fragmentos_nuevos), LOTE):
        lote = fragmentos_nuevos[inicio : inicio + LOTE]
        coleccion.upsert(
            ids=[f["hash"] for f in lote],
            documents=[f["texto"] for f in lote],
            metadatas=[
                {
                    "documento": f["documento"],
                    "pagina": f["pagina"],
                    "articulo": f["articulo"],
                    "audiencia": f["audiencia"],
                }
                for f in lote
            ],
        )


def procesar_un_documento(nombre_archivo, forzar=True):
    ruta = CARPETA_DOCS / nombre_archivo
    if not ruta.exists():
        raise FileNotFoundError(f"No existe {ruta}")
    if ruta.suffix.lower() not in EXTENSIONES:
        raise ValueError(f"Formato no soportado: {ruta.suffix}")

    inicializar_db()
    if not forzar and documento_sin_cambios(nombre_archivo, ruta):
        print(f"Sin cambios: {nombre_archivo}")
        return 0

    coleccion = obtener_coleccion()
    eliminar_por_documento(nombre_archivo)
    coleccion.delete(where={"documento": nombre_archivo})

    trozos = fragmentar_un_archivo(ruta)
    nuevos = guardar_en_sqlite(trozos, nombre_archivo)
    cargar_en_chromadb(coleccion, nuevos)
    guardar_hash_documento(nombre_archivo, ruta)
    print(f"Procesado: {nombre_archivo} -> {len(nuevos)} fragmentos")
    return len(nuevos)


def main():
    archivos = listar_archivos()
    if not archivos:
        print(f"No hay archivos .pdf o .txt en {CARPETA_DOCS}")
        return
    total = 0
    for archivo in archivos:
        try:
            total += procesar_un_documento(archivo, forzar=False)
        except Exception as error:
            print(f"Error al procesar {archivo}: {error}")
    print(f"Ingesta completada. Fragmentos nuevos: {total}")


if __name__ == "__main__":
    main()