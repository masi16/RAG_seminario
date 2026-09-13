"""
api.py
======
API REST para conectar ChromaDB con n8n.
Levanta un servidor local que recibe consultas en JSON
y devuelve los fragmentos más relevantes.

Ejecutar con:
    uvicorn api:app --reload --port 8000

Probar en el navegador:
    http://localhost:8000/docs
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import chromadb
from chromadb.utils import embedding_functions

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────

CARPETA_CHROMA    = "chromadb_unlar"
COLECCION         = "normativas_unlar"
MODELO_EMBEDDINGS = "paraphrase-multilingual-MiniLM-L12-v2"

# ─────────────────────────────────────────────
# INICIALIZAR APP
# ─────────────────────────────────────────────

app = FastAPI(
    title="API RAG UNLaR - Búsqueda Semántica",
    description="Conecta ChromaDB con n8n para el sistema RAG de la UNLaR",
    version="1.0.0"
)

# CORS — necesario para que n8n pueda hacer peticiones
# desde un puerto distinto al de esta API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# CONECTAR CHROMADB AL INICIAR
# ─────────────────────────────────────────────

coleccion = None  # variable global

try:
    cliente = chromadb.PersistentClient(path=CARPETA_CHROMA)
    emb_fn  = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=MODELO_EMBEDDINGS
    )
    coleccion = cliente.get_collection(
        name=COLECCION,
        embedding_function=emb_fn
    )
    print("✅ ChromaDB conectada correctamente.")
    print(f"   Fragmentos indexados: {coleccion.count()}")
except Exception as e:
    print(f"⚠️  Error al conectar con ChromaDB: {e}")
    print("   Ejecutá rol3_sqlite_chroma.py primero para crear la BD.")

# ─────────────────────────────────────────────
# MODELOS DE DATOS
# ─────────────────────────────────────────────

class PeticionBusqueda(BaseModel):
    consulta: str
    top_k: int = 3  # cantidad de fragmentos a devolver

# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@app.get("/")
def estado():
    """
    Ruta de salud — n8n la usa para verificar que la API esté activa.
    También muestra cuántos fragmentos están indexados.
    """
    if coleccion is None:
        return {
            "estado": "error",
            "mensaje": "ChromaDB no conectada. Ejecutá rol3_sqlite_chroma.py primero."
        }
    return {
        "estado": "activo",
        "mensaje": "API RAG UNLaR funcionando correctamente",
        "fragmentos_indexados": coleccion.count()
    }


@app.post("/buscar")
def buscar_documentos(peticion: PeticionBusqueda):
    """
    Recibe una consulta en texto y devuelve los fragmentos
    más relevantes de ChromaDB en formato JSON.

    N8N llama a este endpoint con:
    {
        "consulta": "¿Cuántas materias puedo adeudar?",
        "top_k": 3
    }
    """
    # Verificar que ChromaDB esté conectada
    if coleccion is None:
        raise HTTPException(
            status_code=503,
            detail="ChromaDB no disponible. Ejecutá rol3_sqlite_chroma.py primero."
        )

    # Verificar que no esté vacía
    if coleccion.count() == 0:
        raise HTTPException(
            status_code=503,
            detail="ChromaDB está vacía. Ejecutá rol3_sqlite_chroma.py primero."
        )

    # Validar que la consulta no esté vacía
    if not peticion.consulta.strip():
        raise HTTPException(
            status_code=400,
            detail="La consulta no puede estar vacía."
        )

    try:
        # Búsqueda semántica en ChromaDB
        resultados = coleccion.query(
            query_texts=[peticion.consulta],
            n_results=peticion.top_k
        )

        # Formatear respuesta limpia para n8n
        fragmentos_encontrados = []
        for doc, meta in zip(
            resultados["documents"][0],
            resultados["metadatas"][0]
        ):
            fragmentos_encontrados.append({
                "texto":             doc,
                "documento_origen":  meta.get("documento", "desconocido"),
                "pagina":            meta.get("pagina", "N/A"),
                "audiencia":         meta.get("audiencia", "general")
            })

        return {
            "estado":            "exito",
            "consulta_original": peticion.consulta,
            "total_resultados":  len(fragmentos_encontrados),
            "resultados":        fragmentos_encontrados
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
