"""
api.py
======
API REST para conectar el pipeline de Búsqueda Híbrida (RRF + SQLite) con n8n y Streamlit.
Levanta un servidor local que recibe consultas en JSON y devuelve los fragmentos más relevantes.

Ejecutar con:
    uvicorn src.api.api:app --reload --port 8000
    (o desde la carpeta api: uvicorn api:app --reload --port 8000)

Probar en el navegador:
    http://localhost:8000/docs
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Importamos la búsqueda híbrida que combina BM25, ChromaDB y CRUD de SQLite
try:
    from src.search.fusion_rrf import busqueda_hibrida
except ImportError:
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
    consulta: str
    k: int = Field(default=4, alias="top_k")  # Compatible con k y top_k
    audiencia: str = "todos"

    class Config:
        populate_by_name = True


@app.get("/")
def estado():
    return {
        "estado": "activo",
        "servicio": "Motor RAG UNLaR (Búsqueda Híbrida)",
        "version": "1.0.0"
    }


@app.post("/buscar")
def buscar_documentos(peticion: PeticionBusqueda):
    if not peticion.consulta.strip():
        raise HTTPException(
            status_code=400, detail="La consulta no puede estar vacía."
        )

    try:
        # Ejecuta BM25 + ChromaDB + RRF y recupera los textos desde SQLite
        fragmentos_encontrados = busqueda_hibrida(
            consulta=peticion.consulta,
            k=peticion.k
        )

        return {
            "estado": "exito",
            "total_resultados": len(fragmentos_encontrados),
            "resultados": fragmentos_encontrados,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en la búsqueda híbrida: {str(e)}")
