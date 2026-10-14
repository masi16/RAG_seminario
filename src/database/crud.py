#Operaciones CRUD en la tabla fragmentos de sqlite

import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data" / "sqlite" / "corpus.db"


def get_connection() -> sqlite3.Connection:
    """Crea la conexión a SQLite y configura el retorno como diccionario"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(str(DB_PATH))
    conexion.row_factory = sqlite3.Row
    return conexion


def inicializar_db() -> None:
    with get_connection() as conexion:
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS fragmentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash TEXT UNIQUE NOT NULL,
                texto TEXT NOT NULL,
                documento TEXT NOT NULL,
                pagina TEXT NOT NULL,
                articulo TEXT DEFAULT '',
                audiencia TEXT DEFAULT 'general'
            )
        """)
        conexion.commit()


# 1. CREATE (Crear / Insertar)

def insertar_fragmento(
    hash_id: str,
    texto: str,
    documento: str,
    pagina: str,
    articulo: str = "",
    audiencia: str = "general"
) -> Optional[int]:
    """Inserta un único fragmento. Devuelve el id insertado o None si ya existía"""
    query = """INSERT OR IGNORE INTO fragmentos (hash, texto, documento, pagina, articulo, audiencia) VALUES (?, ?, ?, ?, ?, ?)"""
    with get_connection() as conexion:
        cursor = conexion.cursor()
        cursor.execute(query, (hash_id, texto, documento, str(pagina), articulo, audiencia))
        conexion.commit()
        return cursor.lastrowid if cursor.rowcount > 0 else None


def insertar_fragmentos_lote(fragmentos: List[Dict[str, Any]]) -> int:
    """Inserta múltiples fragmentos en una sola transacción. Devuelve la cantidad de registros nuevos efectivamente insertados"""
    if not fragmentos:
        return 0

    query = """ INSERT OR IGNORE INTO fragmentos (hash, texto, documento, pagina, articulo, audiencia) VALUES (:hash, :texto, :documento, :pagina, :articulo, :audiencia)"""

    with get_connection() as conexion:
        cursor = conexion.cursor()
        filas_antes = conexion.total_changes
        cursor.executemany(query, fragmentos)
        conexion.commit()
        return conexion.total_changes - filas_antes



# 2. READ (Leer / Consultar)

def leer_por_id(fragmento_id: int) -> Optional[Dict[str, Any]]:
    """Busca un fragmento por su ID entero"""
    with get_connection() as conexion:
        cursor = conexion.cursor()
        cursor.execute("SELECT * FROM fragmentos WHERE id = ?", (fragmento_id,))
        fila = cursor.fetchone()
        return dict(fila) if fila else None


def leer_por_hash(hash_id: str) -> Optional[Dict[str, Any]]:
    """Busca un fragmento por su hash"""
    with get_connection() as conexion:
        cursor = conexion.cursor()
        cursor.execute("SELECT * FROM fragmentos WHERE hash = ?", (hash_id,))
        fila = cursor.fetchone()
        return dict(fila) if fila else None


def leer_por_hashes(hashes: List[str]) -> List[Dict[str, Any]]:
    """Devuelve los fragmentos preservando el orden exacto de la lista de hashes. Esencial para que RRF y Chroma devuelvan el ranking respetado"""
    if not hashes:
        return []

    placeholders = ",".join(["?"] * len(hashes))
    query = f"SELECT * FROM fragmentos WHERE hash IN ({placeholders})"

    with get_connection() as conexion:
        cursor = conexion.cursor()
        cursor.execute(query, hashes)
        filas = {row["hash"]: dict(row) for row in cursor.fetchall()}

    return [filas[h] for h in hashes if h in filas]


def listar_fragmentos(audiencia: str = "todos", limite: int = 100) -> List[Dict[str, Any]]:
    """Lista fragmentos con opción de filtrar por audiencia"""
    with get_connection() as conexion:
        cursor = conexion.cursor()
        if audiencia != "todos":
            cursor.execute("SELECT * FROM fragmentos WHERE audiencia = ? LIMIT ?", (audiencia, limite))
        else:
            cursor.execute("SELECT * FROM fragmentos LIMIT ?", (limite,))
        return [dict(f) for f in cursor.fetchall()]


#UPDATE

def actualizar_fragmento(
    hash_id: str,
    articulo: Optional[str] = None,
    audiencia: Optional[str] = None,
    texto: Optional[str] = None
) -> bool:
    
    """Actualiza campos específicos de un fragmento dado su hash. Devuelve True si modificó alguna fila"""
   
    campos = []
    valores = []

    if articulo is not None:
        campos.append("articulo = ?")
        valores.append(articulo)
    if audiencia is not None:
        campos.append("audiencia = ?")
        valores.append(audiencia)
    if texto is not None:
        campos.append("texto = ?")
        valores.append(texto)

    if not campos:
        return False

    valores.append(hash_id)
    query = f"UPDATE fragmentos SET {', '.join(campos)} WHERE hash = ?"

    with get_connection() as conexion:
        cursor = conexion.cursor()
        cursor.execute(query, valores)
        conexion.commit()
        return cursor.rowcount > 0


# 4. DELETE (Eliminar)

def eliminar_por_hash(hash_id: str) -> bool:
    """Elimina un fragmento por su hash"""
    with get_connection() as conexion:
        cursor = conexion.cursor()
        cursor.execute("DELETE FROM fragmentos WHERE hash = ?", (hash_id,))
        conexion.commit()
        return cursor.rowcount > 0


def eliminar_por_documento(nombre_documento: str) -> int:
    """ Elimina todos los fragmentos asociados a un archivo PDF"""
    with get_connection() as conexion:
        cursor = conexion.cursor()
        cursor.execute("DELETE FROM fragmentos WHERE documento = ?", (nombre_documento,))
        conexion.commit()
        return cursor.rowcount



#INICIALIZAR BASE DE DATOS
if __name__ == "__main__":
    inicializar_db()
    print("Base inicializada correctamente.")