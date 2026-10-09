from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi

CARPETA = Path(__file__).parent / "documentos"

splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=50)

fragmentos = []
for archivo in sorted(CARPETA.glob("*.txt")):
    texto = archivo.read_text(encoding="utf-8")
    for numero, trozo in enumerate(splitter.split_text(texto)):
        fragmentos.append({
            "id": f"{archivo.stem}_{numero:03d}",
            "documento": archivo.name,
            "texto": trozo,
        })

if not fragmentos:
    raise SystemExit("No hay archivos .txt en la carpeta 'documentos'.")


def tokenizar(texto):
    return texto.lower().split()


bm25 = BM25Okapi([tokenizar(f["texto"]) for f in fragmentos])


def buscar_bm25(consulta, k=3):
    scores = bm25.get_scores(tokenizar(consulta))
    posiciones = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return [{**fragmentos[i], "score": float(scores[i])} for i in posiciones]


if __name__ == "__main__":
    print(f"Se cargaron {len(fragmentos)} fragmentos de {CARPETA.name}/")
    consulta = input("Pregunta: ")
    print("=" * 60)
    for puesto, r in enumerate(buscar_bm25(consulta, k=3), start=1):
        print(f"Puesto {puesto} | {r['id']} | {r['documento']} | puntaje {r['score']:.2f}")
        print(r["texto"])
        print()