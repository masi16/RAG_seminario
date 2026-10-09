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
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import chromadb
from chromadb.utils import embedding_functions

# Rutas relativas a la estructura del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CARPETA_CHROMA = str(BASE_DIR / "data" / "chroma_db")
COLECCION = "normativas_unlar"
MODELO_EMBEDDINGS = "paraphrase-multilingual-MiniLM-L12-v2"

app = FastAPI(
    title="API RAG UNLaR - Búsqueda Semántica",
    description="Conecta ChromaDB con n8n",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

coleccion = None

try:
  cliente = chromadb.PersistentClient(path=CARPETA_CHROMA)
  emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
      model_name=MODELO_EMBEDDINGS
  )
  coleccion = cliente.get_collection(name=COLECCION, embedding_function=emb_fn)
  print(f"✅ ChromaDB conectada. Fragmentos indexados: {coleccion.count()}")
except Exception as e:
  print(f"⚠️ ChromaDB no inicializada: {e}")


class PeticionBusqueda(BaseModel):
  consulta: str
  k: int = Field(default=4, alias="top_k")  # Compatible con k y top_k
  audiencia: str = "todos"

  class Config:
    populate_by_name = True


@app.get("/")
def estado():
  if coleccion is None:
    return {"estado": "error", "mensaje": "ChromaDB no conectada"}
  return {"estado": "activo", "fragmentos_indexados": coleccion.count()}


@app.post("/buscar")
def buscar_documentos(peticion: PeticionBusqueda):
  if coleccion is None or coleccion.count() == 0:
    raise HTTPException(status_code=503, detail="ChromaDB no disponible o vacía")

  if not peticion.consulta.strip():
    raise HTTPException(
        status_code=400, detail="La consulta no puede estar vacía."
    )

  try:
    filtros = None
    if peticion.audiencia and peticion.audiencia != "todos":
      filtros = {"audiencia": peticion.audiencia}

    resultados = coleccion.query(
        query_texts=[peticion.consulta],
        n_results=peticion.k,
        where=filtros if filtros else None,
    )

    fragmentos_encontrados = []
    if resultados["documents"] and resultados["documents"][0]:
      for doc, meta in zip(
          resultados["documents"][0], resultados["metadatas"][0]
      ):
        fragmentos_encontrados.append({
            "texto": doc,
            "documento": meta.get("documento", "desconocido"),
            "pagina": meta.get("pagina", "N/A"),
            "articulo": meta.get("articulo", ""),
            "audiencia": meta.get("audiencia", "general"),
        })

    return {
        "estado": "exito",
        "total_resultados": len(fragmentos_encontrados),
        "resultados": fragmentos_encontrados,
    }
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))