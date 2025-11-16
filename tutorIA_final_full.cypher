// ======================================================================
// TutorIA — Red de Frames (carga completa) vFINAL (todos los bloques)
// - Bloques 00 → 20, cada uno termina con ';'
// - HAS_SLOT con propiedades en la relación (value, updated_at)
// - Opción B: parámetros gaussianos guardados en los Slot (confianza, frustracion, maestria)
// - Agregado: índices en relaciones HAS_SLOT
// Neo4j 5.x
// ======================================================================

/////////////////////////////////////////////////////////////////////////
// 00) RESET (ejecutar con cuidado: borra TODO)
/////////////////////////////////////////////////////////////////////////
MATCH (n) DETACH DELETE n;
DROP CONSTRAINT frame_name IF EXISTS;
DROP CONSTRAINT slot_name IF EXISTS;
DROP CONSTRAINT facet_name IF EXISTS;
;

/////////////////////////////////////////////////////////////////////////
// 01) CONSTRAINTS
/////////////////////////////////////////////////////////////////////////
CREATE CONSTRAINT frame_name IF NOT EXISTS
FOR (f:Frame) REQUIRE f.name IS UNIQUE;

CREATE CONSTRAINT slot_name IF NOT EXISTS
FOR (s:Slot) REQUIRE s.name IS UNIQUE;

CREATE CONSTRAINT facet_name IF NOT EXISTS
FOR (fa:Facet) REQUIRE fa.name IS UNIQUE;
;

/////////////////////////////////////////////////////////////////////////
// 01b) ÍNDICES ÚTILES EN RELACIONES HAS_SLOT (una sola vez)
/////////////////////////////////////////////////////////////////////////
// Aceleran lecturas/escrituras del daemon y consultas por estado difuso
CREATE INDEX IF NOT EXISTS FOR ()-[r:HAS_SLOT]-() ON (r.fuzzy_updated_at);
CREATE INDEX IF NOT EXISTS FOR ()-[r:HAS_SLOT]-() ON (r.prev_label);
CREATE INDEX IF NOT EXISTS FOR ()-[r:HAS_SLOT]-() ON (r.last_action_at);
CREATE INDEX IF NOT EXISTS FOR ()-[r:HAS_SLOT]-() ON (r.fuzzy_label);
;

/////////////////////////////////////////////////////////////////////////
// 02) SLOTS Y FACETS
/////////////////////////////////////////////////////////////////////////
UNWIND [
  'enunciado','tests_publicos','tests_privados','dificultad',
  'codigo','resultado_tests','tiempo','n_hints','errores_detectados','timestamp',
  'texto','nivel',
  'patron_codigo','descripcion','correccion',
  'taxonomia_bloom','criterio_exito','peso',
  'maestria','confianza','frustracion','estilo','ritmo',
  'contenido_uri','duracion_estimada',
  'tipo_intervencion','disparador',
  'ultimo_ejercicio_recomendado'
] AS slotName
MERGE (:Slot {name: slotName});
;

UNWIND [
  ['requerido','boolean'],
  ['tipo','string|int|float|json|list|datetime'],
  ['cardinalidad','1..*'],
  ['rango','[0,1] (difuso)'],
  ['default','valor por defecto']
] AS facet
MERGE (:Facet {name: facet[0], rule: facet[1]});
;

/////////////////////////////////////////////////////////////////////////
// 03) FRAMES PRINCIPALES
/////////////////////////////////////////////////////////////////////////
UNWIND [
  'Concept',
  'TutorIA','Estudiante_Demo','Runner_Python','BR_default',
  'LO_Funciones_Basicas','LO_Estructuras',
  'Tipo','Variable','Funcion','Lista','Bucle',
  'Eval_UnitTest','PT_Publico','PT_Privado',
  'Concatenar_str_int','OffByOne_en_bucle',
  'Hint_str_int_n1','Hint_off_by_one_n1',
  'Estado_Estudiante_Ejemplo','Maestria_Funcion',
  'Afecto_F_Alta','Confianza_Baja',
  'MC_funciones_basicas','CS_suma_a_b','IA_pausa_microexito',
  'E_SumaDosNumeros','E_MaximoLista','Attempt_e1_v1','FB_e1'
] AS fname
MERGE (:Frame {name: fname});
;

