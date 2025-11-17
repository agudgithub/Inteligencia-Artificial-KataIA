import os
import sys
import argparse
from typing import Any, Optional, List

from neo4j import GraphDatabase, basic_auth
from clasificador_temas import predecir_tema
import json

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import PrivateAttr


# ──────────────────────────────────────────────
# 1) Conexión a Neo4j
# ──────────────────────────────────────────────
URI  = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PWD  = os.environ.get("NEO4J_PASSWORD", "test12345")

driver = GraphDatabase.driver(URI, auth=basic_auth(USER, PWD))

# Estudiante por sesión (puede ser env var o login simple)
STUDENT_NAME = os.getenv("STUDENT_NAME", None)


# ──────────────────────────────────────────────
# 2) Gestión de estudiante y estado
# ──────────────────────────────────────────────
def ensure_student_and_state(sess, student_name: str):
    """
    Asegura que exista el Estudiante y su StudentState con HAS_SLOT
    inicializados para maestria/confianza/frustracion.
    """
    cy = """
    MERGE (e:Estudiante:Frame {name:$name})
    MERGE (st:StudentState:Frame {name: 'Estado_' + $name})
    MERGE (e)-[:TIENE_ESTADO]->(st)
    WITH st
    MATCH (s1:Slot {name:'maestria'}),
          (s2:Slot {name:'confianza'}),
          (s3:Slot {name:'frustracion'})
    MERGE (st)-[r1:HAS_SLOT]->(s1)
      ON CREATE SET r1.value='{}', r1.updated_at=datetime()
    MERGE (st)-[r2:HAS_SLOT]->(s2)
      ON CREATE SET r2.value='0.5', r2.updated_at=datetime()
    MERGE (st)-[r3:HAS_SLOT]->(s3)
      ON CREATE SET r3.value='0.3', r3.updated_at=datetime()
    RETURN st
    """
    sess.run(cy, name=student_name)

def update_student_state(sess, student_name: str, tema: str,
                         d_mae: float, d_conf: float, d_fru: float):
    """Ajusta maestría por conceptos del tema y confianza/frustración.

    Los deltas se calculan afuera (según el texto de la pregunta) y acá
    solo se aplican y se deja marcado updated_at para que el daemon
    detecte cambios.
    """
    # Obtener conceptos del tema
    cy_concepts = """
    MATCH (t:Tema {codigo:$tema})-[:CUBRE_CONCEPTO]->(pc:PythonConcept)
    RETURN collect(pc.name) AS concepts
    """
    rec_concepts = sess.run(cy_concepts, tema=tema).single()
    concepts = rec_concepts["concepts"] if rec_concepts else []

    # Obtener valores actuales del StudentState
    cy_state = """
    MATCH (:Estudiante {name:$name})-[:TIENE_ESTADO]->(st:StudentState)
    OPTIONAL MATCH (st)-[rm:HAS_SLOT]->(:Slot {name:'maestria'})
    OPTIONAL MATCH (st)-[rc:HAS_SLOT]->(:Slot {name:'confianza'})
    OPTIONAL MATCH (st)-[rf:HAS_SLOT]->(:Slot {name:'frustracion'})
    RETURN coalesce(rm.value,'{}') AS v_mae,
           coalesce(toFloat(rc.value),0.5) AS v_conf,
           coalesce(toFloat(rf.value),0.3) AS v_fru
    """
    rec = sess.run(cy_state, name=student_name).single()
    if not rec:
        return

    # Parsear maestría (dict JSON)
    try:
        mae = json.loads(rec["v_mae"]) if rec["v_mae"] else {}
    except:
        mae = {}
    
    # Actualizar maestría por conceptos del tema
    for c in concepts:
        mae[c] = max(0.0, min(1.0, float(mae.get(c, 0.4)) + d_mae))

    # Actualizar confianza y frustración (escalares)
    v_conf = max(0.0, min(1.0, float(rec["v_conf"]) + d_conf))
    v_fru  = max(0.0, min(1.0, float(rec["v_fru"]) + d_fru))

    # Escribir de vuelta con updated_at=datetime()
    sess.run("""
        MATCH (:Estudiante {name:$name})-[:TIENE_ESTADO]->(st:StudentState)
        MATCH (s1:Slot {name:'maestria'}),
              (s2:Slot {name:'confianza'}),
              (s3:Slot {name:'frustracion'})
        MERGE (st)-[r1:HAS_SLOT]->(s1)
          SET r1.value=$mae, r1.updated_at=datetime()
        MERGE (st)-[r2:HAS_SLOT]->(s2)
          SET r2.value=toString($conf), r2.updated_at=datetime()
        MERGE (st)-[r3:HAS_SLOT]->(s3)
          SET r3.value=toString($fru), r3.updated_at=datetime()
    """, name=student_name, mae=json.dumps(mae), conf=v_conf, fru=v_fru)


