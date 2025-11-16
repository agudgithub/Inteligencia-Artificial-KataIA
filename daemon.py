import os, time, math, json, signal, sys
from neo4j import GraphDatabase, basic_auth
from clasificador_temas import predecir_tema

# ──────────────────────────────────────────────
# 1) Leer solo variables de entorno del contenedor
# ──────────────────────────────────────────────
URI  = os.environ["NEO4J_URI"]
USER = os.environ["NEO4J_USER"]
PWD  = os.environ["NEO4J_PASSWORD"]

# ──────────────────────────────────────────────
# 2) Esperar hasta que Neo4j esté disponible
# ──────────────────────────────────────────────
def wait_for_neo4j(uri, user, password, total_timeout=120, step=2):
    deadline = time.time() + total_timeout
    last_err = None
    print(f"🔌 Esperando Neo4j en {uri} como {user} (timeout {total_timeout}s)...", flush=True)
    intentos = 0
    while time.time() < deadline:
        intentos += 1
        try:
            driver = GraphDatabase.driver(uri, auth=basic_auth(user, password))
            with driver.session() as s:
                s.run("RETURN 1").consume()
            print(f"✅ Conectado a Neo4j en {uri} como {user}", flush=True)
            return driver
        except Exception as e:
            last_err = e
            print(f"⏳ Intento {intentos}: aún no disponible ({e}); reintento en {step}s", flush=True)
            time.sleep(step)
    raise RuntimeError(f"Neo4j no respondió a tiempo: {last_err}")


# ──────────────────────────────────────────────
# 3) Conexión
# ──────────────────────────────────────────────
driver = wait_for_neo4j(URI, USER, PWD)
print(f"✅ Conectado a Neo4j en {URI} como {USER}")

# ─────────────────────────────────────────────────────────
# 2) Utilidades difusas
# ─────────────────────────────────────────────────────────
def round4(x: float) -> float:
    """Redondea un número flotante a 4 decimales."""
    return float(f"{x:.4f}")

def clamp01(x: float) -> float:
    """Recorta a [0,1] por seguridad."""
    return max(0.0, min(1.0, x))

def gaussian(x: float, a: float, b: float) -> float:
    """Función Gaussiana con centro a y desvío b."""
    if b == 0:
        return 0.0
    return math.exp(-((x - a) ** 2) / (2 * (b ** 2)))

def fuzzy_entropy(mus: dict) -> float:
    """
    Entropía difusa normalizada en [0,1].
    0 → estado definido; 1 → máxima incertidumbre.
    """
    terms = [m for m in (mus["mu_baja"], mus["mu_media"], mus["mu_alta"]) if m > 0]
    if not terms:
        return 0.0
    return -sum(m * math.log(m) for m in terms) / math.log(3)

def defuzz_centroid(mus: dict) -> float:
    """Centroide discreto con puntos {baja:0, media:0.5, alta:1}."""
    num = 0.0 * mus["mu_baja"] + 0.5 * mus["mu_media"] + 1.0 * mus["mu_alta"]
    den = mus["mu_baja"] + mus["mu_media"] + mus["mu_alta"]
    return (num / den) if den > 0 else 0.0

# ─────────────────────────────────────────────────────────
# 3) Acceso a parámetros/targets en Neo4j
# ─────────────────────────────────────────────────────────
def load_params(tx, slot_name: str):
    """
    Lee de Slot los parámetros gaussianos esperados:
    - s.funcion_pertenencia = 'gaussiana'
    - (a_*, b_*) para baja/media/alta
    """
    q = """
    MATCH (s:Slot {name:$slot})
    RETURN s.funcion_pertenencia AS f,
           s.a_baja AS a_baja,  s.b_baja AS b_baja,
           s.a_media AS a_media, s.b_media AS b_media,
           s.a_alta AS a_alta,   s.b_alta AS b_alta
    """
    rec = tx.run(q, slot=slot_name).single()
    return dict(rec) if rec else None