/////////////////////////////////////////////////////////////////////////
// 04) ETIQUETAS TIPADAS
/////////////////////////////////////////////////////////////////////////
MATCH (n:Frame {name:'TutorIA'})                    SET n:TutorIA;
MATCH (n:Frame {name:'Estudiante_Demo'})            SET n:Estudiante;
MATCH (n:Frame {name:'Runner_Python'})              SET n:Runner;
MATCH (n:Frame {name:'BR_default'})                 SET n:BancoRecursos;

MATCH (n:Frame {name:'LO_Funciones_Basicas'})       SET n:LearningObjective;
MATCH (n:Frame {name:'LO_Estructuras'})             SET n:LearningObjective;

MATCH (n:Frame {name:'Tipo'})                       SET n:PythonConcept;
MATCH (n:Frame {name:'Variable'})                   SET n:PythonConcept;
MATCH (n:Frame {name:'Funcion'})                    SET n:PythonConcept;
MATCH (n:Frame {name:'Lista'})                      SET n:PythonConcept;
MATCH (n:Frame {name:'Bucle'})                      SET n:PythonConcept;

MATCH (n:Frame {name:'Eval_UnitTest'})              SET n:Evaluacion;
MATCH (n:Frame {name:'PT_Publico'})                 SET n:PoliticaTest;
MATCH (n:Frame {name:'PT_Privado'})                 SET n:PoliticaTest;

MATCH (n:Frame {name:'Concatenar_str_int'})         SET n:Misconception;
MATCH (n:Frame {name:'OffByOne_en_bucle'})          SET n:Misconception;

MATCH (n:Frame {name:'Hint_str_int_n1'})            SET n:Hint;
MATCH (n:Frame {name:'Hint_off_by_one_n1'})         SET n:Hint;

MATCH (n:Frame {name:'Estado_Estudiante_Ejemplo'})  SET n:StudentState;
MATCH (n:Frame {name:'Maestria_Funcion'})           SET n:Maestria;
MATCH (n:Frame {name:'Afecto_F_Alta'})              SET n:Afecto;
MATCH (n:Frame {name:'Confianza_Baja'})             SET n:Confianza;

MATCH (n:Frame {name:'MC_funciones_basicas'})       SET n:MicroContenido;
MATCH (n:Frame {name:'CS_suma_a_b'})                SET n:Consigna;
MATCH (n:Frame {name:'IA_pausa_microexito'})        SET n:IntervencionAfectiva;

MATCH (n:Frame {name:'E_SumaDosNumeros'})           SET n:Exercise;
MATCH (n:Frame {name:'E_MaximoLista'})              SET n:Exercise;
MATCH (n:Frame {name:'Attempt_e1_v1'})              SET n:Attempt;
MATCH (n:Frame {name:'FB_e1'})                      SET n:FeedbackPlan;
;

/////////////////////////////////////////////////////////////////////////
// 05) HERENCIA (PythonConcept -> Concept)
/////////////////////////////////////////////////////////////////////////
MATCH (concept:Frame {name:'Concept'})
WITH concept, ['Tipo','Variable','Funcion','Lista','Bucle'] AS subconcepts
UNWIND subconcepts AS sub
MATCH (f:Frame {name: sub})
MERGE (f)-[:IS_A]->(concept);
;

/////////////////////////////////////////////////////////////////////////
// 06) RELACIONES PEDAGÓGICAS
/////////////////////////////////////////////////////////////////////////
MATCH (t:TutorIA),
      (lo1:LearningObjective {name:'LO_Funciones_Basicas'}),
      (lo2:LearningObjective {name:'LO_Estructuras'}),
      (pcFn:PythonConcept {name:'Funcion'}),
      (pcTipo:PythonConcept {name:'Tipo'}),
      (pcList:PythonConcept {name:'Lista'}),
      (pcFor:PythonConcept {name:'Bucle'}),
      (e1:Exercise {name:'E_SumaDosNumeros'}),
      (e2:Exercise {name:'E_MaximoLista'}),
      (u:Estudiante),
      (a1:Attempt {name:'Attempt_e1_v1'}),
      (r:Runner),
      (ev:Evaluacion),
      (ptPub:PoliticaTest {name:'PT_Publico'}),
      (ptPriv:PoliticaTest {name:'PT_Privado'}),
      (mis1:Misconception {name:'Concatenar_str_int'}),
      (mis2:Misconception {name:'OffByOne_en_bucle'}),
      (h1:Hint {name:'Hint_str_int_n1'}),
      (h2:Hint {name:'Hint_off_by_one_n1'}),
      (fp:FeedbackPlan),
      (br:BancoRecursos),
      (st:StudentState),
      (mz:Maestria),
      (af:Afecto),
      (cf:Confianza),
      (mc:MicroContenido),
      (cs:Consigna),
      (ia:IntervencionAfectiva)
