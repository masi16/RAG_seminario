"""
rol3_sqlite_chroma.py
=====================
ROL 3 — Datos y Búsqueda Semántica
Responsable: Maximiliano Orellana

Este script hace tres cosas en orden:
  1. Lee los PDFs de documentos_unlar/ y los fragmenta
  2. Guarda cada fragmento en SQLite (fuente de verdad)
  3. Genera embeddings y los carga en ChromaDB

Ejecutar con:
    python rol3_sqlite_chroma.py

Dependencias:
    pip install chromadb langchain langchain-community
                sentence-transformers pypdf
"""

import os
import sqlite3
import hashlib
import importlib
import chromadb

from langchain_community.document_loaders import PyPDFLoader
from chromadb.utils import embedding_functions

try:
    splitter_module = importlib.import_module("langchain_text_splitters")
except ModuleNotFoundError:
    splitter_module = importlib.import_module("langchain.text_splitter")

RecursiveCharacterTextSplitter = splitter_module.RecursiveCharacterTextSplitter


# ─────────────────────────────────────────────────────────────
# CONFIGURACIÓN — podés cambiar estos valores si hace falta
# ─────────────────────────────────────────────────────────────

CARPETA_DOCS   = "documentos_unlar"   # donde están los PDFs
CARPETA_CHROMA = "chromadb_unlar"     # donde ChromaDB guarda sus datos
DB_SQLITE      = "sqlite_unlar.db"    # archivo de base de datos
COLECCION      = "normativas_unlar"   # nombre de la colección en ChromaDB

# Tamaño de cada fragmento en caracteres
CHUNK_SIZE    = 500
CHUNK_OVERLAP = 50

# Modelo de embeddings en español (se descarga automáticamente la primera vez)
MODELO_EMBEDDINGS = "paraphrase-multilingual-MiniLM-L12-v2"


# ─────────────────────────────────────────────────────────────
# PASO 1 — LEER Y FRAGMENTAR LOS PDFs
# ─────────────────────────────────────────────────────────────

def cargar_y_fragmentar():
    """
    Lee todos los PDFs de la carpeta documentos_unlar/
    y los divide en fragmentos pequeños.
    Devuelve una lista de fragmentos listos para procesar.
    """
    print("\n[PASO 1] Leyendo y fragmentando PDFs...")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " "]
    )

    fragmentos = []
    archivos = [f for f in os.listdir(CARPETA_DOCS)
                if f.endswith(".pdf")]

    if not archivos:
        print("  No se encontraron PDFs en documentos_unlar/")
        print("  Guardá al menos un PDF y volvé a ejecutar.")
        return []

    for archivo in archivos:
        ruta = os.path.join(CARPETA_DOCS, archivo)
        print(f"  Procesando: {archivo}")
        try:
            loader = PyPDFLoader(ruta)
            paginas = loader.load()
            trozos = splitter.split_documents(paginas)
            fragmentos.extend(trozos)
            print(f"  → {len(trozos)} fragmentos generados")
        except Exception as e:
            print(f"  Error al leer {archivo}: {e}")

    print(f"\n  Total fragmentos: {len(fragmentos)}")
    return fragmentos


# ─────────────────────────────────────────────────────────────
# PASO 2 — GUARDAR EN SQLITE
# ─────────────────────────────────────────────────────────────

def crear_tabla_sqlite(conexion):
    """
    Crea la tabla fragmentos en SQLite si no existe.
    Esta tabla es la fuente de verdad del corpus.
    """
    conexion.execute("""
        CREATE TABLE IF NOT EXISTS fragmentos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            hash        TEXT UNIQUE,        -- hash del contenido (evita duplicados)
            texto       TEXT NOT NULL,      -- el fragmento de texto
            documento   TEXT NOT NULL,      -- nombre del PDF de origen
            pagina      TEXT NOT NULL,      -- número de página
            audiencia   TEXT DEFAULT 'general'  -- academico / administrativo / general
        )
    """)
    conexion.commit()
    print("  Tabla SQLite lista")


def determinar_audiencia(nombre_archivo):
    """
    Determina si el documento es académico o administrativo
    basándose en el nombre del archivo.
    """
    nombre = nombre_archivo.lower()
    palabras_admin = ["licencia", "compra", "contratacion",
                      "estructura", "autoridad", "ordenanza"]
    for palabra in palabras_admin:
        if palabra in nombre:
            return "administrativo"
    return "academico"


def guardar_en_sqlite(fragmentos):
    """
    Guarda cada fragmento en SQLite.
    Usa un hash del contenido para no duplicar fragmentos
    si el script se ejecuta más de una vez.
    Devuelve solo los fragmentos nuevos (no duplicados).
    """
    print("\n[PASO 2] Guardando fragmentos en SQLite...")

    conexion = sqlite3.connect(DB_SQLITE)
    crear_tabla_sqlite(conexion)

    nuevos = 0
    duplicados = 0
    fragmentos_nuevos = []

    for frag in fragmentos:
        texto    = frag.page_content.strip()
        fuente   = frag.metadata.get("source", "desconocido")
        pagina   = str(frag.metadata.get("page", "N/A"))
        nombre   = os.path.basename(fuente)
        audiencia = determinar_audiencia(nombre)

        # Hash del texto para detectar duplicados
        hash_texto = hashlib.md5(texto.encode()).hexdigest()

        try:
            conexion.execute("""
                INSERT INTO fragmentos (hash, texto, documento, pagina, audiencia)
                VALUES (?, ?, ?, ?, ?)
            """, (hash_texto, texto, nombre, pagina, audiencia))
            nuevos += 1
            fragmentos_nuevos.append({
                "hash": hash_texto,
                "texto": texto,
                "documento": nombre,
                "pagina": pagina,
                "audiencia": audiencia
            })
        except sqlite3.IntegrityError:
            # El fragmento ya existe (mismo hash), se saltea
            duplicados += 1

    conexion.commit()
    conexion.close()

    print(f"  Fragmentos nuevos guardados: {nuevos}")
    if duplicados:
        print(f"  Duplicados salteados: {duplicados}")
    print(f"  Base de datos: {DB_SQLITE}")

    return fragmentos_nuevos


