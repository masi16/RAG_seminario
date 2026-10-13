# RAG Seminario

Sistema de recuperación de información basado en RAG para documentos normativos de la Universidad Nacional de La Rioja (UNLaR). El proyecto ingesta PDFs y textos, fragmenta los contenidos, indexa el corpus en SQLite y ChromaDB, y ofrece búsqueda híbrida combinando BM25 + embeddings semánticos para responder consultas sobre normativa académica y administrativa.

## Objetivo

Permitir consultar documentos institucionales mediante preguntas naturales y devolver fragmentos relevantes junto con su fuente documental. El flujo está pensado para integrarse con workflows de n8n y una interfaz web simple con Streamlit.

## Arquitectura general

- Ingesta documentos desde `data/raw`
- Fragmenta cada archivo con `RecursiveCharacterTextSplitter`
- Guarda una copia canónica de fragmentos en SQLite (`data/sqlite/corpus.db`)
- Genera embeddings con `SentenceTransformer` y almacena resultados en ChromaDB (`data/chroma_db`)
- Realiza búsquedas híbridas con:
  - BM25 sobre texto léxico
  - embeddings semánticos sobre ChromaDB
  - fusión RRF para combinar ambos rankings
- Expone una API REST con FastAPI
- Incluye una UI de consulta con Streamlit
- Permite integración con n8n para automatizar flujos o webhook de consultas

## Estructura del proyecto

```text
RAG_seminario/
├── data/
│   ├── raw/                 # PDFs y .txt a procesar
│   ├── sqlite/             # base SQLite generada por el proyecto
│   └── chroma_db/          # índice persistente de ChromaDB
├── frontend/
│   ├── app.py              # interfaz Streamlit
│   └── estilos.css
├── n8n/
│   └── workflows/          # workflows exportados/importables
├── src/
│   ├── api/
│   │   └── api.py          # API REST con FastAPI
│   ├── database/
│   │   └── crud.py         # operaciones CRUD sobre SQLite
│   ├── ingestion/
│   │   └── pipeline.py     # pipeline de ingestión y reindexado
│   └── search/
│       ├── bm25_db.py      # índice BM25
│       └── fusion_rrf.py   # fusión de rankings
├── docker-compose.yml      # servicio n8n
├── README.md
└── .gitignore
```

## Requisitos

- Python 3.10+
- pip
- Docker y Docker Compose (opcional para n8n)
- Dependencias principales:
  - `fastapi`
  - `uvicorn`
  - `chromadb`
  - `langchain`
  - `langchain-community`
  - `sentence-transformers`
  - `pypdf`
  - `rank-bm25`
  - `streamlit`
  - `requests`

## Instalación

Desde la raíz del proyecto:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install --upgrade pip
pip install fastapi uvicorn chromadb langchain langchain-community sentence-transformers pypdf rank-bm25 streamlit requests
```

También puede usarse el entorno de Docker para n8n:

```bash
docker compose up -d
```

## Preparación de datos

Colocar los documentos fuente en `data/raw/`.

Formatos soportados:

- `.pdf`
- `.txt`

El pipeline detecta automáticamente los archivos, los fragmenta y crea el índice de búsqueda. Si el archivo ya fue procesado, evita reindexar si no hubo cambios.

## Ingesta de documentos

Ejecutar la ingesta completa:

```bash
python -m src.ingestion.pipeline
```

Esto realiza lo siguiente:

1. Lista archivos en `data/raw/`
2. Fragmenta cada documento
3. Guarda fragmentos en SQLite
4. Genera embeddings para cada fragmento
5. Carga los embeddings en ChromaDB
6. Almacena metadatos: documento, página, artículo, audiencia y hash del archivo

También se expone la función `procesar_un_documento(nombre_archivo, forzar=True)` para reindexar un documento específico.

## API REST

La API se levanta desde la raíz con:

```bash
uvicorn src.api.api:app --reload --host 0.0.0.0 --port 8000
```

Endpoints principales:

### `GET /`
Devuelve el estado del servicio.

### `POST /buscar`
Busca documentos con una consulta de texto.

Ejemplo:

```json
{
  "consulta": "¿Qué condiciones tienen los estudiantes para mantener la regularidad?",
  "top_k": 4,
  "audiencia": "academico"
}
```

### `POST /reindexar`
Reindexa un documento concreto.

Ejemplo:

```json
{
  "documento": "Reglamento de Alumnos.pdf"
}
```

La app FastAPI queda disponible en Swagger/OpenAPI en:

```text
http://localhost:8000/docs
```

## Frontend

Iniciar la interfaz de consulta:

```bash
streamlit run frontend/app.py
```

La app permite:

- ingresar consultas en lenguaje natural
- filtrar por audiencia (`todos`, `academico`, `administrativo`)
- mostrar fragmentos relevantes
- indicar la fuente documental y la página
- mostrar si la coincidencia provino de BM25, embeddings o ambos

## Búsqueda híbrida

El proyecto combina dos estrategias:

- BM25: recuperación por coincidencia léxica
- embeddings: recuperación semántica por similitud
- RRF: combinación de rankings para priorizar los resultados más relevantes

El módulo `src/search/fusion_rrf.py` implementa la fusión y devuelve un ranking final con los fragmentos más relevantes.

## Integración con n8n

El archivo `docker-compose.yml` levanta un servicio `n8n` para automatizar workflows y consumir la API o webhooks del proyecto. La carpeta `n8n/workflows` está preparada para incorporar flujos de automatización que consulten la base documental o disparen reindexación.

## Datos generados por la aplicación

Al ejecutar la ingesta, se crean y actualizan automáticamente las siguientes rutas:

- `data/raw/` → documentos fuente
- `data/sqlite/corpus.db` → base de fragmentos para BM25
- `data/chroma_db/` → vectores semánticos persistidos

## Troubleshooting

### El servicio no encuentra documentos
Verificar que los archivos estén dentro de `data/raw/` y que tengan extensión `.pdf` o `.txt`.

### La búsqueda semántica falla
Revisar si `chromadb` y `sentence-transformers` están correctamente instalados. También puede depender del modelo `paraphrase-multilingual-MiniLM-L12-v2`, que se descarga automáticamente al iniciar la primera conexión.

### El índice queda desactualizado
Ejecutar reindexado de documentos con:

```bash
python -m src.ingestion.pipeline
```

o invocar el endpoint:

```http
POST /reindexar
```

## Contribución

El proyecto está orientado a extensiones futuras, como:

- mejorado del reranking
- extracción automática de metadatos
- soporte de más tipos de documentos
- almacenamiento de historial de consultas
- integración con modelos LLM externos o locales

## Licencia

Este proyecto es de uso académico y de prueba en el marco del seminario de RAG. Ajustar la licencia según el contexto institucional si se va a desplegar en producción.