def fetch_targets(tx):
    """
    Trae relaciones HAS_SLOT con value y que requieren recalcular:
    - nunca se calculó (fuzzy_updated_at IS NULL), o
    - updated_at > fuzzy_updated_at (hubo cambio de value).
    """
    q = """
    MATCH (f:Frame)-[r:HAS_SLOT]->(s:Slot)
    WHERE s.name IN ['confianza','frustracion','maestria']
      AND r.value IS NOT NULL
      AND (
        r.fuzzy_updated_at IS NULL
        OR (r.updated_at IS NOT NULL AND r.updated_at > r.fuzzy_updated_at)
      )
    RETURN elementId(r) AS rid, s.name AS slot, r.value AS val
    """
    return [dict(rec) for rec in tx.run(q)]

def find_pending_slot_relations(tx):
    """Alias para mantener compatibilidad con el bucle propuesto por el usuario."""
    return fetch_targets(tx)

def update_memberships(tx, rid: str, mus: dict, label: str, score: float, H: float, z: float):
    """
    Actualiza la relación HAS_SLOT con valores difusos + tracking:
    - prev_label: etiqueta anterior
    - last_action_at: solo si cambió fuzzy_label
    """
    q = """
    MATCH ()-[r]->()
    WHERE elementId(r) = $rid
    WITH r, r.fuzzy_label AS old
    SET r.prev_label = old,
        r.mu_baja  = $mu_baja,
        r.mu_media = $mu_media,
        r.mu_alta  = $mu_alta,
        r.fuzzy_label = $label,
        r.fuzzy_score = $score,
        r.fuzzy_entropy = $entropy,
        r.fuzzy_defuzz = $defuzz,
        r.fuzzy_updated_at = datetime()
    WITH r, old
    FOREACH (_ IN CASE WHEN old IS NULL OR old <> r.fuzzy_label THEN [1] ELSE [] END |
      SET r.last_action_at = datetime()
    )
    """
    tx.run(
        q,
        rid=rid,
        mu_baja=round4(mus["mu_baja"]),
        mu_media=round4(mus["mu_media"]),
        mu_alta=round4(mus["mu_alta"]),
        label=label,
        score=round4(score),
        entropy=round4(H),
        defuzz=round4(z),
    )

# ──────────────────────────────────────────────
# X) Clasificación de temas con el modelo NLP
# ──────────────────────────────────────────────
def find_unclassified_questions(tx, limit=20):
    """
    Busca preguntas que todavía no tienen 'tema' asignado.
    Ajustá el label y el nombre de la propiedad a tu modelo de grafo real.
    """
    q = """
    MATCH (q:Question)
    WHERE q.texto IS NOT NULL
      AND (q.tema IS NULL OR q.tema = '')
    RETURN elementId(q) AS qid, q.texto AS texto
    LIMIT $limit
    """
    return [dict(rec) for rec in tx.run(q, limit=limit)]


def set_question_topic(tx, qid, tema):
    """
    Graba el tema detectado en la pregunta.
    """
    q = """
    MATCH (q) WHERE elementId(q) = $qid
    SET q.tema = $tema,
        q.tema_updated_at = datetime()
    """
    tx.run(q, qid=qid, tema=tema)

# ─────────────────────────────────────────────────────────
# 4) Fuzzificación de una relación HAS_SLOT
# ─────────────────────────────────────────────────────────
def parse_value_to_float(raw) -> float:
    """
    Convierte r.value a un escalar en [0,1]:
    - string/num simple → float
    - JSON objeto (p.ej. {"Funcion":0.4,"Variable":0.6}) → promedio
    - JSON lista → promedio
    - fallback → 0.0
    """
    # Ej: "0.5" o 0.5
    try:
        x = float(raw)
        return clamp01(x)
    except Exception:
        pass

    # Ej: '{"publicos":"pass","privados":"pass"}' → ignora (no es [0,1])
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            vals = []
            for v in data.values():
                try:
                    vals.append(float(v))
                except Exception:
                    # Ignorar no numéricos
                    pass
            if vals:
                return clamp01(sum(vals) / len(vals))
        elif isinstance(data, list):
            vals = []
            for v in data:
                try:
                    vals.append(float(v))
                except Exception:
                    pass
            if vals:
                return clamp01(sum(vals) / len(vals))
    except Exception:
        pass

    return 0.0

