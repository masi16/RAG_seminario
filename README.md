# Asistente Normativo UNLaR - RAG

Sistema de recuperación aumentada por generación (RAG) para consultar normativas y ordenanzas de la Universidad Nacional de La Rioja (UNLaR). El sistema ingesta documentos en formato PDF y TXT, fragmenta su contenido, persiste el corpus estructurado en SQLite y genera representaciones vectoriales en ChromaDB. 

A través de un motor de búsqueda híbrida que combina **BM25** (recuperación léxica) y **ChromaDB** (recuperación semántica) mediante **RRF (Reciprocal Rank Fusion)**, el sistema recupera los fragmentos más pertinentes y los envía a un modelo de lenguaje local (**Phi-3 Mini** ejecutado en Ollama) orquestado con flujos de **n8n** y consultable desde una interfaz web en **Streamlit**.

---

## Objetivo

Permitir que estudiantes, docentes y personal universitario realicen preguntas en lenguaje natural sobre reglamentos institucionales y reciban respuestas sintetizadas, verídicas y con citas explícitas del documento, artículo y número de página de procedencia.

---

## Arquitectura del Sistema

```text
[ Documentos (PDF/TXT) en data/raw/ ]
                 │
                 ▼
     [ Pipeline de Ingestión ]
      ├── SQLite (data/sqlite/corpus.db) ───► Índice léxico BM25
      └── ChromaDB (data/chroma_db)     ───► Búsqueda semántica
                 │
                 ▼
    [ Motor RRF (src/search/fusion_rrf.py) ]
                 │
                 ▼
       [ FastAPI (rag-api:8000) ]
                 ▲
                 │ (HTTP POST /buscar)
                 ▼
       [ Orquestador n8n (n8n:5678) ]
                 │
                 ▼ (v1/chat/completions)
   [ LLM Local: Ollama (ollama:11434 / phi3:mini) ]
                 ▲
                 │ (Webhook /consulta)
                 ▼
     [ Frontend Streamlit (Puerto 8501) ]
```

### Componentes clave
- **Ingesta y Fragmentación**: `RecursiveCharacterTextSplitter` con cálculo de hashes para evitar duplicados.
- **Base Relacional Canónica**: SQLite (`data/sqlite/corpus.db`) con esquema de fragmentos y metadatos.
- **Base Vectorial**: ChromaDB (`data/chroma_db`) empleando embeddings densos multilingües (`paraphrase-multilingual-MiniLM-L12-v2`).
- **Motor Híbrido**: BM25 + Similitud Coseno fusionados con algoritmo RRF (Reciprocal Rank Fusion).
- **Backend API**: FastAPI exponiendo endpoints seguros para búsqueda y reindexado.
- **Motor LLM Local**: Ollama ejecutando `phi3:mini` en un contenedor aislado con persistencia de pesos.
- **Orquestación de Agente**: n8n ejecutando el webhook de entrada, consulta al motor de búsqueda, ensamblado del prompt con contexto y llamada al LLM.
- **Frontend**: Streamlit con desglose de fuentes documentales, visualización de fragmentos y puntajes de coincidencia.

---

## Estructura del Repositorio

```text
RAG_seminario/
├── data/
│   ├── raw/                 # PDFs y documentos de texto a indexar
│   ├── sqlite/              # Base relacional (corpus.db) generada por el sistema
│   └── chroma_db/           # Base vectorial persistente de ChromaDB
├── frontend/
│   ├── app.py               # Aplicación web Streamlit
│   └── estilos.css          # Estilos visuales de la interfaz
├── n8n/
│   └── workflows/           # Definiciones de workflows exportados (.json)
│       └── workflow.json
├── src/
│   ├── api/
│   │   └── api.py           # API REST con FastAPI (controlador de búsqueda)
│   ├── database/
│   │   └── crud.py          # Operaciones CRUD e inicialización de SQLite
│   ├── ingestion/
│   │   └── pipeline.py      # Pipeline de extracción, división e indexación
│   └── search/
│       ├── bm25_db.py       # Índice léxico BM25 en memoria sobre SQLite
│       └── fusion_rrf.py    # Algoritmo de fusión RRF y orquestación híbrida
├── Dockerfile               # Construcción de la imagen para FastAPI / RAG core
├── docker-compose.yml       # Orquestación de servicios: rag-api, n8n y ollama
├── requirements.txt         # Dependencias Python del backend y frontend
├── README.md
└── .gitignore
```

---

## Requisitos Previos

- **Git**
- **Docker Desktop** (con backend de WSL 2 en Windows) o **Docker Engine + Docker Compose** (en Linux)
- **Python 3.10 o 3.11** (para levantar la interfaz Streamlit en la máquina local)

---

## Despliegue con Docker (Paso a Paso)

### 1. Clonar el repositorio
```bash
git clone <URL_DEL_REPOSITORIO>
cd RAG_seminario
```

Asegurarse de que existan las carpetas para el almacenamiento de datos:
```bash
mkdir -p data/raw data/sqlite data/chroma_db
```

