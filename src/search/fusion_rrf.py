from pathlib import Path

try:
    from src.search.bm25_db import buscar_bm25
    from src.database.crud import leer_por_hashes
except ImportError:
    from bm25_db import buscar_bm25
    from crud import leer_por_hashes

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CARPETA_CHROMA = BASE_DIR / "data" / "chroma_db"
COLECCION = "normativas_unlar"
MODELO_EMBEDDINGS = "paraphrase-multilingual-MiniLM-L12-v2"

_coleccion = None


def fusionar_rrf(*rankings, k=60, top=3):
    puntajes = {}
    datos = {}
    for ranking in rankings:
        for posicion, resultado in enumerate(ranking, start=1):
            id_fragmento = resultado["id"]
            puntajes[id_fragmento] = puntajes.get(id_fragmento, 0) + 1 / (k + posicion)
            if id_fragmento not in datos:
                datos[id_fragmento] = {
                    clave: valor for clave, valor in resultado.items() if clave != "score"
                }
    orden = sorted(puntajes, key=puntajes.get, reverse=True)[:top]
    return [{**datos[i], "score_rrf": puntajes[i]} for i in orden]


def _obtener_coleccion():
    global _coleccion
    if _coleccion is None:
        import chromadb
        from chromadb.utils import embedding_functions

        cliente = chromadb.PersistentClient(path=str(CARPETA_CHROMA))
        emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=MODELO_EMBEDDINGS
        )
        _coleccion = cliente.get_collection(name=COLECCION, embedding_function=emb_fn)
    return _coleccion


def buscar_semantico(consulta, k=10, audiencia="todos"):
    filtros = (
        {"audiencia": {"$in": [audiencia, "general"]}} if audiencia != "todos" else None
    )
    resultado = _obtener_coleccion().query(
        query_texts=[consulta], n_results=k, where=filtros
    )
    return [{"id": id_fragmento} for id_fragmento in resultado["ids"][0]]


def busqueda_hibrida(consulta, k=4, audiencia="todos", candidatos=20):
    lexico = buscar_bm25(consulta, k=candidatos, audiencia=audiencia)

    try:
        semantico = buscar_semantico(consulta, k=candidatos, audiencia=audiencia)
    except Exception as error:
        print(f"AVISO: la búsqueda semántica falló ({error}). Se usa solo BM25.")
        semantico = []

    ids_lexico = {r["id"] for r in lexico}
    ids_semantico = {r["id"] for r in semantico}

    fusionados = fusionar_rrf(lexico, semantico, top=k)
    ids_ordenados = [f["id"] for f in fusionados]
    puntajes = {f["id"]: f["score_rrf"] for f in fusionados}

    resultados = []
    for fila in leer_por_hashes(ids_ordenados):
        id_fragmento = fila["hash"]
        encontrado_por = []
        if id_fragmento in ids_lexico:
            encontrado_por.append("bm25")
        if id_fragmento in ids_semantico:
            encontrado_por.append("semantico")
        resultados.append({
            "id": id_fragmento,
            "texto": fila["texto"],
            "documento": fila["documento"],
            "pagina": fila["pagina"],
            "articulo": fila["articulo"],
            "audiencia": fila["audiencia"],
            "score_rrf": puntajes[id_fragmento],
            "encontrado_por": encontrado_por,
        })
    return resultados


if __name__ == "__main__":
    consulta = input("Pregunta: ")
    print("=" * 60)
    for puesto, r in enumerate(busqueda_hibrida(consulta, k=4), start=1):
        print(f"Puesto {puesto} | {r['documento']} | pág. {r['pagina']} | rrf {r['score_rrf']:.4f} | {', '.join(r['encontrado_por'])}")
        print(r["texto"])
        print()