MERGE (t)-[:SELECCIONA_SEGUN]->(lo1)
MERGE (t)-[:SELECCIONA_SEGUN]->(lo2)
MERGE (lo1)-[:DESCOMPONE_EN]->(pcFn)
MERGE (lo1)-[:DESCOMPONE_EN]->(pcTipo)
MERGE (lo2)-[:DESCOMPONE_EN]->(pcList)
MERGE (lo2)-[:DESCOMPONE_EN]->(pcFor)
MERGE (t)-[:PROPONE]->(e1)
MERGE (t)-[:PROPONE]->(e2)
MERGE (e1)-[:APUNTA_A]->(pcFn)
MERGE (e1)-[:APUNTA_A]->(pcTipo)
MERGE (e2)-[:APUNTA_A]->(pcList)
MERGE (e2)-[:APUNTA_A]->(pcFor)
MERGE (t)-[:ENTREGA]->(mc)
MERGE (t)-[:ENTREGA]->(cs)
MERGE (u)-[:REALIZA]->(a1)
MERGE (a1)-[:USA]->(e1)
MERGE (r)-[:EJECUTA]->(a1)
MERGE (ev)-[:EVALUA]->(a1)
MERGE (ev)-[:USA]->(ptPub)
MERGE (ev)-[:USA]->(ptPriv)
MERGE (ev)-[:DETECTA]->(mis1)
MERGE (mis1)-[:SE_CORRIGE_CON]->(h1)
MERGE (mis2)-[:SE_CORRIGE_CON]->(h2)
MERGE (t)-[:OFRECE]->(h1)
MERGE (t)-[:OFRECE]->(h2)
MERGE (t)-[:CONSTRUYE]->(fp)
MERGE (fp)-[:UTILIZA]->(br)
MERGE (a1)-[:EVIDENCIA]->(mz)
MERGE (a1)-[:GENERA]->(af)
MERGE (a1)-[:GENERA]->(cf)
MERGE (t)-[:ACTUALIZA]->(st)
MERGE (st)-[:ESTIMA_EN]->(mz)
MERGE (st)-[:REGISTRA]->(af)
MERGE (st)-[:REGISTRA]->(cf)
MERGE (t)-[:APLICA]->(ia);
;

/////////////////////////////////////////////////////////////////////////
// 07) HAS_SLOT — E1 (enunciado/tests/dificultad)
/////////////////////////////////////////////////////////////////////////
MATCH (e1:Exercise {name:'E_SumaDosNumeros'}),
      (s_en:Slot {name:'enunciado'}),
      (s_pub:Slot {name:'tests_publicos'}),
      (s_priv:Slot {name:'tests_privados'}),
      (s_diff:Slot {name:'dificultad'})
MERGE (e1)-[e1_en:HAS_SLOT]->(s_en)   ON CREATE SET e1_en.value='Implementa una función suma(a,b) que retorne a+b', e1_en.updated_at=datetime()
MERGE (e1)-[e1_pb:HAS_SLOT]->(s_pub)  ON CREATE SET e1_pb.value='[{"in":[2,3],"out":5},{"in":[-1,1],"out":0}]', e1_pb.updated_at=datetime()
MERGE (e1)-[e1_pr:HAS_SLOT]->(s_priv) ON CREATE SET e1_pr.value='[{"in":[-1000,999],"out":-1},{"in":[0,0],"out":0}]', e1_pr.updated_at=datetime()
MERGE (e1)-[e1_df:HAS_SLOT]->(s_diff) ON CREATE SET e1_df.value='facil', e1_df.updated_at=datetime();
;

/////////////////////////////////////////////////////////////////////////
// 08) HAS_SLOT — E2 (enunciado/tests/dificultad)
/////////////////////////////////////////////////////////////////////////
MATCH (e2:Exercise {name:'E_MaximoLista'}),
      (s_en:Slot {name:'enunciado'}),
      (s_pub:Slot {name:'tests_publicos'}),
      (s_priv:Slot {name:'tests_privados'}),
      (s_diff:Slot {name:'dificultad'})