# ──────────────────────────────────────────────
# 3) Contexto del grafo (tema + estado + señales)
# ──────────────────────────────────────────────
def build_graph_context(question_text: str, student_name: str):
    """[DEPRECATED] Mantener mientras migramos totalmente al GraphTutorRetriever.
    Uso principal: fallback si el retriever falla o devuelve vacío.
    Hace clasificación de tema, obtiene conceptos/ejemplos y estado del estudiante + señales.
    Retorna (contexto_str, tema_pred).
    """
    tema_pred = predecir_tema(question_text)
    print(f"🧠 Tema predicho: {tema_pred}")

    with driver.session() as sess:
        ensure_student_and_state(sess, student_name)

        # Contexto por tema
        rec_tema = sess.run("""
            MATCH (t:Tema {codigo:$tema})
            OPTIONAL MATCH (t)-[:CUBRE_CONCEPTO]->(pc:PythonConcept)
            OPTIONAL MATCH (q:Question)-[:CLASIFICADA_COMO]->(t)
            RETURN t.codigo AS tema_codigo, t.nombre AS tema_nombre,
                   collect(DISTINCT pc.name) AS conceptos,
                   collect(DISTINCT q.texto)[0..5] AS ejemplos_preguntas
        """, tema=tema_pred).single()

        # Estado del estudiante
        rec_est = sess.run("""
            MATCH (:Estudiante {name:$name})-[:TIENE_ESTADO]->(st:StudentState)
            OPTIONAL MATCH (st)-[rc:HAS_SLOT]->(:Slot {name:'confianza'})
            OPTIONAL MATCH (st)-[rf:HAS_SLOT]->(:Slot {name:'frustracion'})
            OPTIONAL MATCH (st)-[rm:HAS_SLOT]->(:Slot {name:'maestria'})
            RETURN coalesce(rc.fuzzy_defuzz, toFloat(rc.value)) AS conf,
                   coalesce(rf.fuzzy_defuzz, toFloat(rf.value)) AS fru,
                   coalesce(rm.value,'{}') AS mae_json,
                   rc.fuzzy_label AS conf_label,
                   rf.fuzzy_label AS fru_label
        """, name=student_name).single()

        # Últimas señales/intervenciones
        rec_signals = sess.run("""
            MATCH (:Estudiante {name:$name})-[:TIENE_ESTADO]->(st:StudentState)
            OPTIONAL MATCH (st)-[r:REGISTRA]->(n)
            WHERE n:Intervencion OR n:IntervencionAfectiva
            WITH n, r
            ORDER BY coalesce(r.at, n.created_at) DESC
            LIMIT 3
            RETURN collect({
                tipo: labels(n)[0],
                motivo: coalesce(n.motivo, n.tipo, 'desconocido')
            }) AS signals
        """, name=student_name).single()

    # Armar texto de contexto
    lines = []
    if not rec_tema:
        lines.append("No se encontró el tema en el grafo. Usa tu conocimiento general de Python.")
    else:
        tema_codigo = rec_tema["tema_codigo"]
        tema_nombre = rec_tema["tema_nombre"] or tema_codigo
        conceptos = rec_tema["conceptos"] or []
        ejemplos  = rec_tema["ejemplos_preguntas"] or []
        
        lines.append("Contexto del grafo TutorIA (Neo4j):")
        lines.append(f"- Tema detectado: {tema_nombre} (codigo: {tema_codigo})")
        if conceptos:
            lines.append("- Conceptos de Python asociados:")
            for c in conceptos:
                lines.append(f"    · {c}")
        if ejemplos:
            lines.append("- Ejemplos de dudas previas:")
            for e in ejemplos:
                lines.append(f"    · {e}")

    # Estado del estudiante (cualitativo, sin mostrar valores numéricos exactos)
    if rec_est:
        lines.append(f"\nEstado de {student_name}:")
        conf = rec_est["conf"]
        fru = rec_est["fru"]
        mae_json = rec_est["mae_json"]
        conf_label = rec_est["conf_label"]
        fru_label = rec_est["fru_label"]

        if conf is not None:
            lines.append(f"- Confianza: {conf_label or 'sin calcular'}")
        if fru is not None:
            lines.append(f"- Frustración: {fru_label or 'sin calcular'}")
        try:
            mae_dict = json.loads(mae_json) if mae_json else {}
            if mae_dict:
                altos = [k for k, v in mae_dict.items() if float(v) >= 0.7]
                bajos = [k for k, v in mae_dict.items() if float(v) < 0.4]
                if altos:
                    lines.append("- Conceptos con buena maestría: " + ", ".join(altos))
                if bajos:
                    lines.append("- Conceptos a reforzar: " + ", ".join(bajos))
        except Exception:
            pass

    # Señales recientes
    if rec_signals and rec_signals["signals"]:
        lines.append("\nSeñales/Intervenciones recientes:")
        for s in rec_signals["signals"]:
            lines.append(f"  - {s['tipo']}: {s['motivo']}")

    return "\n".join(lines), tema_pred