### 2. Construir y levantar los contenedores
Desde la raíz del proyecto, ejecutar:
```bash
docker compose up --build -d
```

Verificar que los tres servicios estén corriendo (`Up`):
```bash
docker compose ps
```
Deberán figurar:
- `rag_unlar_api` en el puerto `8000`
- `n8n_unlar` en el puerto `5678`
- `ollama_llm` en el puerto `11434`

### 3. Descargar el modelo Phi-3 Mini en Ollama
Ejecutar la descarga del modelo dentro del contenedor de Ollama (se descarga una sola vez y persiste en el volumen `ollama_models`):
```bash
docker compose exec ollama ollama pull phi3:mini
```

### 4. Inicializar la base de datos e indexar documentos
Dado que la base de datos `corpus.db` y el índice de vectores no se versionan en Git, deben inicializarse por primera vez:

1. **Crear las tablas en SQLite:**
   ```bash
   docker compose exec rag-api python -m src.database.crud
   ```
   *(Salida esperada: `Base inicializada correctamente.`)*

2. **Procesar y vectorizar los documentos en `data/raw/`:**
   Colocar los PDFs o TXT en `data/raw/` y ejecutar el pipeline:
   ```bash
   docker compose exec rag-api python -m src.ingestion.pipeline
   ```
   *(Salida esperada: `Ingesta e indexación completadas. Fragmentos nuevos: X`)*

### 5. Configurar el flujo de n8n
1. Ingresar en el navegador a: `http://localhost:5678`.
2. Completar la configuración del usuario inicial de n8n si es la primera vez.
3. Ir a **Workflows** -> menú de tres puntos (`...`) en la esquina superior derecha -> **Import from File**.
4. Seleccionar el archivo `n8n/workflows/workflow.json`.
5. Verificar que los nodos internos utilicen la red interna de Docker:
   - Nodo **Buscar en Chroma DB**: `POST http://rag-api:8000/buscar`
   - Nodo **Armar Prompt**: Modelo configurado como `'phi3:mini'`
   - Nodo **Llamar LLM**: `POST http://ollama:11434/v1/chat/completions`
6. Hacer clic en **Publish** (arriba a la derecha) para dejar el webhook en estado activo.

### 6. Ejecutar la interfaz web (Streamlit)
1. Instalar las dependencias locales si aún no están instaladas:
   ```bash
   pip install -r requirements.txt
   ```
2. Ejecutar la aplicación:
   ```bash
   streamlit run frontend/app.py
   ```
3. Acceder en el navegador a: `http://localhost:8501`.

---

## Ejecución Local sin Docker (Modo Desarrollo)

Si se desea depurar o correr los componentes fuera de Docker:

1. **Crear y activar entorno virtual:**
   ```bash
   python -m venv .venv
   # En Windows:
   .venv\Scripts\activate
   # En Linux/macOS:
   source .venv/bin/activate
   ```

2. **Instalar dependencias:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Inicializar datos:**
   ```bash
   python -m src.database.crud
   python -m src.ingestion.pipeline
   ```

4. **Levantar la API FastAPI:**
   ```bash
   uvicorn src.api.api:app --reload --host 0.0.0.0 --port 8000
   ```

5. **Modo directo de prueba en Streamlit (sin n8n/LLM):**
   Para probar la recuperación híbrida directamente contra la API:
   ```bash
   # En PowerShell:
   $env:API_URL="http://localhost:8000"; streamlit run frontend/app.py

   # En Linux/Git Bash:
   API_URL="http://localhost:8000" streamlit run frontend/app.py
   ```

---

## Endpoints de la API REST

La documentación Swagger interactiva se encuentra disponible en `http://localhost:8000/docs`.

### `GET /`
Verifica el estado del servicio de búsqueda.

### `POST /buscar`
Ejecuta la recuperación híbrida (BM25 + ChromaDB + RRF) sobre SQLite.
```json
{
  "consulta": "¿Qué condiciones tienen los estudiantes para mantener la regularidad?",
  "top_k": 4,
  "audiencia": "academico"
}
```

### `POST /reindexar`
Procesa y reindexa un archivo específico depositado en `data/raw/`.
```json
{
  "documento": "Reglamento_de_Alumnos.pdf"
}
```

---

## Comandos Útiles de Mantenimiento

- **Inspeccionar registros de la API:**
  ```bash
  docker compose logs -f rag-api
  ```
- **Reindexar documentos tras agregar nuevos archivos a `data/raw/`:**
  ```bash
  docker compose exec rag-api python -m src.ingestion.pipeline
  ```
- **Detener los servicios de Docker:**
  ```bash
  docker compose down
  ```
- **Reiniciar los servicios existentes sin reconstruir:**
  ```bash
  docker compose up -d
  ```

---

## Licencia y Uso

Proyecto desarrollado con fines académicos y de investigación en el marco del Seminario RAG — Universidad Nacional de La Rioja (UNLaR).