def ver_sqlite():
    """
    Muestra un resumen de lo que hay en SQLite.
    """
    conexion = sqlite3.connect(DB_SQLITE)
    cursor = conexion.execute("""
        SELECT audiencia, COUNT(*) as total
        FROM fragmentos
        GROUP BY audiencia
    """)
    print("\n  Resumen SQLite:")
    for fila in cursor.fetchall():
        print(f"  → {fila[0]}: {fila[1]} fragmentos")
    conexion.close()


# ─────────────────────────────────────────────────────────────
# PASO 3 — GENERAR EMBEDDINGS Y CARGAR EN CHROMADB
# ─────────────────────────────────────────────────────────────

def cargar_en_chromadb(fragmentos_nuevos):
    """
    Toma los fragmentos nuevos de SQLite y los carga en ChromaDB
    con sus embeddings generados por sentence-transformers.
    Solo procesa fragmentos que no estén ya en ChromaDB
    (usando el hash como ID único).
    """
    print("\n[PASO 3] Cargando embeddings en ChromaDB...")

    if not fragmentos_nuevos:
        print("  No hay fragmentos nuevos para indexar.")
        return

    # Modelo de embeddings multilingüe (funciona bien en español)
    emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=MODELO_EMBEDDINGS
    )

    # ChromaDB persistente (guarda en disco en chromadb_unlar/)
    cliente = chromadb.PersistentClient(path=CARPETA_CHROMA)
    coleccion = cliente.get_or_create_collection(
        name=COLECCION,
        embedding_function=emb_fn,
        metadata={"hnsw:space": "cosine"}
    )

    # Preparar datos para insertar
    textos    = [f["texto"]     for f in fragmentos_nuevos]
    ids       = [f["hash"]      for f in fragmentos_nuevos]
    metadatos = [
        {
            "documento": f["documento"],
            "pagina":    f["pagina"],
            "audiencia": f["audiencia"]
        }
        for f in fragmentos_nuevos
    ]

    # Insertar en lotes de 50 para no sobrecargar la memoria
    LOTE = 50
    total = len(textos)
    for i in range(0, total, LOTE):
        fin = min(i + LOTE, total)
        coleccion.add(
            documents=textos[i:fin],
            ids=ids[i:fin],
            metadatas=metadatos[i:fin]
        )
        print(f"  Indexados {fin}/{total} fragmentos...")

    print(f"\n  ChromaDB lista en: {CARPETA_CHROMA}/")
    print(f"  Colección: '{COLECCION}'")
    print(f"  Total en ChromaDB: {coleccion.count()} fragmentos")

    return coleccion


# ─────────────────────────────────────────────────────────────
# PRUEBA DE CONSULTA
# ─────────────────────────────────────────────────────────────

def probar_consulta(consulta="¿Cuántas materias puedo adeudar para rendir final?"):
    """
    Hace una consulta de prueba a ChromaDB para verificar
    que la indexación funcionó correctamente.
    """
    print(f"\n[PRUEBA] Consulta: '{consulta}'")

    emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=MODELO_EMBEDDINGS
    )
    cliente = chromadb.PersistentClient(path=CARPETA_CHROMA)

    try:
        coleccion = cliente.get_collection(
            name=COLECCION,
            embedding_function=emb_fn
        )
    except Exception:
        print("  ChromaDB vacía. Ejecutá el script completo primero.")
        return

    resultados = coleccion.query(
        query_texts=[consulta],
        n_results=3
    )

    print("\n  Fragmentos más relevantes encontrados:")
    for i, (doc, meta) in enumerate(zip(
        resultados["documents"][0],
        resultados["metadatas"][0]
    )):
        print(f"\n  --- Fragmento {i+1} ---")
        print(f"  Documento: {meta['documento']} | "
              f"Página: {meta['pagina']} | "
              f"Audiencia: {meta['audiencia']}")
        print(f"  {doc[:250]}{'...' if len(doc) > 250 else ''}")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  ROL 3 — Datos y Búsqueda Semántica")
    print("  Proyecto RAG UNLAR")
    print("=" * 55)

    # Paso 1: leer y fragmentar PDFs
    fragmentos = cargar_y_fragmentar()
    if not fragmentos:
        return

    # Paso 2: guardar en SQLite
    fragmentos_nuevos = guardar_en_sqlite(fragmentos)
    ver_sqlite()

    # Paso 3: cargar en ChromaDB
    cargar_en_chromadb(fragmentos_nuevos)

    # Prueba final
    probar_consulta()

    print("\n" + "=" * 55)
    print("  Proceso completado.")
    print("  Entregá a Persona 2:")
    print(f"  → {DB_SQLITE}")
    print(f"  → carpeta {CARPETA_CHROMA}/")
    print("=" * 55)


if __name__ == "__main__":
    main()
