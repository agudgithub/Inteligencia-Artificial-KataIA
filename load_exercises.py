import os
import csv
import time
from typing import Dict, Any, Optional, List

from neo4j import GraphDatabase, basic_auth


# ============================
# Configuración Neo4j
# ============================

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "test12345")


def wait_for_neo4j(uri: str, user: str, password: str, total_timeout: int = 120, step: int = 2):
  """Espera a que Neo4j esté disponible antes de continuar."""
  deadline = time.time() + total_timeout
  last_err: Optional[Exception] = None
  intentos = 0
  print(f"Esperando Neo4j en {uri} como {user} (timeout {total_timeout}s)...", flush=True)
  while time.time() < deadline:
    intentos += 1
    try:
      driver = GraphDatabase.driver(uri, auth=basic_auth(user, password))
      with driver.session() as s:
        s.run("RETURN 1").consume()
      print(f"Conectado a Neo4j en {uri} como {user}", flush=True)
      return driver
    except Exception as e:  # pragma: no cover - robustez en entorno docker
      last_err = e
      print(f"Intento {intentos}: Neo4j no disponible ({e}); reintento en {step}s", flush=True)
      time.sleep(step)
  raise RuntimeError(f"Neo4j no respondió a tiempo: {last_err}")


driver = wait_for_neo4j(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)


def load_csv(path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    # Detectamos automáticamente si el separador es coma o punto y coma
    with open(path, newline="", encoding="latin-1") as f:
        sample = f.read(4096)
        f.seek(0)
        import csv as _csv
        dialect = _csv.Sniffer().sniff(sample, delimiters=",;")
        reader = _csv.DictReader(f, dialect=dialect)
        for row in reader:
            rows.append(row)
    return rows


def upsert_exercise(tx, row: Dict[str, str]) -> None:
    """
    Crea/actualiza un Exercise y sus slots básicos a partir de una fila del CSV.
    Usa:
      - id
      - tema_principal
      - dificultad
      - enunciado
      - tests_publicos
      - tests_privados
    """

    # Sanitizamos valores por si vienen vacíos o None
    eid = (row.get("id") or "").strip()

    # Usamos tema_principal directamente como código de Tema del grafo
    # (por ejemplo: variables_y_tipos, control_de_flujo, estructuras_de_datos, errores_y_debugging)
    tema_codigo = (row.get("tema_principal") or "").strip() or "variables_y_tipos"
    dificultad = (row.get("dificultad") or "").strip() or "facil"
    enunciado = (row.get("enunciado") or "").strip()
    tests_publicos = (row.get("tests_publicos") or "").strip()
    tests_privados = (row.get("tests_privados") or "").strip()

    q = """
    // 1) MERGE del ejercicio como Frame + Exercise
    MERGE (e:Frame:Exercise {name:$id})
      ON CREATE SET e.created_at = datetime()
      ON MATCH  SET e.last_updated_at = datetime()

    // 2) Conectar el ejercicio a todos los PythonConcept cubiertos por el Tema
    WITH e
    MATCH (t:Tema {codigo:$tema})-[:CUBRE_CONCEPTO]->(pc:PythonConcept)
    MERGE (e)-[:APUNTA_A]->(pc)

    // 3) Slots de enunciado/tests/dificultad
    MATCH (s_en:Slot {name:'enunciado'}),
          (s_pub:Slot {name:'tests_publicos'}),
          (s_priv:Slot {name:'tests_privados'}),
          (s_diff:Slot {name:'dificultad'})

    MERGE (e)-[r_en:HAS_SLOT]->(s_en)
      ON CREATE SET r_en.value = $enunciado, r_en.updated_at = datetime()
      ON MATCH  SET r_en.value = $enunciado, r_en.updated_at = datetime()

    MERGE (e)-[r_pb:HAS_SLOT]->(s_pub)
      ON CREATE SET r_pb.value = $tests_publicos, r_pb.updated_at = datetime()
      ON MATCH  SET r_pb.value = $tests_publicos, r_pb.updated_at = datetime()

    MERGE (e)-[r_pr:HAS_SLOT]->(s_priv)
      ON CREATE SET r_pr.value = $tests_privados, r_pr.updated_at = datetime()
      ON MATCH  SET r_pr.value = $tests_privados, r_pr.updated_at = datetime()

    MERGE (e)-[r_df:HAS_SLOT]->(s_diff)
      ON CREATE SET r_df.value = $dificultad, r_df.updated_at = datetime()
      ON MATCH  SET r_df.value = $dificultad, r_df.updated_at = datetime()
    """
    tx.run(
        q,
        id=eid,
        tema=tema_codigo,
        dificultad=dificultad,
        enunciado=enunciado,
        tests_publicos=tests_publicos,
        tests_privados=tests_privados,
    )


def main():
    csv_path = "exercises.csv"
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"No se encontró {csv_path} en el directorio actual.")

    rows = load_csv(csv_path)
    print(f"Leyendo {len(rows)} ejercicios desde {csv_path}")

    with driver.session() as session:
        for row in rows:
            eid = row.get("id", "").strip()
            if not eid:
                print("Fila sin 'id', se salta:", row)
                continue
            print(f"Upsert ejercicio {eid}...")
            session.execute_write(upsert_exercise, row)

    print("Carga de ejercicios completada.")


if __name__ == "__main__":
    try:
        main()
    finally:
        driver.close()
