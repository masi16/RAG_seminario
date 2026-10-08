from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi

textos_prueba = [
    """El Reglamento de Alumnos establece que para mantener la condicion de alumno
    regular se debe aprobar al menos dos materias por año academico. La regularidad
    se pierde si el estudiante no cumple con este requisito durante dos años
    consecutivos.""",

    """Las licencias del personal administrativo se rigen por la Ordenanza 45/2018.
    El personal tiene derecho a licencia anual ordinaria de veinte dias habiles,
    que se otorgan segun antiguedad en el cargo.""",

    """El calendario academico 2026 establece el inicio del primer cuatrimestre
    el 9 de marzo y su finalizacion el 3 de julio. Las mesas de examen de julio
    se desarrollan entre el 6 y el 24 de julio.""",

    """Las becas estudiantiles se otorgan segun el promedio academico
    y la situacion socioeconomica del solicitante. El monto mensual
    de la beca completa equivale a dos canastas basicas.""",
]

splitter = RecursiveCharacterTextSplitter(chunk_size=150, chunk_overlap=20)

fragmentos = []
for texto in textos_prueba:
    fragmentos.extend(splitter.split_text(texto))


def tokenizar(texto):
    return texto.lower().split()


bm25 = BM25Okapi([tokenizar(f) for f in fragmentos])


def buscar_bm25(consulta, k=3):
    scores = bm25.get_scores(tokenizar(consulta))
    posiciones = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return [
        {"id": i, "texto": fragmentos[i], "score": float(scores[i])}
        for i in posiciones
    ]


if __name__ == "__main__":
    consulta = "receta de empanadas"
    print("Consulta:", consulta)
    print("=" * 60)
    for puesto, r in enumerate(buscar_bm25(consulta, k=3), start=1):
        print(f"Puesto {puesto} | fragmento {r['id']} | puntaje {r['score']:.2f}")
        print(r["texto"])
        print()