MERGE (e2)-[e2_en:HAS_SLOT]->(s_en)   ON CREATE SET e2_en.value='Implementa max_lista(xs) que retorne el máximo sin usar max()', e2_en.updated_at=datetime()
MERGE (e2)-[e2_pb:HAS_SLOT]->(s_pub)  ON CREATE SET e2_pb.value='[{"in":[[1,2,3]],"out":3},{"in":[[-5,-2]],"out":-2}]', e2_pb.updated_at=datetime()
MERGE (e2)-[e2_pr:HAS_SLOT]->(s_priv) ON CREATE SET e2_pr.value='[{"in":[[10]],"out":10},{"in":[[0,0,0]],"out":0}]', e2_pr.updated_at=datetime()
MERGE (e2)-[e2_df:HAS_SLOT]->(s_diff) ON CREATE SET e2_df.value='facil', e2_df.updated_at=datetime();
;

/////////////////////////////////////////////////////////////////////////
// 09) HAS_SLOT — Attempt del estudiante
/////////////////////////////////////////////////////////////////////////
MATCH (a1:Attempt {name:'Attempt_e1_v1'}),
      (s_cod:Slot {name:'codigo'}),
      (s_res:Slot {name:'resultado_tests'}),
      (s_tim:Slot {name:'tiempo'}),
      (s_nh:Slot {name:'n_hints'}),
      (s_err:Slot {name:'errores_detectados'}),
      (s_ts:Slot {name:'timestamp'})
MERGE (a1)-[a1_cd:HAS_SLOT]->(s_cod) ON CREATE SET a1_cd.value='def suma(a,b): return a+b', a1_cd.updated_at=datetime()
MERGE (a1)-[a1_rs:HAS_SLOT]->(s_res) ON CREATE SET a1_rs.value='{"publicos":"pass","privados":"pass"}', a1_rs.updated_at=datetime()
MERGE (a1)-[a1_tm:HAS_SLOT]->(s_tim) ON CREATE SET a1_tm.value='12.3', a1_tm.updated_at=datetime()
MERGE (a1)-[a1_nh:HAS_SLOT]->(s_nh)  ON CREATE SET a1_nh.value='1', a1_nh.updated_at=datetime()
MERGE (a1)-[a1_er:HAS_SLOT]->(s_err) ON CREATE SET a1_er.value='[]', a1_er.updated_at=datetime()
MERGE (a1)-[a1_ts:HAS_SLOT]->(s_ts)  ON CREATE SET a1_ts.value=toString(datetime()), a1_ts.updated_at=datetime();
;

/////////////////////////////////////////////////////////////////////////
// 10) HAS_SLOT — Hints
/////////////////////////////////////////////////////////////////////////
MATCH (h1:Hint {name:'Hint_str_int_n1'}),
      (h2:Hint {name:'Hint_off_by_one_n1'}),
      (s_txt:Slot {name:'texto'}),
      (s_lvl:Slot {name:'nivel'})
MERGE (h1)-[h1_tx:HAS_SLOT]->(s_txt) ON CREATE SET h1_tx.value='Convertí números a string antes de concatenar', h1_tx.updated_at=datetime()
MERGE (h1)-[h1_lv:HAS_SLOT]->(s_lvl) ON CREATE SET h1_lv.value='1', h1_lv.updated_at=datetime()
MERGE (h2)-[h2_tx:HAS_SLOT]->(s_txt) ON CREATE SET h2_tx.value='Recordá: range(start, stop) excluye stop', h2_tx.updated_at=datetime()
MERGE (h2)-[h2_lv:HAS_SLOT]->(s_lvl) ON CREATE SET h2_lv.value='1', h2_lv.updated_at=datetime();
;

/////////////////////////////////////////////////////////////////////////
// 11) HAS_SLOT — Misconceptions
/////////////////////////////////////////////////////////////////////////
MATCH (m1:Misconception {name:'Concatenar_str_int'}),
      (m2:Misconception {name:'OffByOne_en_bucle'}),
      (s_pat:Slot {name:'patron_codigo'}),
      (s_desc:Slot {name:'descripcion'}),
      (s_corr:Slot {name:'correccion'})
MERGE (m1)-[m1_pt:HAS_SLOT]->(s_pat)  ON CREATE SET m1_pt.value='TypeError: can only concatenate str (not "int")', m1_pt.updated_at=datetime()
MERGE (m1)-[m1_ds:HAS_SLOT]->(s_desc) ON CREATE SET m1_ds.value='Mezcla de tipos sin conversión explícita', m1_ds.updated_at=datetime()
MERGE (m1)-[m1_cr:HAS_SLOT]->(s_corr) ON CREATE SET m1_cr.value='Usar str() o f-strings', m1_cr.updated_at=datetime()
MERGE (m2)-[m2_pt:HAS_SLOT]->(s_pat)  ON CREATE SET m2_pt.value='Off-by-one por rango mal definido', m2_pt.updated_at=datetime()
MERGE (m2)-[m2_ds:HAS_SLOT]->(s_desc) ON CREATE SET m2_ds.value='stop excluido en range()', m2_ds.updated_at=datetime()
MERGE (m2)-[m2_cr:HAS_SLOT]->(s_corr) ON CREATE SET m2_cr.value='Verificar inclusive/exclusive con casos pequeños', m2_cr.updated_at=datetime();
;

