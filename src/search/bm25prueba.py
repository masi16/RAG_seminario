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
]

splitter = RecursiveCharacterTextSplitter(
    chunk_size=150,
    chunk_overlap=20,
)

fragmentos = []
for texto in textos_prueba:
    fragmentos.extend(splitter.split_text(texto))

print(f"Se generaron {len(fragmentos)} fragmentos:\n")
for i, frag in enumerate(fragmentos):
    print(f"[{i}] {frag}\n")

fragmentos_tokenizados = [frag.lower().split() for frag in fragmentos]

bm25 = BM25Okapi(fragmentos_tokenizados)

consulta = "cuantas materias hay que aprobar para ser alumno regular"
consulta_tokenizada = consulta.lower().split()

scores = bm25.get_scores(consulta_tokenizada)

mejor_indice = scores.argmax()
print("=" * 60)
print("Consulta:", consulta)
print("\nFragmento mas relevante encontrado:\n")
print(fragmentos[mejor_indice])