def fuzzify_relation(rel: dict, params: dict) -> dict:
    """
    Toma (rid, slot, val) y parámetros gaussianos → devuelve μ_*.
    params requiere: f='gaussiana' y (a_*, b_*) para baja/media/alta.
    """
    x = parse_value_to_float(rel["val"])
    mus = {
        "mu_baja":  gaussian(x, float(params["a_baja"]),  float(params["b_baja"]  or 0)),
        "mu_media": gaussian(x, float(params["a_media"]), float(params["b_media"] or 0)),
        "mu_alta":  gaussian(x, float(params["a_alta"]),  float(params["b_alta"]  or 0)),
    }
    # Seguridad: si alguna b_* = 0, gaussian devuelve 0; está bien.
    return mus

# ─────────────────────────────────────────────────────────
# 5) Daemon principal
# ─────────────────────────────────────────────────────────
def loop(poll_seconds: int = 5):
    """
    Bucle principal del daemon difuso + clasificador de temas.
    - Recalcula relaciones HAS_SLOT de confianza, frustracion y maestria.
    - Clasifica preguntas sin tema usando `predecir_tema`.
    - Recarga parámetros gaussianos en cada iteración.
    """
    from collections import OrderedDict

    print("🟢 Daemon difuso + clasificador de temas iniciado", flush=True)
    slots = ['confianza', 'frustracion', 'maestria']

    while True:
        try:
            with driver.session() as sess:
                # Recargar parámetros cada ciclo (por si fueron modificados en Neo4j)
                slot_params = {s: sess.execute_read(load_params, s) for s in slots}

                # 1) Lógica difusa
                targets = sess.execute_read(find_pending_slot_relations)
                print(f"🔎 Relaciones pendientes: {len(targets)}")
                for r in targets:
                    p = slot_params.get(r["slot"])
                    if not p or (p.get("f") or "").lower() != "gaussiana":
                        print(f"⏭️  Salteado {r['slot']} (sin params gaussiana)")
                        continue

                    mus = fuzzify_relation(r, p)

                    label_order = OrderedDict([
                        ("baja",  "mu_baja"),
                        ("media", "mu_media"),
                        ("alta",  "mu_alta"),
                    ])
                    label = max(label_order, key=lambda k: mus[label_order[k]])
                    score = mus[label_order[label]]

                    H = fuzzy_entropy(mus)
                    z = defuzz_centroid(mus)

                    sess.execute_write(update_memberships, r["rid"], mus, label, score, H, z)
                    reactive_rules(sess, r["rid"], r["slot"], mus, label, score, H, z)
                    print(
                        f"✅ {r['slot']}: { {k: round4(v) for k,v in mus.items()} } "
                        f"label={label} score={round4(score)} H={round4(H)} z={round4(z)}"
                    )

                # 2) Clasificación de dudas pendientes (NLP)
                preguntas = sess.execute_read(find_unclassified_questions, limit=50)
                if preguntas:
                    print(f"🧠 Preguntas sin tema: {len(preguntas)}")
                for q in preguntas:
                    tema = predecir_tema(q["texto"])  # función del modelo NLP
                    print(f"   · '{q['texto']}' → {tema}")
                    sess.execute_write(set_question_topic, q["qid"], tema)

            time.sleep(poll_seconds)

        except KeyboardInterrupt:
            print("🛑 Detenido por el usuario")
            break
        except Exception as e:
            print(f"⚠️ Error en loop: {e}", flush=True)
            time.sleep(poll_seconds)

