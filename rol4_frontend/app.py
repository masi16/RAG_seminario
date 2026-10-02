"""Front Streamlit - Asistente normativo UNLaR.
Modos: DEMO=1 (datos de ejemplo) | API_URL=http://localhost:8000 (api.py) | N8N_WEBHOOK_URL (flujo completo).
"""

import os, time
import requests
import streamlit as st

WEBHOOK = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/consulta")
API_URL = os.getenv("API_URL")
AVATAR = {"user": ":material/person:", "assistant": ":material/school:"}
SUGERENCIAS = [
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
ORIGEN = {
    "ambos": "Coincidencia semántica y de palabras",
    "semantico": "Coincidencia semántica",
    "lexico": "Coincidencia de palabras",
}

st.set_page_config(page_title="Asistente UNLaR", layout="wide")
st.markdown(
    """<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap');
:root{--acento:#3B9AE1;--tinta:#14171A;--borde:#E7E8EB}
.stApp{background:#F3F4F6}
.stApp,.stApp p,.stApp label,.stApp h1,.stApp h2,.stApp li,.stApp input,.stApp textarea,.stApp button{font-family:'DM Sans',system-ui,sans-serif}
header[data-testid="stHeader"]{background:transparent}
section[data-testid="stSidebar"]{background:#fff;border-right:1px solid var(--borde)}
[data-testid="stMainBlockContainer"]{background:#fff;border:1px solid var(--borde);border-radius:22px;max-width:980px;padding:1rem 2rem 4.5rem;margin-top:0}
.stApp [data-testid="stMarkdownContainer"] *,.stApp label *{color:var(--tinta)!important}
.stApp [data-testid="stCaptionContainer"] *{color:#6B7280!important}
.stApp [data-testid="stBaseButton-primary"] *{color:#fff!important}
[data-testid="stBaseButton-primary"]{background:var(--tinta);border-radius:11px}
[data-testid="stVerticalBlockBorderWrapper"],[data-testid="stExpander"]{border-radius:14px;border-color:var(--borde);background:#FCFCFD}
[data-testid="stChatInput"],[data-testid="stChatInput"] textarea{background:#fff!important;color:var(--tinta)!important}
[data-testid="stChatInput"]{border-radius:18px;box-shadow:0 6px 24px rgba(20,23,26,.08)}
[data-testid="stBottom"],[data-testid="stBottom"]>div{background:transparent!important}
[data-testid="stChatMessageAvatarAssistant"]{background:var(--acento)!important}
[data-testid="stChatMessageAvatarUser"]{background:var(--tinta)!important}
[data-testid="stChatMessage"]{background:transparent}
/* historial: alineado a la izquierda */
[data-testid="stSidebar"] [data-testid="stBaseButton-tertiary"]{display:flex!important;width:100%!important;justify-content:flex-start!important;border:0;border-radius:9px;min-height:0;padding:.4rem .6rem}
[data-testid="stSidebar"] [data-testid="stBaseButton-tertiary"] *{justify-content:flex-start!important;text-align:left!important}
[data-testid="stSidebar"] [data-testid="stBaseButton-tertiary"]:hover{background:#F1F2F4}
[data-testid="stSidebar"] [data-testid="stBaseButton-tertiary"] [data-testid="stMarkdownContainer"]{flex:1;min-width:0}
[data-testid="stSidebar"] [data-testid="stBaseButton-tertiary"] p{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:.9rem}
[data-testid="stSidebar"] [data-testid="stIconMaterial"]{color:var(--acento)!important}
[class*="st-key-s_"] button{min-height:3.2rem;border:1px solid var(--borde);border-radius:14px;background:#FCFCFD}
[class*="st-key-s_"] button:hover{border-color:var(--acento)}
[class*="st-key-s_"] button *{justify-content:flex-start!important;text-align:left!important}
/* "Nueva consulta" fija en la parte baja de la barra lateral */
[data-testid="stSidebarUserContent"]{padding-bottom:5rem}
.st-key-nueva{position:fixed;bottom:1rem;left:1rem;width:19rem;z-index:100}
.marca{display:flex;align-items:center;gap:.6rem;margin-bottom:1rem}
.marca b{display:flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:9px;background:var(--acento);color:#fff}
.rot{font-size:.75rem;letter-spacing:.04em;text-transform:uppercase;color:#9AA0A6;margin:1rem 0 .4rem}
</style>""",
    unsafe_allow_html=True,
)


def consultar(q, aud):
    """Devuelve (respuesta, fuentes) según el modo configurado."""
    if os.getenv("DEMO"):
        time.sleep(1)
        return (
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
    if API_URL:  # directo a api.py, sin LLM
        r = requests.post(
            f"{API_URL}/buscar_hibrido",
            json={"consulta": q, "audiencia": aud, "top_k": 3},
            timeout=120,
        )
        r.raise_for_status()
        return (
            "**Modo prueba (sin LLM):** fragmentos más relevantes (BM25 + semántica).",
            r.json()["resultados"],
        )
    r = requests.post(
        WEBHOOK, json={"consulta": q, "audiencia": aud}, timeout=120
    )  # LLM local: puede tardar
    r.raise_for_status()
    d = r.json()
    return d.get("respuesta", ""), d.get("fuentes") or d.get("resultados") or []


def fuentes_ui(fuentes):
    if fuentes:
        st.markdown(f"**Fuentes consultadas ({len(fuentes)})**")
    for f in fuentes:
        doc = f.get("documento") or f.get("documento_origen", "Documento")
        with st.expander(doc + (f" — {f['articulo']}" if f.get("articulo") else "")):
            meta = [
                f"Página {f['pagina']}" if f.get("pagina") else "",
                ORIGEN.get(f.get("encontrado_por"), ""),
            ]
            st.caption(" · ".join(m for m in meta if m))
            st.markdown("> " + f.get("texto", "").replace("\n", " "))


ss = st.session_state
ss.setdefault("h", [])  # historial: [{"rol", "texto", "fuentes"}]

with st.sidebar:
    st.markdown(
        "<div class='marca'><b>U</b><div><strong>UNLaR</strong><br><small>Asistente virtual</small></div></div>",
        unsafe_allow_html=True,
    )
    aud = st.radio(
        "Consultar normativa",
        ["todos", "academico", "administrativo"],
        format_func=lambda x: {
            "todos": "Toda la normativa",
            "academico": "Académica (estudiantes y docentes)",
            "administrativo": "Administrativa (personal)",
        }[x],
    )
    preguntas = list(
        dict.fromkeys(m["texto"] for m in reversed(ss.h) if m["rol"] == "user")
    )
    if preguntas:
        st.markdown("<div class='rot'>Mis consultas</div>", unsafe_allow_html=True)
        for i, p in enumerate(preguntas[:8]):
            if st.button(
                p,
                key=f"h{i}",
                type="tertiary",
                icon=":material/chat_bubble_outline:",
                use_container_width=True,
            ):
                ss.pendiente = p
                st.rerun()
    if st.button(
        "＋  Nueva consulta", key="nueva", type="primary", use_container_width=True
    ):
        ss.h = []
        st.rerun()

c1, c2 = st.columns([4, 1.6])
c1.caption("Universidad Nacional de La Rioja · Ingeniería en Sistemas de Información")
c2.download_button(
    "Exportar conversación",
    disabled=not ss.h,
    file_name="consulta_unlar.txt",
    use_container_width=True,
    data="\n".join(
        f"{'Consulta' if m['rol'] == 'user' else 'Respuesta'}: {m['texto']}"
        for m in ss.h
    ),
)

consulta = st.chat_input(
    "Escribí tu consulta sobre reglamentos y ordenanzas"
) or ss.pop("pendiente", None)
if consulta:
    ss.h.append({"rol": "user", "texto": consulta})

if not ss.h:  # pantalla de inicio
    with st.chat_message("assistant", avatar=AVATAR["assistant"]):
        st.markdown(
            "**¡Hola! Soy el asistente virtual de la UNLaR.**  \nConsultame sobre reglamentos, ordenanzas y normativas: "
            "siempre indico el documento y artículo de origen."
        )
    st.markdown("<div class='rot'>Consultas frecuentes</div>", unsafe_allow_html=True)
    for fila in (SUGERENCIAS[:3], SUGERENCIAS[3:]):
        for col, (icono, titulo, pregunta) in zip(st.columns(3), fila):
            if col.button(
                titulo,
                key=f"s_{icono}",
                icon=f":material/{icono}:",
                help=pregunta,
                use_container_width=True,
            ):
                ss.pendiente = pregunta
                st.rerun()

for m in ss.h:
    with st.chat_message(m["rol"], avatar=AVATAR[m["rol"]]):
        st.markdown(m["texto"])
        fuentes_ui(m.get("fuentes", []))

if consulta:
    with st.chat_message("assistant", avatar=AVATAR["assistant"]):
        with st.spinner("Buscando en los documentos…"):
            try:
                texto, fuentes = consultar(consulta, aud)
                texto = (
                    texto
                    or "No encontré información sobre eso en los documentos cargados."
                )
            except requests.RequestException as e:
                texto, fuentes = (
                    f"No pude obtener respuesta del servicio. ¿Están activos n8n o la API?\n\n`{type(e).__name__}`",
                    [],
                )
        st.markdown(texto)
        fuentes_ui(fuentes)
    ss.h.append({"rol": "assistant", "texto": texto, "fuentes": fuentes})

st.markdown(
    "<p style='text-align:center;color:#9AA0A6;font-size:.78rem;margin-top:1rem'>Respuestas basadas en documentos públicos "
    "de unlar.edu.ar y del Digesto Digital. Verificá siempre el texto del documento citado.</p>",
    unsafe_allow_html=True,
)