/////////////////////////////////////////////////////////////////////////
// 12) HAS_SLOT — Learning Objectives
/////////////////////////////////////////////////////////////////////////
MATCH (lo1:LearningObjective {name:'LO_Funciones_Basicas'}),
      (lo2:LearningObjective {name:'LO_Estructuras'}),
      (s_bloom:Slot {name:'taxonomia_bloom'}),
      (s_crit:Slot  {name:'criterio_exito'}),
      (s_peso:Slot  {name:'peso'})
MERGE (lo1)-[l1_bl:HAS_SLOT]->(s_bloom) ON CREATE SET l1_bl.value='Aplicar', l1_bl.updated_at=datetime()
MERGE (lo1)-[l1_cr:HAS_SLOT]->(s_crit)  ON CREATE SET l1_cr.value='Pasa tests públicos y privados', l1_cr.updated_at=datetime()
MERGE (lo1)-[l1_ps:HAS_SLOT]->(s_peso)  ON CREATE SET l1_ps.value='1.0', l1_ps.updated_at=datetime()
MERGE (lo2)-[l2_bl:HAS_SLOT]->(s_bloom) ON CREATE SET l2_bl.value='Aplicar', l2_bl.updated_at=datetime()
MERGE (lo2)-[l2_cr:HAS_SLOT]->(s_crit)  ON CREATE SET l2_cr.value='Pasa tests públicos y privados', l2_cr.updated_at=datetime()
MERGE (lo2)-[l2_ps:HAS_SLOT]->(s_peso)  ON CREATE SET l2_ps.value='1.0', l2_ps.updated_at=datetime();
;

/////////////////////////////////////////////////////////////////////////
// 13) HAS_SLOT — StudentState (difuso/longitudinal)
/////////////////////////////////////////////////////////////////////////
MATCH (st:StudentState {name:'Estado_Estudiante_Ejemplo'}),
      (s_mae:Slot {name:'maestria'}),
      (s_conf:Slot {name:'confianza'}),
      (s_fru:Slot {name:'frustracion'}),
      (s_est:Slot {name:'estilo'}),
      (s_rit:Slot {name:'ritmo'})
MERGE (st)-[st_mae:HAS_SLOT]->(s_mae)  ON CREATE SET st_mae.value='{ "Funcion": 0.4, "Variable": 0.6 }', st_mae.updated_at=datetime()
MERGE (st)-[st_cf:HAS_SLOT]->(s_conf)  ON CREATE SET st_cf.value='0.5', st_cf.updated_at=datetime()
MERGE (st)-[st_fr:HAS_SLOT]->(s_fru)   ON CREATE SET st_fr.value='0.3', st_fr.updated_at=datetime()
MERGE (st)-[st_es:HAS_SLOT]->(s_est)   ON CREATE SET st_es.value='visual', st_es.updated_at=datetime()
MERGE (st)-[st_rt:HAS_SLOT]->(s_rit)   ON CREATE SET st_rt.value='normal', st_rt.updated_at=datetime();
;

/////////////////////////////////////////////////////////////////////////
// 14) HAS_SLOT — MicroContenido / Consigna / Intervención Afectiva
/////////////////////////////////////////////////////////////////////////
MATCH (mc:MicroContenido {name:'MC_funciones_basicas'}),
      (cs:Consigna {name:'CS_suma_a_b'}),
      (ia:IntervencionAfectiva {name:'IA_pausa_microexito'}),
      (s_uri:Slot {name:'contenido_uri'}),
      (s_dur:Slot {name:'duracion_estimada'}),
      (s_txt:Slot {name:'texto'}),
      (s_ti:Slot  {name:'tipo_intervencion'}),
      (s_dp:Slot  {name:'disparador'})