# ----------------------------------------------------------
# 🔥 Reglas reactivas (acciones sobre el grafo)
# - Histeresis: solo dispara al cambiar de estado dominante
# - Cooldown: evita disparos repetidos en ventanas cortas
# ----------------------------------------------------------

COOLDOWN_MINUTES = 3  # ventana mínima entre acciones iguales en la misma rel/slot

def _now(sess):
    return sess.run("RETURN datetime() AS now").single()["now"]

def _minutes_since(sess, dt):
    if not dt:
        return 1e9
    rec = sess.run("RETURN duration.between($dt, datetime()).minutes AS mins",
                   dt=dt).single()
    return rec["mins"]

def _read_prev_state(sess, rid):
    q = """
    MATCH ()-[r]->() WHERE elementId(r) = $rid
    RETURN r.fuzzy_label AS prev_label,
           r.last_action_label AS last_action_label,
           r.last_action_at    AS last_action_at
    """
    rec = sess.run(q, rid=rid).single()
    return (rec["prev_label"], rec["last_action_label"], rec["last_action_at"]) if rec else (None, None, None)

def _mark_action(sess, rid, action_label):
    sess.run("""
        MATCH ()-[r]->() WHERE elementId(r) = $rid
        SET r.last_action_label = $lbl,
            r.last_action_at    = datetime()
    """, rid=rid, lbl=action_label)

def _resolve_student_state(sess, rid: str):
    """
    Resuelve el StudentState dueño de la relación HAS_SLOT identificada por rid.
    Retorna el elementId del StudentState o None si no existe.
    """
    q = """
    MATCH (st:StudentState)-[r:HAS_SLOT]->(:Slot)
    WHERE elementId(r) = $rid
    RETURN elementId(st) AS st_id
    """
    rec = sess.run(q, rid=rid).single()
    return rec["st_id"] if rec else None

def _link_intervention(sess, st_id: str, motivo: str, tipo: str = "Afectiva", detalle: dict = None):
    """
    Crea/actualiza un nodo de intervención y lo vincula al StudentState especificado.
    """
    if not st_id:
        print(f"⚠️ No se pudo vincular intervención '{motivo}': StudentState no encontrado.")
        return
    detalle = detalle or {}
    q = """
    MATCH (st) WHERE elementId(st) = $st_id
    MERGE (i:Intervencion {motivo:$motivo})
      ON CREATE SET i.tipo=$tipo, i.created_at=datetime()
      ON MATCH  SET i.last_at=datetime()
    MERGE (st)-[rg:REGISTRA]->(i)
      ON CREATE SET rg.at = datetime()
      ON MATCH  SET rg.at = datetime()
    RETURN i
    """
    sess.run(q, st_id=st_id, motivo=motivo, tipo=tipo)