# ──────────────────────────────────────────────
# 4) Modelo LLM en Ollama
# ──────────────────────────────────────────────
llm = ChatOllama(
    model="llama3",
    temperature=0.2,
    base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
)


def get_conversation_history(sess, student_name: str, limit: int = 3):
    """
    Obtiene las últimas N preguntas y respuestas del estudiante.
    Retorna lista de tuplas [(pregunta, respuesta), ...]
    """
    cy = """
    MATCH (e:Estudiante {name:$name})-[:PREGUNTA]->(q:Question)
    OPTIONAL MATCH (e)-[:RECIBE]->(r:Respuesta)
    WHERE r.creada_en >= q.creada_en
    WITH q, r
    ORDER BY q.creada_en DESC
    LIMIT $limit
    RETURN q.texto AS pregunta, r.texto AS respuesta
    ORDER BY q.creada_en ASC
    """
    records = sess.run(cy, name=student_name, limit=limit)
    history = []
    for rec in records:
        if rec["pregunta"] and rec["respuesta"]:
            history.append((rec["pregunta"], rec["respuesta"]))
    return history


# ──────────────────────────────────────────────
# Retriever formal (LangChain) para contexto estructurado
# ──────────────────────────────────────────────
class GraphTutorRetriever(BaseRetriever):
    """Recupera documentos estructurados del grafo Neo4j para una pregunta.

    Documentos generados (metadata.type):
    - tema: descripción básica del tema detectado.
    - conceptos: lista de conceptos asociados.
    - ejemplos: preguntas previas (hasta 5).
    - estado: estado cualitativo del estudiante (confianza/frustración/maestría resumida).
    - intervenciones: últimas señales/intervenciones (hasta 3).
    """
    limit_examples: int = 5
    student_name: Optional[str] = None
    last_tema: Optional[str] = None

    _driver: Any = PrivateAttr()

    def __init__(self, driver, limit_examples: int = 5, **data: Any):
        super().__init__(limit_examples=limit_examples, **data)
        self._driver = driver

    def set_student(self, student_name: str):
        self.student_name = student_name

    def _get_recommended_exercises(self, sess, tema_codigo: str, dificultad: Optional[str] = None) -> List[dict]:
        """Devuelve hasta 3 ejercicios recomendados para un tema y dificultad.

        Usa Exercise->APUNTA_A->PythonConcept cubiertos por el Tema.
        """
        if not tema_codigo:
            return []

        recs = sess.run(
            """
            MATCH (t:Tema {codigo:$tema})-[:CUBRE_CONCEPTO]->(pc:PythonConcept)
            MATCH (e:Exercise:Frame)-[:APUNTA_A]->(pc)
            OPTIONAL MATCH (e)-[r_diff:HAS_SLOT]->(:Slot {name:'dificultad'})
            WITH DISTINCT e, coalesce(r_diff.value, 'facil') AS dificultad
            WHERE $dificultad IS NULL OR dificultad = $dificultad
            OPTIONAL MATCH (e)-[r_en:HAS_SLOT]->(:Slot {name:'enunciado'})
            OPTIONAL MATCH (e)-[r_pub:HAS_SLOT]->(:Slot {name:'tests_publicos'})
            RETURN e.name AS id,
                   dificultad,
                   r_en.value AS enunciado,
                   r_pub.value AS tests_publicos
            LIMIT 3
            """,
            tema=tema_codigo,
            dificultad=dificultad,
        )
        return [r.data() for r in recs]

    def _infer_target_difficulty(self, sess, tema_codigo: str) -> Optional[str]:
        """Elige dificultad objetivo a partir de confianza/frustración y maestría.

        Heurística simple:
        - frustración alta (>=0.7) o confianza baja (<0.4) → 'facil'
        - frustración baja (<0.4) y confianza alta (>=0.7) → 'media'
        - caso contrario → None (cualquier dificultad)
        """
        rec = sess.run(
            """
            MATCH (:Estudiante {name:$name})-[:TIENE_ESTADO]->(st:StudentState)
            OPTIONAL MATCH (st)-[rc:HAS_SLOT]->(:Slot {name:'confianza'})
            OPTIONAL MATCH (st)-[rf:HAS_SLOT]->(:Slot {name:'frustracion'})
            OPTIONAL MATCH (st)-[rm:HAS_SLOT]->(:Slot {name:'maestria'})
            RETURN coalesce(rc.fuzzy_defuzz, toFloat(rc.value)) AS conf,
                   coalesce(rf.fuzzy_defuzz, toFloat(rf.value)) AS fru,
                   coalesce(rm.value,'{}') AS mae_json
            """,
            name=self.student_name,
        ).single()
        if not rec:
            return None

        try:
            conf = float(rec["conf"]) if rec["conf"] is not None else 0.5
        except Exception:
            conf = 0.5
        try:
            fru = float(rec["fru"]) if rec["fru"] is not None else 0.3
        except Exception:
            fru = 0.3

        if fru >= 0.7 or conf < 0.4:
            return "facil"
        if fru < 0.4 and conf >= 0.7:
            return "media"
        return None

    def _get_relevant_documents(self, query: str) -> List[Document]:  # LangChain internal
        if not self.student_name:
            raise ValueError("student_name no seteado en retriever")

        # Reglas fuertes por palabras clave en la pregunta para fijar el tema
        q_lower = query.lower()
        if "funcion" in q_lower or "función" in q_lower:
            tema_pred = "funciones"
        elif "control de flujo" in q_lower:
            tema_pred = "control_de_flujo"
        elif "lista" in q_lower or "listas" in q_lower:
            tema_pred = "estructuras_de_datos"
        elif "error" in q_lower or "exception" in q_lower:
            tema_pred = "errores_y_debugging"
        else:
            tema_pred = predecir_tema(query)

        self.last_tema = tema_pred

        docs: List[Document] = []
        with self._driver.session() as sess:
            ensure_student_and_state(sess, self.student_name)

            rec_tema = sess.run(
                """
                MATCH (t:Tema {codigo:$tema})
                OPTIONAL MATCH (t)-[:CUBRE_CONCEPTO]->(pc:PythonConcept)
                OPTIONAL MATCH (q:Question)-[:CLASIFICADA_COMO]->(t)
                RETURN t.codigo AS tema_codigo,
                       t.nombre AS tema_nombre,
                       collect(DISTINCT pc.name) AS conceptos,
                       collect(DISTINCT q.texto)[0..$lim] AS ejemplos_preguntas
                """,
                tema=tema_pred,
                lim=self.limit_examples,
            ).single()

            if rec_tema:
                tema_codigo = rec_tema["tema_codigo"]
                tema_nombre = rec_tema["tema_nombre"] or tema_codigo
                conceptos = rec_tema["conceptos"] or []
                ejemplos = rec_tema["ejemplos_preguntas"] or []
                docs.append(
                    Document(
                        page_content=f"Tema detectado: {tema_nombre} (codigo: {tema_codigo})",
                        metadata={"type": "tema", "tema": tema_codigo},
                    )
                )
                if conceptos:
                    docs.append(
                        Document(
                            page_content="\n".join(conceptos),
                            metadata={"type": "conceptos", "tema": tema_codigo},
                        )
                    )
                if ejemplos:
                    docs.append(
                        Document(
                            page_content="\n".join(ejemplos),
                            metadata={"type": "ejemplos", "tema": tema_codigo},
                        )
                    )

                # Ejercicios recomendados para el tema detectado, adaptados al estado
                target_diff = self._infer_target_difficulty(sess, tema_codigo)
                ejercicios = self._get_recommended_exercises(sess, tema_codigo, dificultad=target_diff)
                if ejercicios:
                    if target_diff:
                        lines = [
                            "Ejercicios recomendados para este tema (dificultad adaptada al estado del estudiante).",
                            f"Dificultad objetivo sugerida: {target_diff}.",
                            "",
                            "Lista de ejercicios:",
                        ]
                    else:
                        lines = ["Ejercicios recomendados para este tema:"]
                    for ex in ejercicios:
                        enun = (ex.get("enunciado") or "").strip()
                        if len(enun) > 280:
                            enun = enun[:280] + "..."
                        lines.append(
                            f"- {ex.get('id')} (dificultad: {ex.get('dificultad')})\n  Enunciado: {enun}"
                        )
                    docs.append(
                        Document(
                            page_content="\n".join(lines),
                            metadata={"type": "ejercicios", "tema": tema_codigo},
                        )
                    )

            # Último Attempt del estudiante (si existe)
            rec_attempt = sess.run(
                """
                MATCH (e:Estudiante {name:$name})-[:REALIZA]->(a:Attempt)
                OPTIONAL MATCH (a)-[r_cod:HAS_SLOT]->(:Slot {name:'codigo'})
                OPTIONAL MATCH (a)-[r_res:HAS_SLOT]->(:Slot {name:'resultado_tests'})
                WITH a, r_cod, r_res
                ORDER BY a.name DESC
                LIMIT 1
                RETURN a.name AS intento_id,
                       r_cod.value AS codigo,
                       r_res.value AS resultado
                """,
                name=self.student_name,
            ).single()
            if rec_attempt and rec_attempt["intento_id"]:
                codigo = (rec_attempt.get("codigo") or "").strip()
                resumen_codigo = codigo.split("\n")[0] if codigo else "(sin código registrado)"
                lines_attempt = [
                    f"Último attempt registrado (id: {rec_attempt['intento_id']}):",
                    f"- Resultado de tests: {rec_attempt.get('resultado') or 'sin datos'}",
                    f"- Primera línea de código enviado: {resumen_codigo}",
                ]
                docs.append(
                    Document(
                        page_content="\n".join(lines_attempt),
                        metadata={"type": "attempt", "tema": tema_pred},
                    )
                )

            rec_est = sess.run(
                """
                MATCH (:Estudiante {name:$name})-[:TIENE_ESTADO]->(st:StudentState)
                OPTIONAL MATCH (st)-[rc:HAS_SLOT]->(:Slot {name:'confianza'})
                OPTIONAL MATCH (st)-[rf:HAS_SLOT]->(:Slot {name:'frustracion'})
                OPTIONAL MATCH (st)-[rm:HAS_SLOT]->(:Slot {name:'maestria'})
                RETURN coalesce(rc.fuzzy_defuzz, toFloat(rc.value)) AS conf,
                       coalesce(rf.fuzzy_defuzz, toFloat(rf.value)) AS fru,
                       coalesce(rm.value,'{}') AS mae_json,
                       rc.fuzzy_label AS conf_label,
                       rf.fuzzy_label AS fru_label
                """,
                name=self.student_name,
            ).single()
            if rec_est:
                try:
                    mae_dict = json.loads(rec_est["mae_json"]) if rec_est["mae_json"] else {}
                except Exception:
                    mae_dict = {}
                altos = [k for k, v in mae_dict.items() if float(v) >= 0.7]
                bajos = [k for k, v in mae_dict.items() if float(v) < 0.4]
                estado_lines = []
                estado_lines.append(f"Confianza: {rec_est['conf_label'] or 'sin calcular'}")
                estado_lines.append(f"Frustración: {rec_est['fru_label'] or 'sin calcular'}")
                if altos:
                    estado_lines.append("Buena maestría: " + ", ".join(altos))
                if bajos:
                    estado_lines.append("A reforzar: " + ", ".join(bajos))
                docs.append(
                    Document(
                        page_content="\n".join(estado_lines),
                        metadata={"type": "estado", "tema": tema_pred},
                    )
                )

            rec_signals = sess.run(
                """
                MATCH (:Estudiante {name:$name})-[:TIENE_ESTADO]->(st:StudentState)
                OPTIONAL MATCH (st)-[r:REGISTRA]->(n)
                WHERE n:Intervencion OR n:IntervencionAfectiva
                WITH n, r ORDER BY coalesce(r.at, n.created_at) DESC LIMIT 3
                RETURN collect({ tipo: labels(n)[0], motivo: coalesce(n.motivo, n.tipo, 'desconocido') }) AS signals
                """,
                name=self.student_name,
            ).single()
            if rec_signals and rec_signals["signals"]:
                sig_lines = []
                for s in rec_signals["signals"]:
                    sig_lines.append(f"{s['tipo']}: {s['motivo']}")
                docs.append(
                    Document(
                        page_content="\n".join(sig_lines),
                        metadata={"type": "intervenciones", "tema": tema_pred},
                    )
                )

        return docs


