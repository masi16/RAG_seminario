"""
Pipeline de ingesta de documentos para el motor RAG de la UNLaR.

Lee PDF y TXT desde data/raw/, los fragmenta, guarda los fragmentos en SQLite
y los indexa en ChromaDB. También permite reindexar un documento individual.

Ejecutar desde la raíz del proyecto:
    python -m src.ingestion.pipeline
"""
import hashlib
import importlib
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from langchain_community.document_loaders import PyPDFLoader, TextLoader

from src.database.crud import (
    DB_PATH,
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
DB_SQLITE = DB_PATH
COLECCION = "normativas_unlar"
EXTENSIONES = (".pdf", ".txt")
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
MIN_CARACTERES = 100
MODELO_EMBEDDINGS = "paraphrase-multilingual-MiniLM-L12-v2"
LOTE = 50
PALABRAS_ADMINISTRATIVAS = (
    "licencia",
    "compra",
    "contratacion",
    "ordenanza",
)

_coleccion = None


def listar_documentos():
    CARPETA_DOCS.mkdir(parents=True, exist_ok=True)
    return sorted(
        archivo.name
        for archivo in CARPETA_DOCS.iterdir()
        if archivo.is_file() and archivo.suffix.lower() in EXTENSIONES
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
    return sum(len(pagina.page_content.strip()) for pagina in paginas) >= MIN_CARACTERES


def clasificar_audiencia(nombre_documento):
    nombre = nombre_documento.lower()
    if any(palabra in nombre for palabra in PALABRAS_ADMINISTRATIVAS):
        return "administrativo"
    return "academico"


def fragmentar_un_archivo(ruta):
    paginas = cargar_paginas(ruta)
    if not tiene_texto(paginas):
        raise ValueError(
            f"{ruta.name} no tiene suficiente texto extraíble (¿es un escaneo? "
            "hace falta OCR)"
        )
    return crear_splitter().split_documents(paginas)


def cargar_y_fragmentar():
    fragmentos = []
    omitidos = []
    archivos = listar_documentos()
    if not archivos:
        print(f"No hay documentos en {CARPETA_DOCS}")
        return fragmentos

    splitter = crear_splitter()
    for archivo in archivos:
        try:
            paginas = cargar_paginas(CARPETA_DOCS / archivo)
            if not tiene_texto(paginas):
                print(f"Sin texto extraíble: {archivo} (posible escaneo; requiere OCR)")
                omitidos.append(archivo)
                continue
            trozos = splitter.split_documents(paginas)
            fragmentos.extend(trozos)
            print(f"Procesado: {archivo} -> {len(trozos)} fragmentos")
        except Exception as error:
            print(f"Error al leer {archivo}: {error}")

    if omitidos:
        print(f"Documentos omitidos por falta de texto: {omitidos}")
    return fragmentos


def guardar_en_sqlite(trozos, nombre_archivo=None):
    inicializar_db()
    audiencia = (
        clasificar_audiencia(nombre_archivo) if nombre_archivo is not None else None
    )
    nuevos = []

    for trozo in trozos:
        texto = trozo.page_content.strip()
        if not texto:
            continue
        documento = nombre_archivo or Path(
            trozo.metadata.get("source", "desconocido")
        ).name
        pagina = str(trozo.metadata.get("page", "N/A"))
        audiencia_fragmento = audiencia or clasificar_audiencia(documento)
        hash_texto = hashlib.md5(texto.encode("utf-8")).hexdigest()
        insertado = insertar_fragmento(
            hash_id=hash_texto,
            texto=texto,
            documento=documento,
            pagina=pagina,
            articulo="",
            audiencia=audiencia_fragmento,
        )
        if insertado is not None:
            nuevos.append(
                {
                    "hash": hash_texto,
                    "texto": texto,
                    "documento": documento,
                    "pagina": pagina,
                    "articulo": "",
                    "audiencia": audiencia_fragmento,
                }
            )
    return nuevos


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


def calcular_hash_archivo(ruta):
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def guardar_hash_documento(nombre_archivo, ruta):
    with get_connection() as conexion:
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
    with get_connection() as conexion:
        crear_tabla_documentos(conexion)
        fila = conexion.execute(
            "SELECT hash FROM documentos WHERE nombre = ?", (nombre_archivo,)
        ).fetchone()
        tiene_fragmentos = conexion.execute(
            "SELECT 1 FROM fragmentos WHERE documento = ? LIMIT 1",
            (nombre_archivo,),
        ).fetchone()
    return bool(
        fila
        and tiene_fragmentos
        and fila["hash"] == calcular_hash_archivo(ruta)
    )


def registrar_hashes(nombres):
    for nombre in nombres:
        ruta = CARPETA_DOCS / nombre
        if ruta.is_file():
            guardar_hash_documento(nombre, ruta)


def obtener_coleccion():
    global _coleccion
    if _coleccion is None:
        CARPETA_CHROMA.mkdir(parents=True, exist_ok=True)
        funcion_embeddings = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=MODELO_EMBEDDINGS
        )
        cliente = chromadb.PersistentClient(path=str(CARPETA_CHROMA))
        _coleccion = cliente.get_or_create_collection(
            name=COLECCION,
            embedding_function=funcion_embeddings,
            metadata={"hnsw:space": "cosine"},
        )
    return _coleccion


def cargar_en_chromadb(fragmentos_nuevos, coleccion=None):
    if not fragmentos_nuevos:
        return
    coleccion = coleccion or obtener_coleccion()
    for inicio in range(0, len(fragmentos_nuevos), LOTE):
        lote = fragmentos_nuevos[inicio : inicio + LOTE]
        coleccion.upsert(
            ids=[fragmento["hash"] for fragmento in lote],
            documents=[fragmento["texto"] for fragmento in lote],
            metadatas=[
                {
                    "documento": fragmento["documento"],
                    "pagina": fragmento["pagina"],
                    "articulo": fragmento["articulo"],
                    "audiencia": fragmento["audiencia"],
                }
                for fragmento in lote
            ],
        )


def procesar_un_documento(nombre_archivo, forzar=True):
    ruta = CARPETA_DOCS / nombre_archivo
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe un archivo en {ruta}")
    if ruta.suffix.lower() not in EXTENSIONES:
        raise ValueError(f"Formato no soportado: {ruta.suffix}")

    inicializar_db()
    if not forzar and documento_sin_cambios(nombre_archivo, ruta):
        print(f"Sin cambios: {nombre_archivo}")
        return 0

    trozos = fragmentar_un_archivo(ruta)
    coleccion = obtener_coleccion()
    eliminar_por_documento(nombre_archivo)
    coleccion.delete(where={"documento": nombre_archivo})

    nuevos = guardar_en_sqlite(trozos, nombre_archivo)
    cargar_en_chromadb(nuevos, coleccion)
    guardar_hash_documento(nombre_archivo, ruta)
    print(f"Procesado: {nombre_archivo} -> {len(nuevos)} fragmentos")
    return len(nuevos)


def main():
    total = 0
    for archivo in listar_documentos():
        try:
            total += procesar_un_documento(archivo, forzar=False)
        except Exception as error:
            print(f"Error al procesar {archivo}: {error}")
    print(f"Ingesta e indexación completadas. Fragmentos nuevos: {total}")


if __name__ == "__main__":
    main()
