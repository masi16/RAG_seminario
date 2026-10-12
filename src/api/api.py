"""
api.py
======
API REST para conectar el motor de Búsqueda Híbrida (BM25 + ChromaDB + RRF
sobre SQLite) con n8n y Streamlit.

Ejecutar con (desde la raíz del proyecto):
    uvicorn src.api.api:app --reload --host 0.0.0.0 --port 8000

Probar en el navegador:
    http://localhost:8000/docs
"""
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.ingestion.pipeline import DB_SQLITE, procesar_un_documento
from src.search.fusion_rrf import busqueda_hibrida

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


class PeticionReindexar(BaseModel):
    nombre_documento: str


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
        raise HTTPException(
            status_code=400, detail="La consulta no puede estar vacía."
        )
    try:
        resultados = busqueda_hibrida(
            peticion.consulta, k=peticion.k, audiencia=peticion.audiencia
        )
        return {
            "estado": "exito",
            "total_resultados": len(resultados),
            "resultados": resultados,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documentos/hashes")
def obtener_hashes():
    if not DB_SQLITE.exists():
        return {}
    conexion = sqlite3.connect(DB_SQLITE)
    try:
        cursor = conexion.execute("SELECT nombre, hash FROM documentos")
        return dict(cursor.fetchall())
    except sqlite3.OperationalError:
        return {}  # la tabla documentos todavía no existe
    finally:
        conexion.close()


@app.post("/reindexar")
def reindexar(peticion: PeticionReindexar):
    try:
        cantidad = procesar_un_documento(peticion.nombre_documento)
        return {
            "estado": "exito",
            "documento": peticion.nombre_documento,
            "fragmentos_indexados": cantidad,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))