MERGE (mc)-[mc_u:HAS_SLOT]->(s_uri) ON CREATE SET mc_u.value='https://recursos/funciones_basicas.html', mc_u.updated_at=datetime()
MERGE (mc)-[mc_d:HAS_SLOT]->(s_dur) ON CREATE SET mc_d.value='6', mc_d.updated_at=datetime()
MERGE (cs)-[cs_t:HAS_SLOT]->(s_txt)  ON CREATE SET cs_t.value='Implementá suma(a,b) y retorná el resultado', cs_t.updated_at=datetime()
MERGE (ia)-[ia_t:HAS_SLOT]->(s_ti)   ON CREATE SET ia_t.value='pausa', ia_t.updated_at=datetime()
MERGE (ia)-[ia_d:HAS_SLOT]->(s_dp)   ON CREATE SET ia_d.value='μ_frustracion alta (>0.7)', ia_d.updated_at=datetime();
;

/////////////////////////////////////////////////////////////////////////
// 15) HAS_FACET — tipado/rangos para Slots
/////////////////////////////////////////////////////////////////////////
MATCH
  (s_en:Slot {name:'enunciado'}),
  (s_pub:Slot {name:'tests_publicos'}),
  (s_priv:Slot {name:'tests_privados'}),
  (s_diff:Slot {name:'dificultad'}),
  (s_cod:Slot {name:'codigo'}),
  (s_res:Slot {name:'resultado_tests'}),
  (s_tim:Slot {name:'tiempo'}),
  (s_nh:Slot {name:'n_hints'}),
  (s_err:Slot {name:'errores_detectados'}),
  (s_ts:Slot {name:'timestamp'}),
  (s_txt:Slot {name:'texto'}),
  (s_lvl:Slot {name:'nivel'}),
  (s_pat:Slot {name:'patron_codigo'}),
  (s_desc:Slot {name:'descripcion'}),
  (s_corr:Slot {name:'correccion'}),
  (s_bloom:Slot {name:'taxonomia_bloom'}),
  (s_crit:Slot {name:'criterio_exito'}),
  (s_peso:Slot {name:'peso'}),
  (s_mae:Slot {name:'maestria'}),
  (s_conf:Slot {name:'confianza'}),
  (s_fru:Slot {name:'frustracion'}),
  (s_est:Slot {name:'estilo'}),
  (s_rit:Slot {name:'ritmo'}),
  (s_uri:Slot {name:'contenido_uri'}),
  (s_dur:Slot {name:'duracion_estimada'}),
  (s_tint:Slot {name:'tipo_intervencion'}),
  (s_disp:Slot {name:'disparador'}),
  (f_req:Facet {name:'requerido'}),
  (f_tipo:Facet {name:'tipo'}),
  (f_rng:Facet {name:'rango'}),
  (f_card:Facet {name:'cardinalidad'})
MERGE (s_en)-[:HAS_FACET]->(f_req)
MERGE (s_en)-[:HAS_FACET]->(f_tipo)
MERGE (s_pub)-[:HAS_FACET]->(f_tipo)
MERGE (s_priv)-[:HAS_FACET]->(f_tipo)
MERGE (s_diff)-[:HAS_FACET]->(f_tipo)
MERGE (s_cod)-[:HAS_FACET]->(f_tipo)
MERGE (s_res)-[:HAS_FACET]->(f_tipo)
MERGE (s_tim)-[:HAS_FACET]->(f_tipo)
MERGE (s_nh)-[:HAS_FACET]->(f_tipo)
MERGE (s_err)-[:HAS_FACET]->(f_tipo)
MERGE (s_ts)-[:HAS_FACET]->(f_tipo)
MERGE (s_txt)-[:HAS_FACET]->(f_tipo)
MERGE (s_lvl)-[:HAS_FACET]->(f_tipo)
MERGE (s_pat)-[:HAS_FACET]->(f_tipo)
MERGE (s_desc)-[:HAS_FACET]->(f_tipo)
MERGE (s_corr)-[:HAS_FACET]->(f_tipo)
MERGE (s_bloom)-[:HAS_FACET]->(f_tipo)
MERGE (s_crit)-[:HAS_FACET]->(f_tipo)
MERGE (s_peso)-[:HAS_FACET]->(f_tipo)
MERGE (s_mae)-[:HAS_FACET]->(f_rng)
MERGE (s_conf)-[:HAS_FACET]->(f_rng)
MERGE (s_fru)-[:HAS_FACET]->(f_rng)
MERGE (s_est)-[:HAS_FACET]->(f_tipo)
MERGE (s_rit)-[:HAS_FACET]->(f_tipo)
MERGE (s_uri)-[:HAS_FACET]->(f_tipo)
MERGE (s_dur)-[:HAS_FACET]->(f_tipo)
MERGE (s_tint)-[:HAS_FACET]->(f_tipo)
MERGE (s_disp)-[:HAS_FACET]->(f_tipo);
;