# Instancia global del retriever
retriever = GraphTutorRetriever(driver)


def answer_with_llm(question_text: str, student_name: str) -> str:
    """
    Pregunta del usuario → contexto de grafo → LLM responde como tutor.
    Registra Q/A y actualiza estado del estudiante.
    """
    # Obtener historial de conversación para contexto
    with driver.session() as sess:
        conv_history = get_conversation_history(sess, student_name, limit=3)
    
    # Clasificar tipo de pregunta con el LLM (meta vs técnica)
    classifier_system = SystemMessage(
        content=(
            "Sos un clasificador de preguntas. Devolvés SOLO un JSON con la clave 'tipo'. "
            "Valores posibles: 'meta' (pregunta sobre progreso/estado/feedback del estudiante) o "
            "'tecnica' (pregunta sobre Python/código/conceptos). "
            "Ejemplo: {\"tipo\": \"meta\"}"
        )
    )
    classifier_user = HumanMessage(
        content=f"Pregunta: {question_text}\n\nClasificá esta pregunta."
    )
    
    classifier_resp = llm.invoke([classifier_system, classifier_user])
    try:
        classifier_json = json.loads(classifier_resp.content.strip())
        is_meta = (classifier_json.get("tipo") == "meta")
    except Exception:
        is_meta = False  # fallback: tratar como técnica

    if is_meta:
        # Construir mensajes con historial para preguntas meta
        messages = [
            SystemMessage(
                content=(
                    "Sos un tutor de Python y además das feedback motivacional. "
                    "La estudiante te pregunta cómo viene aprendiendo; respondé de forma honesta, "
                    "breve y motivadora, sin entrar en detalles técnicos de código."
                )
            )
        ]
        
        # Agregar historial si existe
        for q, r in conv_history:
            messages.append(HumanMessage(content=q))
            messages.append(SystemMessage(content=r))
        
        # Pregunta actual
        messages.append(HumanMessage(content=question_text))

        print("🕒 Generando respuesta con el modelo...\n")
        full_text = ""
        for chunk in llm.stream(messages):
            text = chunk.content
            full_text += text
            print(text, end="", flush=True)
        print()

        with driver.session() as sess:
            ensure_student_and_state(sess, student_name)
            sess.run(
                """
                MERGE (e:Estudiante {name:$name})
                MERGE (t:Tema {codigo:$tema}) ON CREATE SET t.nombre = $tema
                WITH e, t
                CREATE (q:Question:Frame {
                    name: 'Q_' + toString(timestamp()),
                    texto: $qt,
                    tema: $tema,
                    creada_en: datetime()
                })
                MERGE (q)-[:CLASIFICADA_COMO]->(t)
                MERGE (e)-[:PREGUNTA]->(q)
                WITH e
                MERGE (tu:TutorIA)
                CREATE (r:Respuesta:Frame {
                    name: 'R_' + toString(timestamp()),
                    texto: $rt,
                    creada_en: datetime()
                })
                MERGE (tu)-[:ENTREGA]->(r)
                MERGE (e)-[:RECIBE]->(r)
                """,
                name=student_name,
                qt=question_text,
                rt=full_text,
                tema="meta_feedback",
            )

        return full_text

    # Flujo normal: usar retriever con fallback + clasificación emocional

    # 1) Pedir al LLM una etiqueta emocional estructurada (JSON)
    emo_system = SystemMessage(
        content=(
            "Sos un clasificador de estado emocional del estudiante. "
            "Devolvés SOLO un JSON válido en una sola línea, sin texto extra. "
            "El JSON debe tener las claves: confianza_impacto y frustracion_impacto, "
            "cada una con uno de estos valores: 'sube', 'baja' o 'neutro'."
        )
    )
    emo_user = HumanMessage(
        content=(
            "Texto de la pregunta del estudiante: "
            f"""{question_text}""""\n"
            "Analizá este texto y decidí si la pregunta refleja que la confianza "
            "del estudiante sube, baja o queda neutra, y lo mismo para la frustración.\n"
            "Recordá: devolvé SOLO el JSON. Ejemplo: {\"confianza_impacto\": \"baja\", \"frustracion_impacto\": \"sube\"}."
        )
    )

    emo_resp = llm.invoke([emo_system, emo_user])
    emo_text = emo_resp.content.strip()

    d_mae = 0.03
    d_conf = 0.0
    d_fru = 0.0

    try:
        emo_json = json.loads(emo_text)
        conf_imp = emo_json.get("confianza_impacto", "neutro")
        fru_imp = emo_json.get("frustracion_impacto", "neutro")

        if conf_imp == "sube":
            d_conf = +0.08
        elif conf_imp == "baja":
            d_conf = -0.08
        else:
            d_conf = +0.02  # leve subida por interacción

        if fru_imp == "sube":
            d_fru = +0.10
        elif fru_imp == "baja":
            d_fru = -0.08
        else:
            d_fru = 0.0
    except Exception:
        # Fallback neutro si el JSON vino mal
        d_conf = +0.02
        d_fru = 0.0

    # Detectar si la pregunta es principalmente de recomendación de ejercicio
    q_lower = question_text.lower()
    pide_ejercicio = any(
        kw in q_lower
        for kw in [
            "ejercicio",
            "ejercicios",
            "practicar",
            "otro ejercicio",
            "otro",
            "recomendame",
            "recomendarme",
            "recomendá",
            "recomienda",
        ]
    )
    pide_otro = "otro ejercicio" in q_lower or q_lower.strip() in {"otro", "otro mas", "otro más"}

    # 2) Obtener contexto vía retriever (fallback legacy)
    retriever.set_student(student_name)
    try:
        docs = retriever.invoke(question_text)
        if not docs:
            raise ValueError("Retriever vacío")
        context_blocks = []
        for d in docs:
            context_blocks.append(f"[{d.metadata.get('type','info')}] {d.page_content}")
        graph_context = "\n".join(context_blocks)
        tema_pred = retriever.last_tema or predecir_tema(question_text)
    except Exception:
        # Fallback al método legacy
        graph_context, tema_pred = build_graph_context(question_text, student_name)

    # Si corresponde, elegir un ejercicio concreto desde catálogo (sin inventar)
    ejercicio_seleccionado = None
    if pide_ejercicio:
        with driver.session() as sess:
            # Inferir dificultad objetivo según estado del estudiante
            try:
                dificultad_obj = retriever._infer_target_difficulty(sess, tema_pred)
            except Exception:
                dificultad_obj = None

            # Obtener candidatos por tema + dificultad
            try:
                recs = retriever._get_recommended_exercises(sess, tema_pred, dificultad_obj)
            except Exception:
                recs = []

            candidatos_unicos = [r.get("id") for r in recs if r.get("id")]

            # Leer último ejercicio recomendado desde StudentState
            last_id = None
            if candidatos_unicos:
                rec_last = sess.run(
                    """
                    MATCH (e:Estudiante {name:$name})-[:TIENE_ESTADO]->(st:StudentState)
                    OPTIONAL MATCH (st)-[r:HAS_SLOT]->(:Slot {name:'ultimo_ejercicio_recomendado'})
                    RETURN r.value AS last_id
                    """,
                    name=student_name,
                ).single()
                last_id = rec_last["last_id"] if rec_last else None

            candidatos_rotados = candidatos_unicos

            if last_id and candidatos_unicos:
                # Si hay más de uno, sacamos el último para rotar
                if len(candidatos_unicos) > 1 and last_id in candidatos_unicos:
                    candidatos_rotados = [c for c in candidatos_unicos if c != last_id]
                # Si solo hay uno y es el mismo que antes o el usuario pidió explícitamente "otro",
                # intentamos buscar otros ejercicios del mismo tema (sin filtrar dificultad)
                elif len(candidatos_unicos) == 1 and (candidatos_unicos[0] == last_id or pide_otro):
                    try:
                        otros = retriever._get_recommended_exercises(sess, tema_pred, dificultad=None)
                    except Exception:
                        otros = []
                    otros_ids = [ex.get("id") for ex in otros if ex.get("id")]
                    otros_ids = [eid for eid in otros_ids if eid != last_id]
                    if otros_ids:
                        candidatos_rotados = otros_ids

            if candidatos_rotados:
                ejercicio_seleccionado = candidatos_rotados[0]

                # Guardamos en StudentState para no repetir en la próxima
                sess.run(
                    """
                    MATCH (e:Estudiante {name:$name})-[:TIENE_ESTADO]->(st:StudentState)
                    MATCH (s:Slot {name:'ultimo_ejercicio_recomendado'})
                    MERGE (st)-[r:HAS_SLOT]->(s)
                    SET r.value = $eid,
                        r.updated_at = datetime()
                    """,
                    name=student_name,
                    eid=ejercicio_seleccionado,
                )

    # 3) Respuesta pedagógica usando contexto del grafo
    messages = [
        SystemMessage(
            content=(
                "Sos un tutor de Python para principiantes. "
                "Respondé en español, paso a paso, con ejemplos simples cuando sea útil. "
                "Tenés acceso a un grafo de conocimiento del dominio Python (TutorIA). "
                "Usá el contexto del grafo como guía para enfocarte en los conceptos relevantes. "
                "Si en la instrucción del sistema o en el contexto se menciona un ejercicio concreto "
                "(por ejemplo E_SumaDosNumeros), NO inventes ejercicios nuevos: recomendá ese ejercicio "
                "y explicá brevemente por qué es adecuado para practicar lo que pregunta el estudiante."
            )
        )
    ]
    
    # Agregar historial de conversación
    for q, r in conv_history:
        messages.append(HumanMessage(content=q))
        messages.append(SystemMessage(content=r))
    
    # Agregar contexto del grafo y pregunta actual
    if ejercicio_seleccionado:
        prompt_extra = (
            f"Para esta pregunta, el sistema ya eligió el ejercicio del catálogo: {ejercicio_seleccionado}.\n"
            "Recomendale específicamente ese ejercicio al estudiante (con su id) y explicá brevemente por qué "
            "es adecuado, usando el contexto del grafo y el estado del estudiante."
        )
    else:
        prompt_extra = (
            "Dale una explicación clara. Si es útil, incluye un ejemplo de código corto."
        )

    messages.append(
        HumanMessage(
            content=(
                f"{graph_context}\n\n"
                f"Pregunta del estudiante: {question_text}\n\n"
                f"{prompt_extra}"
            )
        )
    )

    print("🕒 Generando respuesta con el modelo...\n")

    full_text = ""
    for chunk in llm.stream(messages):
        text = chunk.content
        full_text += text
        print(text, end="", flush=True)

    print()

    # 4) Persistir turno y actualizar estado
    with driver.session() as sess:
        ensure_student_and_state(sess, student_name)

        # Registrar Question y Respuesta, enlazar Tema
        sess.run("""
            MERGE (e:Estudiante {name:$name})
            MERGE (t:Tema {codigo:$tema}) ON CREATE SET t.nombre = $tema
            WITH e, t
            CREATE (q:Question:Frame {
                name: 'Q_' + toString(timestamp()),
                texto: $qt,
                tema: $tema,
                creada_en: datetime()
            })
            MERGE (q)-[:CLASIFICADA_COMO]->(t)
            MERGE (e)-[:PREGUNTA]->(q)
            WITH e
            MERGE (tu:TutorIA)
            CREATE (r:Respuesta:Frame {
                name: 'R_' + toString(timestamp()),
                texto: $rt,
                creada_en: datetime()
            })
            MERGE (tu)-[:ENTREGA]->(r)
            MERGE (e)-[:RECIBE]->(r)
        """, name=student_name, qt=question_text, rt=full_text, tema=tema_pred)

        # Ajustar estado → el daemon detecta updated_at y recalcula difuso
        update_student_state(sess, student_name, tema_pred,
                             d_mae=d_mae, d_conf=d_conf, d_fru=d_fru)

    return full_text


