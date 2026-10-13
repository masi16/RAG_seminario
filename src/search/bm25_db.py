import re
import sqlite3
import unicodedata
from pathlib import Path

from rank_bm25 import BM25Okapi

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_SQLITE = BASE_DIR / "data" / "sqlite" / "corpus.db"

PALABRAS_VACIAS = {
    "a", "al", "algo", "ante", "como", "con", "cual", "cuales", "cuando", "cuanto",
    "cuantos", "cuantas", "de", "del", "donde", "e", "el", "ella", "ellos", "en",
    "entre", "es", "esa", "ese", "eso", "esta", "este", "esto", "hay", "la", "las",
    "le", "les", "lo", "los", "me", "mi", "muy", "ni", "no", "nos", "o", "para",
    "pero", "por", "porque", "que", "quien", "se", "sea", "ser", "si", "sin", "sobre",
    "su", "sus", "te", "tiene", "tengo", "tu", "un", "una", "uno", "unos", "unas",
    "y", "ya", "hacer", "puedo", "puede", "debo", "deben", "debe",
}

_fragmentos = []
_indice = None


def cargar_fragmentos():
    if not DB_SQLITE.exists():
        return []
    conexion = sqlite3.connect(DB_SQLITE)
    conexion.row_factory = sqlite3.Row
    try:
        filas = conexion.execute(
            "SELECT hash, texto, documento, pagina, articulo, audiencia FROM fragmentos"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conexion.close()
    return [
        {
            "id": fila["hash"],
            "documento": fila["documento"],
            "pagina": fila["pagina"],
            "articulo": fila["articulo"],
            "audiencia": fila["audiencia"],
            "texto": fila["texto"],
        }
        for fila in filas
    ]


def tokenizar(texto):
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return [p for p in re.findall(r"\w+", texto) if p not in PALABRAS_VACIAS]


def reconstruir_indice():
    global _fragmentos, _indice
    _fragmentos = cargar_fragmentos()
    if _fragmentos:
        _indice = BM25Okapi([tokenizar(f["texto"]) for f in _fragmentos])
    else:
        _indice = None
    return len(_fragmentos)


def buscar_bm25(consulta, k=3, audiencia="todos", minimo=0.0):
    if _indice is None:
        reconstruir_indice()
    if _indice is None:
        return []
    scores = _indice.get_scores(tokenizar(consulta))
    posiciones = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    resultados = []
    for i in posiciones:
        if scores[i] <= minimo:
            break
        if audiencia != "todos" and _fragmentos[i]["audiencia"] not in (audiencia, "general"):
            continue
        resultados.append({**_fragmentos[i], "score": float(scores[i])})
        if len(resultados) == k:
            break
    return resultados


if __name__ == "__main__":
    cantidad = reconstruir_indice()
    print(f"Se cargaron {cantidad} fragmentos desde {DB_SQLITE.name}")
    consulta = input("Pregunta: ")
    print("=" * 60)
    resultados = buscar_bm25(consulta, k=3)
    if not resultados:
        print("Ningún fragmento comparte palabras con la pregunta.")
    for puesto, r in enumerate(resultados, start=1):
        print(f"Puesto {puesto} | {r['documento']} | pág. {r['pagina']} | {r['audiencia']} | puntaje {r['score']:.2f}")
        print(f"id: {r['id']}")
        print(r["texto"])
        print()