/////////////////////////////////////////////////////////////////////////
// 16) SANITY CHECKS (extendidos)
/////////////////////////////////////////////////////////////////////////
// Conteo por etiquetas
MATCH (n) RETURN labels(n) AS etiquetas, count(*) AS cantidad ORDER BY cantidad DESC;
;
// Conteo de relaciones
MATCH ()-[r]->() RETURN type(r) AS relacion, count(*) AS cantidad ORDER BY cantidad DESC;
;
// Frames sin slots (inspección)
MATCH (f:Frame)
WHERE NOT (f)-[:HAS_SLOT]->(:Slot)
RETURN f.name AS frame_sin_slots LIMIT 50;
;
// Ejercicios sin tests
MATCH (e:Exercise:Frame)
WHERE NOT (e)-[:HAS_SLOT]->(:Slot {name:'tests_publicos'})
   OR NOT (e)-[:HAS_SLOT]->(:Slot {name:'tests_privados'})
RETURN e.name AS ejercicio_incompleto;
;
// Ejercicios sin concepto
MATCH (e:Exercise:Frame)
WHERE NOT (e)-[:APUNTA_A]->(:PythonConcept:Frame)
RETURN e.name AS ejercicio_sin_concepto;
;
// Misconceptions sin hint
MATCH (m:Misconception:Frame)
WHERE NOT (m)-[:SE_CORRIGE_CON]->(:Hint:Frame)
RETURN m.name AS misconception_sin_hint;
;
// Slots sin facet
MATCH (s:Slot)
WHERE NOT (s)-[:HAS_FACET]->(:Facet)
RETURN s.name AS slot_sin_facet LIMIT 100;
;

/////////////////////////////////////////////////////////////////////////
// 17) DIFUSO — Parámetros gaussianos por Slot (Opción B)
/////////////////////////////////////////////////////////////////////////
// Para cada Slot [0..1] definimos la función de pertenencia 'gaussiana'
UNWIND [
  ['confianza',   0.15, 0.15,  0.50, 0.15,  0.85, 0.15],
  ['frustracion', 0.15, 0.15,  0.50, 0.15,  0.85, 0.15],
  ['maestria',    0.15, 0.15,  0.50, 0.15,  0.85, 0.15]
] AS row
WITH row[0] AS slot,
     row[1] AS a_baja,  row[2] AS b_baja,
     row[3] AS a_media, row[4] AS b_media,
     row[5] AS a_alta,  row[6] AS b_alta
MATCH (s:Slot {name: slot})
SET s.funcion_pertenencia = 'gaussiana',
    s.etiquetas = ['baja','media','alta'],
    s.a_baja  = a_baja,  s.b_baja  = b_baja,
    s.a_media = a_media, s.b_media = b_media,
    s.a_alta  = a_alta,  s.b_alta  = b_alta;
;

/////////////////////////////////////////////////////////////////////////
// 18) Defaults efectivos (completar si falta value en HAS_SLOT)
/////////////////////////////////////////////////////////////////////////
MATCH (f:Frame)-[r:HAS_SLOT]->(s:Slot {name:'n_hints'})
WHERE r.value IS NULL
SET r.value = '0', r.updated_at = datetime();
;

MATCH (f:Frame)-[r:HAS_SLOT]->(s:Slot {name:'tiempo'})
WHERE r.value IS NULL
SET r.value = '0', r.updated_at = datetime();
;

MATCH (f:Frame)-[r:HAS_SLOT]->(s:Slot {name:'nivel'})
WHERE r.value IS NULL
SET r.value = '1', r.updated_at = datetime();
;

/////////////////////////////////////////////////////////////////////////
// 19) Inferencia simple — sugerir próximo ejercicio (según maestría)
/////////////////////////////////////////////////////////////////////////
// Idea: priorizar ejercicios cuyo concepto principal tenga menor maestría
MATCH (st:StudentState {name:'Estado_Estudiante_Ejemplo'})-[rm:HAS_SLOT]->(:Slot {name:'maestria'})
WITH apoc.convert.fromJsonMap(rm.value) AS mx
WITH coalesce(mx['Funcion'],0.0) AS m_func
MATCH (e:Exercise)-[:APUNTA_A]->(:PythonConcept {name:'Funcion'})
WITH e, m_func
ORDER BY m_func ASC  // menor maestría → refuerzo
RETURN e.name AS ejercicio_recomendado LIMIT 1;
;

