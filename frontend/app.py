import html
import os
import time
from pathlib import Path

import requests
import streamlit as st

WEBHOOK = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/consulta")
API_URL = os.getenv("API_URL")
TIMEOUT = int(os.getenv("TIMEOUT", "180"))  # segundos; el modelo local puede tardar
AVATAR = {"user": ":material/person:", "assistant": ":material/school:"}
AUDIENCIAS = {
    "todos": "Toda la normativa",
    "academico": "Académica (estudiantes y docentes)",
    "administrativo": "Administrativa (personal)",
}
ORIGEN = {
    "ambos": "Coincidencia semántica y de palabras",
    "semantico": "Coincidencia semántica",
    "lexico": "Coincidencia de palabras",
}
FRECUENTES = [
    (
        "school",
        "Regularidad de materias",
        "¿Qué condiciones tengo que cumplir para regularizar una materia?",
    ),
    (
        "edit_note",
        "Exámenes finales",
        "¿Cuántas veces puedo rendir un examen final y cuándo vence la regularidad?",
    ),
    (
        "savings",
        "Becas estudiantiles",
        "¿Qué becas y beneficios estudiantiles existen y cómo se solicitan?",
    ),
    (
        "event",
        "Calendario académico",
        "¿Cuándo empieza y termina el primer cuatrimestre?",
    ),
    (
        "badge",
        "Licencias del personal",
        "¿Cuántos días de licencia anual ordinaria corresponden al personal?",
    ),
    (
        "receipt_long",
        "Compras y contrataciones",
        "¿Qué dice el régimen de compras sobre contrataciones directas?",
    ),
]
DEMO = (
    "**Modo demo:** para mantener la regularidad hay que aprobar al menos dos materias por año académico.",
    [
        {
            "documento": "Reglamento de Alumnos",
            "articulo": "Art. 12",
            "pagina": 3,
            "puntaje_embedding": 0.82,
            "puntaje_rerank": 0.94,
            "texto": "Para mantener la condición de alumno regular se debe aprobar al menos dos materias por año académico.",
        },
        {
            "documento": "Reglamento de exámenes finales",
            "articulo": "Art. 8",
            "pagina": 1,
            "puntaje_embedding": 0.74,
            "puntaje_rerank": 0.61,
            "texto": "La regularidad se pierde si no se cumple este requisito durante dos años consecutivos.",
        },
    ],
)


