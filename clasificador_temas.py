# backend/nlp/clasificador_temas.py
import pathlib
import joblib

# Ruta al modelo .pkl (ajustá si tu estructura es distinta)
MODEL_PATH = pathlib.Path(__file__).with_name("modelo_temas_python.pkl")

# Cargamos una sola vez al importar el módulo
_modelo_temas = joblib.load(MODEL_PATH)


def _normalizar_tema(etiqueta: str) -> str:
    """Normaliza etiquetas del modelo a los códigos de Tema del grafo.

    Ver bloque 20 de tutorIA_final_full.cypher para los códigos usados:
    - variables_y_tipos
    - control_de_flujo
    - funciones
    - estructuras_de_datos
    - errores_y_debugging
    """
    if not etiqueta:
        return "variables_y_tipos"

    e = etiqueta.strip().lower()

    # Regla fuerte: si la etiqueta menciona "funcion"/"función"/"function",
    # forzamos el tema a "funciones".
    if "funcion" in e or "función" in e or "function" in e:
        return "funciones"

    mapa = {
        # POO y variantes → funciones
        "poo": "funciones",
        "orientado_a_objetos": "funciones",
        # Alias de funciones
        "funcion": "funciones",
        "funciones": "funciones",
        # Listas / estructuras de datos
        "lista": "estructuras_de_datos",
        "listas": "estructuras_de_datos",
        "estructuras": "estructuras_de_datos",
        # Control de flujo
        "bucle": "control_de_flujo",
        "bucles": "control_de_flujo",
        "condicional": "control_de_flujo",
        "condicionales": "control_de_flujo",
        # Errores / debugging
        "errores": "errores_y_debugging",
        "debug": "errores_y_debugging",
    }

    return mapa.get(e, e)


def predecir_tema(texto: str) -> str:
    """Devuelve la etiqueta de tema normalizada para una duda dada."""
    etiqueta_cruda = _modelo_temas.predict([texto])[0]
    return _normalizar_tema(etiqueta_cruda)
