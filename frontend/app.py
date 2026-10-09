import os
import time
from pathlib import Path

import requests
import streamlit as st

WEBHOOK = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/consulta")
API_URL = os.getenv("API_URL")
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
            "pagina": 4,
            "texto": "Para mantener la condición de alumno regular se debe aprobar al menos dos materias por año académico.",
        },
        {
            "documento": "Reglamento de exámenes finales",
            "articulo": "Art. 8",
            "pagina": 2,
            "texto": "La regularidad se pierde si no se cumple este requisito durante dos años consecutivos.",
        },
    ],
)


def llamar(url, pregunta, audiencia, **extra):
    r = requests.post(
        url, json={"consulta": pregunta, "audiencia": audiencia, **extra}, timeout=120
    )
    r.raise_for_status()
    return r.json()


def consultar(pregunta, audiencia):
    if os.getenv("DEMO"):
        time.sleep(1)
        return DEMO
    if API_URL:
        datos = llamar(f"{API_URL}/buscar_hibrido", pregunta, audiencia, top_k=3)
        return (
            "**Modo prueba (sin LLM):** fragmentos más relevantes.",
            datos["resultados"],
        )
    datos = llamar(WEBHOOK, pregunta, audiencia)
    return datos.get("respuesta", ""), datos.get("fuentes") or datos.get(
        "resultados", []
    )


def mostrar_fuentes(fuentes):
    if fuentes:
        st.markdown(f"**Fuentes consultadas ({len(fuentes)})**")
    for f in fuentes:
        nombre = f.get("documento") or f.get("documento_origen", "Documento")
        if f.get("articulo"):
            nombre += f" — {f['articulo']}"
        with st.expander(nombre):
            detalle = [
                f"Página {f['pagina']}" if f.get("pagina") else "",
                ORIGEN.get(f.get("encontrado_por"), ""),
            ]
            st.caption(" · ".join(d for d in detalle if d))
            st.markdown("> " + f.get("texto", "").replace("\n", " "))


def barra_lateral(historial):
    with st.sidebar:
        st.markdown(
            "<div class='marca'><b>U</b><div><strong>UNLaR</strong><br><small>Asistente virtual</small></div></div>",
            unsafe_allow_html=True,
        )
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
        if st.button(
            "＋  Nueva consulta", key="nueva", type="primary", width="stretch"
        ):
            historial.clear()
            st.rerun()
    return audiencia


def pantalla_inicio():
    with st.chat_message("assistant", avatar=AVATAR["assistant"]):
        st.markdown(
            "**¡Hola! Soy el asistente virtual de la UNLaR.**  \n"
            "Consultame sobre reglamentos, ordenanzas y normativas: siempre indico el documento y artículo de origen."
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

izquierda, derecha = st.columns([4, 1.6])
izquierda.caption(
    "Universidad Nacional de La Rioja · Ingeniería en Sistemas de Información"
)
derecha.download_button(
    "Exportar conversación",
    data="\n".join(
        f"{'Consulta' if m['rol'] == 'user' else 'Respuesta'}: {m['texto']}"
        for m in historial
    ),
    file_name="consulta_unlar.txt",
    disabled=not historial,
    width="stretch",
)

consulta = st.chat_input(
    "Escribí tu consulta sobre reglamentos y ordenanzas"
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
            except requests.RequestException as error:
                texto, fuentes = (
                    f"No pude obtener respuesta del servicio. ¿Están activos n8n o la API?\n\n`{type(error).__name__}`",
                    [],
                )
        st.markdown(texto)
        mostrar_fuentes(fuentes)
    historial.append({"rol": "assistant", "texto": texto, "fuentes": fuentes})

st.markdown(
    "<p class='pie'>Respuestas basadas en documentos públicos de unlar.edu.ar y del Digesto Digital. "
    "Verificá siempre el texto del documento citado.</p>",
    unsafe_allow_html=True,
)
