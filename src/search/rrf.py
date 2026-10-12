from pathlib import Path
from typing import List, Dict, Any

# 1. Import de BM25 (solo la función de búsqueda, ya no la lista 'fragmentos')
try:
    from src.search.bm25_docs import buscar_bm25
except ImportError:
    from bm25_docs import buscar_bm25

# 2. Import del CRUD de SQLite
from src.database.crud import leer_por_hashes

# 3. ChromaDB para reemplazar la simulación
import chromadb
from chromadb.utils import embedding_functions

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CARPETA_CHROMA = BASE_DIR / "data" / "chroma_db"
COLECCION_NOMBRE = "normativas_unlar"
MODELO_EMBEDDINGS = "paraphrase-multilingual-MiniLM-L12-v2"


def buscar_chromadb(consulta: str, k: int = 5, audiencia: str = "todos") -> List[Dict[str, Any]]:
    """Consulta semántica a ChromaDB devolviendo IDs y distancias."""
    try:
        cliente = chromadb.PersistentClient(path=str(CARPETA_CHROMA))
        emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=MODELO_EMBEDDINGS
        )
        coleccion = cliente.get_collection(
            name=COLECCION_NOMBRE,
            embedding_function=emb_fn
        )

        filtros = {"audiencia": audiencia} if audiencia != "todos" else None
        res = coleccion.query(
            query_texts=[consulta],
            n_results=k,
            where=filtros if filtros else None
        )

        ranking = []
        if res["ids"] and res["ids"][0]:
            distancias = res.get("distances", [[0.0] * len(res["ids"][0])])[0]
            for doc_id, dist in zip(res["ids"][0], distancias):
                ranking.append({"id": doc_id, "score": float(dist)})
        return ranking
    except Exception as e:
        print(f"Aviso en ChromaDB: {e}")
        return []


def fusionar_rrf(*rankings, k: int = 60, top: int = 3) -> List[Dict[str, Any]]:
    """
    Calcula el puntaje RRF sumando 1 / (k + posicion) para cada hash,
    y extrae los fragmentos finales directamente de SQLite.
    """
    puntajes: Dict[str, float] = {}

    for ranking in rankings:
        for posicion, resultado in enumerate(ranking, start=1):
            id_fragmento = resultado["id"]
            puntajes[id_fragmento] = puntajes.get(id_fragmento, 0.0) + (1.0 / (k + posicion))

    # Obtenemos los mejores IDs (hashes) según el puntaje acumulado
    orden_hashes = sorted(puntajes, key=puntajes.get, reverse=True)[:top]

    if not orden_hashes:
        return []

    # <-- ACÁ ESTÁ LA CONEXIÓN CON SQLITE -->
    # Traemos texto, página, documento y artículo desde corpus.db
    fragmentos_reales = leer_por_hashes(orden_hashes)

    # Le agregamos el score RRF a cada fragmento devuelto
    for frag in fragmentos_reales:
        frag["score_rrf"] = puntajes.get(frag.get("hash"), 0.0)

    return fragmentos_reales


def busqueda_hibrida(consulta: str, k: int = 3, audiencia: str = "todos") -> List[Dict[str, Any]]:
    """Función unificada lista para ser llamada desde FastAPI."""
    # Pedimos algunos candidatos de más (ej: 10) para que RRF tenga de dónde comparar y cruzar
    lexico = buscar_bm25(consulta, k=10)
    semantico = buscar_chromadb(consulta, k=10, audiencia=audiencia)

    return fusionar_rrf(lexico, semantico, k=60, top=k)


def mostrar(titulo: str, resultados: List[Dict[str, Any]], campo: str):
    print(titulo)
    for puesto, r in enumerate(resultados, start=1):
        identificador = r.get("id") or r.get("hash", "desconocido")
        valor = r.get(campo, 0.0)
        print(f"  {puesto}. {identificador}  ({campo}: {valor:.4f})")
    print()


if __name__ == "__main__":
    consulta = input("Pregunta: ")
    print("=" * 60)

    # 1. Búsquedas individuales
    lexico = buscar_bm25(consulta, k=3)
    semantico = buscar_chromadb(consulta, k=3)

    mostrar("Ranking BM25 (real):", lexico, "score")
    mostrar("Ranking ChromaDB (real):", semantico, "score")

    # 2. Fusión híbrida alimentada por SQLite
    fusionados = busqueda_hibrida(consulta, k=3)
    mostrar("Resultado fusionado (RRF + SQLite):", fusionados, "score_rrf")

    print("Contenido recuperado de SQLite:")
    for f in fusionados:
        print(f"- Doc: {f.get('documento')} (Pág {f.get('pagina')}): {f.get('texto')[:100]}...\n")