def llamar(url, pregunta, audiencia, **extra):
    r = requests.post(
        url,
        json={
            "consulta": pregunta,
            "pregunta": pregunta,  # compatibilidad con el workflow original
            "audiencia": audiencia,
            **extra,
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def normalizar_fuente(f):
    if isinstance(f.get("metadata"), dict):
        f = {**f["metadata"], **f}
    else:
        f = dict(f)
    origen = f.get("encontrado_por")
    if isinstance(origen, list):
        if "bm25" in origen and "semantico" in origen:
            f["encontrado_por"] = "ambos"
        elif "bm25" in origen:
            f["encontrado_por"] = "lexico"
        elif "semantico" in origen:
            f["encontrado_por"] = "semantico"
        else:
            f["encontrado_por"] = ""
    if "puntaje_rrf" not in f and es_numero(f.get("score_rrf")):
        f["puntaje_rrf"] = f["score_rrf"]
    return f


def consultar(pregunta, audiencia):
    if os.getenv("DEMO"):
        time.sleep(1)
        return DEMO
    if API_URL:
        datos = llamar(f"{API_URL}/buscar", pregunta, audiencia, k=3)
        return (
            "**Modo prueba (sin LLM):** fragmentos más relevantes.",
            datos.get("resultados", []),
        )
    datos = llamar(WEBHOOK, pregunta, audiencia)
    if isinstance(datos, list):  # n8n a veces devuelve una lista con un elemento
        datos = datos[0] if datos else {}
    if not isinstance(datos, dict):
        raise ValueError("formato inesperado")
    respuesta = next(
        (
            datos[k]
            for k in ("respuesta", "output", "text", "answer")
            if isinstance(datos.get(k), str)
        ),
        "",
    )
    if not respuesta and isinstance(datos.get("choices"), list) and datos["choices"]:
        respuesta = datos["choices"][0].get("message", {}).get("content", "")
    fuentes = next(
        (
            datos[k]
            for k in ("fuentes", "resultados", "sources")
            if isinstance(datos.get(k), list)
        ),
        [],
    )
    return respuesta, [normalizar_fuente(f) for f in fuentes if isinstance(f, dict)]


def formatear_pagina(valor):
    # PyPDFLoader numera las páginas desde 0
    try:
        return f"Página {int(valor) + 1}"
    except (TypeError, ValueError):
        return ""


def explicar_error(error):
    if isinstance(error, requests.exceptions.ConnectionError):
        return (
            "No pude conectar con el servicio. Verificá que n8n (o la API) esté "
            "en ejecución y que el workflow esté publicado."
        )
    if isinstance(error, requests.exceptions.Timeout):
        return (
            "El servicio tardó demasiado en responder. Puede ser que el modelo "
            "de LM Studio no esté cargado o sea muy lento."
        )
    if isinstance(error, requests.exceptions.HTTPError):
        codigo = error.response.status_code if error.response is not None else "?"
        if codigo == 404:
            return (
                "n8n no encontró el webhook (404). Verificá que el workflow esté "
                "publicado y que la URL sea correcta."
            )
        return f"El servicio devolvió un error (HTTP {codigo}). Revisá las ejecuciones en n8n."
    return (
        "La respuesta del servicio no tiene el formato esperado "
        "(se esperaba un JSON con 'respuesta' y 'fuentes')."
    )


def exportar(historial):
    lineas = []
    for m in historial:
        if m["rol"] == "user":
            lineas.append(f"Consulta: {m['texto']}")
        else:
            lineas.append(f"Respuesta: {m['texto']}")
            for f in m.get("fuentes", []):
                nombre = f.get("documento") or f.get("documento_origen", "Documento")
                if f.get("articulo"):
                    nombre += f" - {f['articulo']}"
                lineas.append(f"  Fuente: {nombre}")
        lineas.append("")
    return "\n".join(lineas)


PUNTAJES = [
    ("puntaje_embedding", "Embedding", "emb"),
    ("puntaje_bm25", "BM25", "bm25"),
    ("puntaje_rrf", "RRF", "rrf"),
    ("puntaje_rerank", "Re-ranking", "rerank"),
]


def es_numero(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def mostrar_fuentes(fuentes):
    if fuentes:
        st.markdown(f"**Fuentes consultadas ({len(fuentes)})**")
    for n, f in enumerate(fuentes, 1):
        nombre = f.get("documento") or f.get("documento_origen", "Documento")
        if f.get("articulo"):
            nombre += f" — {f['articulo']}"
        with st.container(border=True):
            st.markdown(
                f"<div class='frag'><span class='rango'>#{n}</span> <b>{html.escape(nombre)}</b></div>",
                unsafe_allow_html=True,
            )
            detalle = [
                formatear_pagina(f.get("pagina")),
                ORIGEN.get(f.get("encontrado_por"), ""),
            ]
            st.caption(" · ".join(d for d in detalle if d))
            chips = "".join(
                f"<span class='chip {clase}'>{etiqueta} {f[clave]:.3f}</span>"
                for clave, etiqueta, clase in PUNTAJES
                if es_numero(f.get(clave))
            )
            if chips:
                st.markdown(chips, unsafe_allow_html=True)
            # barra del puntaje principal: re-ranking si existe, si no embedding
            clave = (
                "puntaje_rerank"
                if es_numero(f.get("puntaje_rerank"))
                else "puntaje_embedding"
            )
            if es_numero(f.get(clave)):
                st.progress(max(0.0, min(1.0, f[clave])))
            with st.expander("Ver texto del fragmento"):
                st.markdown("> " + f.get("texto", "").replace("\n", " "))


def barra_lateral(historial):
    with st.sidebar:
        st.markdown(
            "<div class='marca'><strong>UNLaR</strong><span>Asistente virtual</span></div>",
            unsafe_allow_html=True,
        )
        if st.button(
            "Nueva consulta",
            key="nueva",
            type="tertiary",
            icon=":material/edit_square:",
            width="stretch",
        ):
            historial.clear()
            st.rerun()
        audiencia = st.radio(
            "Consultar normativa", list(AUDIENCIAS), format_func=AUDIENCIAS.get
        )
        preguntas = list(
            dict.fromkeys(m["texto"] for m in reversed(historial) if m["rol"] == "user")
        )
        if preguntas:
            st.markdown(
                "<div class='rotulo'>Mis consultas</div>", unsafe_allow_html=True
            )
        for i, pregunta in enumerate(preguntas[:8]):
            if st.button(
                pregunta,
                key=f"hist_{i}",
                type="tertiary",
                icon=":material/chat_bubble_outline:",
                width="stretch",
            ):
                st.session_state.pendiente = pregunta
                st.rerun()
        with st.container(key="pie_lateral"):
            st.markdown(
                "<div class='promo'><b>Respuestas con fuente</b>"
                "<span>Cada respuesta indica el documento y la página de origen.</span></div>",
                unsafe_allow_html=True,
            )
            st.download_button(
                "Exportar conversación",
                data=exportar(historial),
                file_name="consulta_unlar.txt",
                disabled=not historial,
                width="stretch",
            )
    return audiencia


def pantalla_inicio():
    st.markdown(
        "<div class='saludo'><span class='grad'>¡Hola, estudiante!</span>"
        "<span class='sub'>¿Qué querés consultar hoy? Te respondo con el documento y el artículo de origen.</span></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='rotulo'>Consultas frecuentes</div>", unsafe_allow_html=True
    )
    for fila in (FRECUENTES[:3], FRECUENTES[3:]):
        for columna, (icono, titulo, pregunta) in zip(st.columns(3), fila):
            if columna.button(
                titulo,
                key=f"sug_{icono}",
                icon=f":material/{icono}:",
                help=pregunta,
                width="stretch",
            ):
                st.session_state.pendiente = pregunta
                st.rerun()


st.set_page_config(page_title="Asistente UNLaR", layout="wide")
estilos = Path(__file__).with_name("estilos.css").read_text(encoding="utf-8")
st.markdown(f"<style>{estilos}</style>", unsafe_allow_html=True)

historial = st.session_state.setdefault("historial", [])
audiencia = barra_lateral(historial)

st.caption("Universidad Nacional de La Rioja · Ingeniería en Sistemas de Información")

consulta = st.chat_input(
    "Preguntale al asistente sobre reglamentos y ordenanzas"
) or st.session_state.pop("pendiente", None)
if consulta:
    historial.append({"rol": "user", "texto": consulta})

if not historial:
    pantalla_inicio()

for mensaje in historial:
    with st.chat_message(mensaje["rol"], avatar=AVATAR[mensaje["rol"]]):
        st.markdown(mensaje["texto"])
        mostrar_fuentes(mensaje.get("fuentes", []))

if consulta:
    with st.chat_message("assistant", avatar=AVATAR["assistant"]):
        with st.spinner("Buscando en los documentos…"):
            try:
                texto, fuentes = consultar(consulta, audiencia)
                texto = (
                    texto
                    or "No encontré información sobre eso en los documentos cargados."
                )
            except (requests.RequestException, ValueError) as error:
                texto, fuentes = explicar_error(error), []
        st.markdown(texto)
        mostrar_fuentes(fuentes)
    historial.append({"rol": "assistant", "texto": texto, "fuentes": fuentes})

st.markdown(
    "<p class='pie'>Respuestas basadas en documentos públicos de unlar.edu.ar y del Digesto Digital. "
    "Verificá siempre el texto del documento citado.</p>",
    unsafe_allow_html=True,
)
