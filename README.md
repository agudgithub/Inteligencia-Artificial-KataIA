# TutorIA: Sistema Tutor Inteligente para Python

TutorIA es un sistema tutor inteligente diseñado para acompañar el aprendizaje de programación en Python. Integra un modelo generativo (LLM), una base de conocimiento orientada a grafos (Neo4j), procesamiento de lenguaje natural (NLP) y lógica difusa para adaptar la experiencia educativa a cada estudiante. El sistema responde preguntas abiertas, recomienda ejercicios personalizados y ajusta sus intervenciones según el estado emocional y de maestría detectado.

## Características principales

- **Respuestas automáticas** a preguntas sobre Python usando un modelo LLM (Ollama con llama3) vía Langchain.
- **Recomendación de ejercicios** adaptados al nivel y estado del estudiante.
- **Seguimiento de progreso** y registro de interacciones en una base Neo4j.
- **Procesamiento de lenguaje natural** para clasificar dudas y detectar temas.
- **Lógica difusa y triggers** para intervenciones afectivas y pedagógicas automáticas.
- **Arquitectura modular** y extensible, con integración de distintos componentes.


## Cómo ejecutar el proyecto

1. **Clonar el repositorio**
   ```sh
   git clone https://github.com/agudgithub/Inteligencia-Artificial-KataIA.git
   cd KataIA
   ```
2. **Instalar Docker**
   - Desde la pagina oficial para el sistema operativo respectivo: 
   `https://www.docker.com/`

3. **Inicializar la base de datos Neo4j y componentes**
   - Levanta Neo4j (usando Docker Compose):
     ```sh
     docker-compose up -d
     ```
   - Ejecuta el script Cypher para crear la estructura y datos base:
     - Ingresa a la consola de Neo4j ( desde el browser en `http://localhost:7474/browser/`)
     - Ejecuta el contenido de [`tutorIA_final_full.cypher`](tutorIA_final_full.cypher)

4. **Levantar el sistema TutorIA**
   - Para iniciar el módulo principal (preguntas/respuestas) desde la terminal:
     ```sh
     docker compose exec llm_tutor python llm_qa.py
     ```


## Índice de la Documentación Técnica

La documentación técnica se encuentra en la carpeta [`Documentacion_Tecnica`](Documentacion_Tecnica/):

1. [Módulo 1 - Red de Procesos](Documentacion_Tecnica/Modulo 1 - Red de Procesos/README.md):  
   Flujo general de interacción, modelado del proceso didáctico y adaptación personalizada.

2. [Módulo 2 - Red Semántica](Documentacion_Tecnica/Modulo 2 - Red Semantica/README.md):  
   Modelado de conceptos de Python, relaciones semánticas y recursos didácticos.

3. [Módulo 3 - Red de Frames](Documentacion_Tecnica/Modulo 3 - Red de Frames/README.md):  
   Estructura de conocimiento basada en frames y relaciones pedagógicas.

4. [Módulo 4 - Base Orientada a Grafos](Documentacion_Tecnica/Modulo 4 - Base Orientada a Grafos/README.md):  
   Implementación y consultas sobre la base Neo4j.

5. [Módulo 5 - Integración Módulo NLP](Documentacion_Tecnica/Modulo 5 - Integracion Modulo NLP/README.md):  
   Clasificación automática de preguntas y detección de temas usando NLP.

6. [Módulo 6 - Integración Módulo Generativo](Documentacion_Tecnica/Modulo 6 - Integracion Modulo Generativo/README.md):  
   Integración del modelo generativo (Ollama/llama3), lógica difusa y triggers automáticos.

---

Para más detalles sobre cada módulo, consulta los archivos README.md dentro de cada carpeta de la documentación técnica.