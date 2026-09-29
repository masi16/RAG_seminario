from bm25_docs import buscar_bm25, fragmentos


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


def ranking_simulado(ids):
    por_id = {f["id"]: f for f in fragmentos}
    return [{**por_id[i], "score": 0.0} for i in ids]


def mostrar(titulo, resultados, campo):
    print(titulo)
    for puesto, r in enumerate(resultados, start=1):
        print(f"  {puesto}. {r['id']}  ({campo} {r[campo]:.4f})")
    print()


if __name__ == "__main__":
    consulta = input("Pregunta: ")
    print("=" * 60)
    lexico = buscar_bm25(consulta, k=3)
    semantico = ranking_simulado([
        "reglamento_prueba_001",
        "reglamento_prueba_000",
        "becas_prueba_000",
    ])
    mostrar("Ranking BM25 (real):", lexico, "score")
    mostrar("Ranking semantico (SIMULADO):", semantico, "score")
    mostrar("Resultado fusionado (RRF):", fusionar_rrf(lexico, semantico), "score_rrf")