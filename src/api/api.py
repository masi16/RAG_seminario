#API REST para conectar el motor de Búsqueda Híbrida (BM25 + ChromaDB + RRF
#sobre SQLite) con n8n y Streamlit.

#Ejecutar con (desde la raíz del proyecto):
#    uvicorn src.api.api:app --reload --host 0.0.0.0 --port 8000

#Probar en el navegador:
#    http://localhost:8000/docs

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

try:
    from src.search.bm25_db import reconstruir_indice
    from src.search.fusion_rrf import busqueda_hibrida
except ImportError:
    from bm25_db import reconstruir_indice
    from fusion_rrf import busqueda_hibrida

app = FastAPI(
    title="API RAG UNLaR - Búsqueda Híbrida",
    description="Conecta el motor de recuperación (BM25 + ChromaDB + SQLite) con n8n",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PeticionBusqueda(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    consulta: str
    k: int = Field(default=4, alias="top_k", ge=1, le=20)
    audiencia: str = "todos"


class PeticionReindexar(BaseModel):
    documento: str


@app.get("/")
def estado():
    return {
        "estado": "activo",
        "servicio": "Motor RAG UNLaR (Búsqueda Híbrida)",
        "version": "1.0.0",
    }


@app.post("/buscar")
def buscar_documentos(peticion: PeticionBusqueda):
    if not peticion.consulta.strip():
        raise HTTPException(status_code=400, detail="La consulta no puede estar vacía.")
    try:
        resultados = busqueda_hibrida(
            peticion.consulta, k=peticion.k, audiencia=peticion.audiencia
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))
    return {
        "estado": "exito",
        "total_resultados": len(resultados),
        "resultados": resultados,
    }


@app.post("/reindexar")
def reindexar_documento(peticion: PeticionReindexar):
    try:
        from src.ingestion.pipeline import procesar_un_documento

        insertados = procesar_un_documento(peticion.documento)
        total = reconstruir_indice()
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))
    return {
        "estado": "exito",
        "documento": peticion.documento,
        "fragmentos_insertados": insertados,
        "fragmentos_en_indice": total,
    }