def reactive_rules(sess, rid:str, slot:str, mus:dict, label:str, score:float, H:float, z:float):
    """
    Dispara acciones cuando cambia el estado difuso de una relación HAS_SLOT.
    Reglas simples:
      - frustracion alta (score>=0.7, H<=0.5): crear intervención 'frustracion_alta'
      - confianza baja sostenida (score>=0.6, H<=0.6): crear intervención 'refuerzo_confianza'
      - maestria alta y confianza media/alta: marcar 'sugerir_siguiente_ejercicio'
    Usa cooldown y sólo dispara cuando el label dominante cambia respecto del anterior.
    Todas las acciones están scopeadas al StudentState dueño del rid.
    """
    prev_label, last_action_label, last_action_at = _read_prev_state(sess, rid)
    label_changed = (prev_label != label)

    # Condición de cooldown por última acción (global para la misma relación)
    mins = _minutes_since(sess, last_action_at)

    # Resolver el StudentState dueño de esta relación
    st_id = _resolve_student_state(sess, rid)
    if not st_id:
        print(f"⚠️ No se encontró StudentState para rid={rid}; omitiendo reglas reactivas.")
        return

    # -------- Regla 1: Frustración alta -> Pausa + microéxito --------
    if slot == "frustracion" and label == "alta" and score >= 0.70 and H <= 0.50:
        if (label_changed or last_action_label != "frustracion_alta") and mins >= COOLDOWN_MINUTES:
            _link_intervention(sess, st_id,
                               motivo="frustracion_alta",
                               tipo="Afectiva",
                               detalle={"score": score, "H": H})
            _mark_action(sess, rid, "frustracion_alta")
            print("⚠️ Acción: Pausa + microéxito por frustración alta.")

    # -------- Regla 2: Confianza baja -> Refuerzo de confianza --------
    if slot == "confianza" and label == "baja" and score >= 0.60 and H <= 0.60:
        if (label_changed or last_action_label != "refuerzo_confianza") and mins >= COOLDOWN_MINUTES:
            _link_intervention(sess, st_id,
                               motivo="refuerzo_confianza",
                               tipo="Afectiva",
                               detalle={"score": score, "H": H})
            _mark_action(sess, rid, "refuerzo_confianza")
            print("💬 Acción: Mensaje de refuerzo de confianza.")

    # -------- Regla 3: Maestría alta + confianza no-baja -> Sugerir siguiente --------
    if slot == "maestria" and label == "alta" and H <= 0.50 and z >= 0.75:
        # Leer confianza del MISMO StudentState
        rec = sess.run("""
            MATCH (st)-[rc:HAS_SLOT]->(:Slot {name:'confianza'})
            WHERE elementId(st) = $st_id
            RETURN coalesce(rc.fuzzy_defuzz, toFloat(rc.value)) AS conf
        """, st_id=st_id).single()
        conf = float(rec["conf"]) if rec and rec["conf"] is not None else 0.0
        
        if conf >= 0.4:  # no-baja
            if (label_changed or last_action_label != "sugerir_siguiente") and mins >= COOLDOWN_MINUTES:
                # Crear señal vinculada al mismo StudentState
                sess.run("""
                    MATCH (st) WHERE elementId(st) = $st_id
                    MERGE (s:Signal {kind:'sugerir_siguiente'})
                      ON CREATE SET s.created_at = datetime()
                      ON MATCH  SET s.last_at    = datetime()
                    MERGE (st)-[r:REGISTRA]->(s)
                      ON CREATE SET r.at = datetime()
                      ON MATCH  SET r.at = datetime()
                """, st_id=st_id)
                _mark_action(sess, rid, "sugerir_siguiente")
                print("🧭 Acción: Sugerir siguiente ejercicio (alta maestría + conf no-baja).")

# ─────────────────────────────────────────────────────────
# 6) Señales / Main
# ─────────────────────────────────────────────────────────
def handle_sigint(sig, frame):
    print("\n🧹 Cerrando conexión…")
    try:
        driver.close()
    finally:
        sys.exit(0)

signal.signal(signal.SIGINT, handle_sigint)

if __name__ == "__main__":
    try:
        #check_connection()
        # (Opcional) Semilla de parámetros si faltaran:
        # with driver.session() as s:
        #     s.run("""
        #     MATCH (s:Slot) WHERE s.name IN ['confianza','frustracion','maestria']
        #     SET s.funcion_pertenencia = coalesce(s.funcion_pertenencia, 'gaussiana'),
        #         s.a_baja = coalesce(s.a_baja, 0.0),   s.b_baja = coalesce(s.b_baja, 0.2),
        #         s.a_media = coalesce(s.a_media, 0.5), s.b_media = coalesce(s.b_media, 0.15),
        #         s.a_alta = coalesce(s.a_alta, 1.0),   s.b_alta = coalesce(s.b_alta, 0.2)
        #     """)
        loop(poll_seconds=5)
    except Exception as e:
        print(f"❌ Error fatal: {e}")
        try:
            driver.close()
        finally:
            sys.exit(1)
