/////////////////////////////////////////////////////////////////////////
// 0) RESET DE INSTANCIACIÓN (solo estudiantes + attempts)
//    ⚠ Ejecutar solo si querés limpiar instancias previas
/////////////////////////////////////////////////////////////////////////
MATCH (ana:Estudiante {name:"Estudiante_Ana"})
OPTIONAL MATCH (ana)-[:REALIZA]->(att:Attempt)
DETACH DELETE ana, att;
;

/////////////////////////////////////////////////////////////////////////
// 1) Crear estudiante concreto (instanciación de Estudiante_Demo)
/////////////////////////////////////////////////////////////////////////
MERGE (ana:Estudiante:Frame {name:"Estudiante_Ana"});
;

/////////////////////////////////////////////////////////////////////////
// 2) Crear un nuevo intento de Ana sobre el ejercicio E_SumaDosNumeros
/////////////////////////////////////////////////////////////////////////
MATCH (ana:Estudiante {name:"Estudiante_Ana"}),
      (ex:Exercise {name:"E_SumaDosNumeros"})
MERGE (att:Attempt:Frame {name:"Attempt_e1_v2"})   // v2 = segundo intento
MERGE (ana)-[:REALIZA]->(att)
MERGE (att)-[:USA]->(ex);
;

/////////////////////////////////////////////////////////////////////////
// 3) Guardar datos del intento en HAS_SLOT
/////////////////////////////////////////////////////////////////////////
MATCH (att:Attempt {name:"Attempt_e1_v2"}),
      (s_cod:Slot {name:"codigo"}),
      (s_res:Slot {name:"resultado_tests"}),
      (s_tim:Slot {name:"tiempo"}),
      (s_nh:Slot {name:"n_hints"}),
      (s_err:Slot {name:"errores_detectados"}),
      (s_ts:Slot {name:"timestamp"})
MERGE (att)-[cd:HAS_SLOT]->(s_cod) ON CREATE SET cd.value="def suma(a,b): return a-b", cd.updated_at=datetime()
MERGE (att)-[rs:HAS_SLOT]->(s_res) ON CREATE SET rs.value='{"publicos":"fail","privados":"fail"}', rs.updated_at=datetime()
MERGE (att)-[tm:HAS_SLOT]->(s_tim) ON CREATE SET tm.value="15.4", tm.updated_at=datetime()
MERGE (att)-[nh:HAS_SLOT]->(s_nh)  ON CREATE SET nh.value="2", nh.updated_at=datetime()
MERGE (att)-[er:HAS_SLOT]->(s_err) ON CREATE SET er.value="['off_by_one']", er.updated_at=datetime()
MERGE (att)-[ts:HAS_SLOT]->(s_ts)  ON CREATE SET ts.value=toString(datetime()), ts.updated_at=datetime();
;

/////////////////////////////////////////////////////////////////////////
// 4) Relacionar evaluación, misconception y hint recibido
/////////////////////////////////////////////////////////////////////////
MATCH (ana:Estudiante {name:"Estudiante_Ana"}),
      (att:Attempt {name:"Attempt_e1_v2"}),
      (ev:Evaluacion {name:"Eval_UnitTest"}),
      (mis:Misconception {name:"OffByOne_en_bucle"}),
      (hint:Hint {name:"Hint_off_by_one_n1"})
MERGE (ev)-[:EVALUA]->(att)
MERGE (ev)-[:DETECTA]->(mis)
MERGE (mis)-[:SE_CORRIGE_CON]->(hint)
MERGE (ana)-[:RECIBE]->(hint);
;

/////////////////////////////////////////////////////////////////////////
// 5) Actualizar estado difuso del estudiante
/////////////////////////////////////////////////////////////////////////
MATCH (st:StudentState {name:"Estado_Estudiante_Ejemplo"}),
      (s_mae:Slot {name:"maestria"}),
      (s_conf:Slot {name:"confianza"}),
      (s_fru:Slot {name:"frustracion"})
MERGE (st)-[mae:HAS_SLOT]->(s_mae)
  SET mae.value='{ "Funcion": 0.5, "Variable": 0.6 }', mae.updated_at=datetime()
MERGE (st)-[cf:HAS_SLOT]->(s_conf)
  SET cf.value="0.3", cf.updated_at=datetime()
MERGE (st)-[fr:HAS_SLOT]->(s_fru)
  SET fr.value="0.7", fr.updated_at=datetime();
;

/////////////////////////////////////////////////////////////////////////
// 6) CONSULTA DE VERIFICACIÓN FINAL — sin duplicados
/////////////////////////////////////////////////////////////////////////

// 1. Estado difuso
MATCH (st:StudentState {name:"Estado_Estudiante_Ejemplo"})-[rs:HAS_SLOT]->(ss:Slot)
WITH collect(DISTINCT {slot:ss.name, valor:rs.value}) AS Estado_Difuso

// 2. Intento y slots
MATCH (ana:Estudiante {name:"Estudiante_Ana"})
OPTIONAL MATCH (ana)-[:REALIZA]->(att:Attempt)-[:USA]->(ex:Exercise)
WITH Estado_Difuso, ana, att, ex
OPTIONAL MATCH (att)-[r:HAS_SLOT]->(s:Slot)
WITH Estado_Difuso, ana, ex, att, collect(DISTINCT {slot:s.name, valor:r.value}) AS Datos_Attempt

// 3. Hints recibidos
OPTIONAL MATCH (ana)-[:RECIBE]->(hint:Hint)
WITH Estado_Difuso, ana, ex, att, Datos_Attempt, collect(DISTINCT hint.name) AS Hints_Recibidos

// 4. Resultado final
RETURN 
  ana.name AS Estudiante,
  ex.name  AS Ejercicio,
  att.name AS Intento,
  Estado_Difuso,
  Datos_Attempt,
  Hints_Recibidos;
;





/////////////////////////////////////////////////////////////////////////
// CONSULTA FINAL — mostrar último intento primero
/////////////////////////////////////////////////////////////////////////

MATCH (ana:Estudiante {name:"Estudiante_Ana"})

CALL {
  MATCH (st:StudentState {name:"Estado_Estudiante_Ejemplo"})-[rs:HAS_SLOT]->(ss:Slot)
  RETURN collect({slot:ss.name, valor:rs.value}) AS Estado_Difuso
}

CALL {
  MATCH (ana)-[:REALIZA]->(att:Attempt)-[:USA]->(ex:Exercise)
  OPTIONAL MATCH (att)-[r:HAS_SLOT]->(s:Slot {name:"timestamp"})
  WITH att, ex, s, r
  ORDER BY r.value DESC               // 👈 más nuevo primero
  LIMIT 2                             // 👈 solo el último intento
  OPTIONAL MATCH (att)-[r2:HAS_SLOT]->(s2:Slot)
  RETURN att.name AS Intento, ex.name AS Ejercicio,
         collect({slot:s2.name, valor:r2.value}) AS Datos_Attempt
}

CALL {
  MATCH (ana)-[:RECIBE]->(hint:Hint)
  RETURN collect(DISTINCT hint.name) AS Hints_Recibidos
}

RETURN ana.name AS Estudiante, Ejercicio, Intento, Estado_Difuso, Datos_Attempt, Hints_Recibidos;