/////////////////////////////////////////////////////////////////////////
// 20) NLP — Preguntas de ejemplo para clasificación de temas
/////////////////////////////////////////////////////////////////////////

UNWIND [
  ["Q1", "No entiendo qué es una variable en Python"],
  ["Q2", "Cómo hago un bucle for que repita diez veces"],
  ["Q3", "Cuál es la diferencia entre lista y tupla"],
  ["Q4", "Qué significa NameError name is not defined"],
  ["Q5", "Cómo abro un archivo y leo sus líneas"],
  ["Q6", "No entiendo qué es self en una clase"]
] AS row

// Podés engancharlas al tutor y/o estudiante si querés
MATCH (t:TutorIA)
OPTIONAL MATCH (e:Estudiante {name:"Estudiante_Demo"})

MERGE (q:Frame:Question {name: row[0]})
SET q.texto     = row[1],
    q.creada_en = datetime()

MERGE (t)-[:RECIBE_DUDA]->(q)

FOREACH (_ IN CASE WHEN e IS NULL THEN [] ELSE [1] END |
  MERGE (e)-[:PREGUNTA]->(q)
);

//Conectar los temas con los conceptos del grafo
UNWIND [
  ["variables_y_tipos", "Variable"],
  ["variables_y_tipos", "Tipo"],
  ["control_de_flujo", "Bucle"],
  ["funciones", "Funcion"],
  ["estructuras_de_datos", "Lista"],
  ["errores_y_debugging", "Concatenar_str_int"],
  ["errores_y_debugging", "OffByOne_en_bucle"]
] AS row

MERGE (t:Tema {codigo: row[0]})
  ON CREATE SET t.nombre = row[0]

WITH t, row   // ← NECESARIO

MATCH (pc:PythonConcept:Frame {name: row[1]})
MERGE (t)-[:CUBRE_CONCEPTO]->(pc);



/////////////////////////////////////////////////////////////////////////
// 21) NLP — Enlazar preguntas con temas y conceptos de Python
/////////////////////////////////////////////////////////////////////////

// 21a) Crear relación explícita desde Question al Tema detectado
MATCH (q:Question)
WHERE q.tema IS NOT NULL
MATCH (t:Tema {codigo: q.tema})
MERGE (q)-[:CLASIFICADA_COMO]->(t);


// 21b) Ver el camino completo Question → Tema → PythonConcept
MATCH (q:Question)-[:CLASIFICADA_COMO]->(t:Tema)-[:CUBRE_CONCEPTO]->(pc:PythonConcept)
RETURN
  q.name        AS id_pregunta,
  q.texto       AS texto_pregunta,
  t.codigo      AS tema,
  collect(DISTINCT pc.name) AS conceptos_relacionados
ORDER BY tema, id_pregunta;


// 21c) (Opcional) Ver los paths en formato grafo para screenshot
MATCH p = (q:Question)-[:CLASIFICADA_COMO]->(t:Tema)-[:CUBRE_CONCEPTO]->(pc:PythonConcept)
RETURN p
LIMIT 25;

/////////////////////////////////////////////////////////////////////////
// 22) Descripciones para los PythonConcept del grafo TutorIA
/////////////////////////////////////////////////////////////////////////

MATCH (pc:PythonConcept {name:'Tipo'})
SET pc.descripcion = 'Categoría de dato en Python (int, float, str, bool, list, etc.), que determina qué valores puede tomar y qué operaciones se pueden hacer.';

MATCH (pc:PythonConcept {name:'Variable'})
SET pc.descripcion = 'Nombre que referencia un valor almacenado en memoria. Se crea al asignar con = y puede cambiar de valor durante la ejecución.';

MATCH (pc:PythonConcept {name:'Funcion'})
SET pc.descripcion = 'Bloque reutilizable de código que recibe parámetros (opcional), ejecuta instrucciones y puede devolver un resultado mediante return.';

MATCH (pc:PythonConcept {name:'Lista'})
SET pc.descripcion = 'Colección ordenada y mutable de elementos. Se define con corchetes [], permite índices, slicing y métodos como append, remove, sort.';

MATCH (pc:PythonConcept {name:'Bucle'})
SET pc.descripcion = 'Estructura de control que repite un bloque de código mientras se cumpla una condición (while) o al iterar una secuencia (for).';