# ──────────────────────────────────────────────
# 5) CLI con login simple
# ──────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TutorIA - LLM + Grafo Neo4j")
    parser.add_argument("--test", action="store_true", help="Modo test del retriever (muestra documentos y termina)")
    args = parser.parse_args()

    print("🎓 TutorIA LLM + Grafo de Conocimiento")
    print(f"(Neo4j en {URI}, modelo Ollama: llama3)\n")

    if not STUDENT_NAME:
        STUDENT_NAME = input("👤 Ingresá tu nombre de estudiante: ").strip() or "Estudiante_Demo"

    print(f"\n✅ Bienvenido/a {STUDENT_NAME}!")

    if args.test:
        q = input("🔎 Pregunta de prueba para el retriever: ").strip()
        retriever.set_student(STUDENT_NAME)
        # Para debug: si la pregunta menciona "funcion", forzamos el tema a "funciones"
        # para inspeccionar los ejercicios de ese tema.
        if "funcion" in q.lower() or "función" in q.lower():
            retriever.last_tema = "funciones"
        try:
            docs = retriever.invoke(q)
        except Exception as e:
            print(f"Error al invocar retriever: {e}")
            docs = []
        if not docs:
            print("(Fallback) Usando build_graph_context...")
            ctx, tema = build_graph_context(q, STUDENT_NAME)
            print("Tema:", tema)
            print("Contexto legacy:\n", ctx)
        else:
            print(f"\n📄 {len(docs)} documentos recuperados:")
            for i, d in enumerate(docs, 1):
                print(f"[{i}] tipo={d.metadata.get('type')} tema={retriever.last_tema}")
                print(d.page_content[:400] + ("..." if len(d.page_content) > 400 else ""))
                print("-")
        driver.close()
        sys.exit(0)

    print("Escribí tu pregunta (o 'salir' para terminar)\n")

    try:
        while True:
            q = input("👨‍🎓 Pregunta: ").strip()
            if not q:
                continue
            if q.lower() in {"salir", "exit", "quit"}:
                break
            print("\n🔍 Buscando contexto (retriever + fallback si falla)...")
            answer = answer_with_llm(q, STUDENT_NAME)
            print("\n" + "-" * 60 + "\n")
    finally:
        driver.close()

