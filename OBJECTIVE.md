# OBJECTIVE.md

## Contexto

Tengo una cuenta de **Coursera Plus (individual)** y quiero automatizar la descarga del material de los cursos en los que estoy inscrito, para tener una copia local organizada.

En la interfaz de Coursera, dentro de cada lección de video, hay un panel lateral **"Files"** (se abre con un botón) que expone enlaces de descarga directa para:
- El video en distintas resoluciones (ej. `Lecture Video (240p)`, `Lecture Video (1080p)`) en `.mp4`
- Subtítulos en `.vtt` (WebVTT)
- Transcripción en `.txt`
- A veces notebooks (`.ipynb`) u otros adjuntos

Adjunto dos capturas de pantalla como referencia de cómo se ve esta UI (panel de "Files" con los mp4/vtt/txt, y una página de tipo "Reading" con contenido de texto/HTML).

## Objetivo principal (MVP)

Construir un script/agente que, dado un curso de Coursera (o un módulo dentro de un curso), descargue automáticamente:
1. Los videos de las lecciones (idealmente en la mejor resolución disponible, o resolución configurable)
2. Los subtítulos de esos videos (`.vtt`, en inglés y/o el idioma disponible)

Y los guarde en disco de forma organizada.

## Objetivo secundario

Una vez el MVP funcione, ampliar la cobertura a otros tipos de contenido descargable/extraíble:
- Lecturas (readings) — exportar el contenido (HTML/texto) a Markdown o PDF
- Exámenes / quizzes — al menos guardar las preguntas (si es posible)
- Transcripciones (`.txt`)
- Notebooks (`.ipynb`) u otros adjuntos que aparezcan en el panel "Files"

## Alcance incremental (importante)

No intentes resolver "toda una especialización" de una. El desarrollo debe ser iterativo:
1. **Fase 1:** descargar el contenido de **un solo módulo** de un curso (todas las lecciones de video + subtítulos de ese módulo)
2. **Fase 2:** extender a **un curso completo** (todos los módulos)
3. **Fase 3:** extender a una **especialización completa** (varios cursos)

No implementes las fases 2 y 3 de golpe — primero valida que la fase 1 funciona de forma robusta.

## Consideraciones técnicas a evaluar

Antes de escribir código, evalúa y decide (y explícame el razonamiento) entre estas estrategias:

1. **¿Existe una API oficial de Coursera** (App Item / Content API, u otra) accesible con una cuenta Coursera Plus individual que permita listar el contenido de un curso y obtener las URLs de descarga sin pasar por la UI? Investiga si es viable con las credenciales de un usuario normal (no partner/instructor).
2. **Automatización de navegador (Playwright u otra herramienta similar):** dado que Coursera es una SPA que tarda en cargar el DOM y requiere sesión autenticada, evalúa usar Playwright para:
   - Iniciar sesión (reutilizando una sesión/cookies existentes, para no lidiar con 2FA/captcha en cada corrida)
   - Navegar a cada lección
   - Abrir el panel "Files"
   - Interceptar las peticiones de red (network requests) para capturar las URLs reales de descarga de los mp4/vtt, en lugar de simular clics en el botón de descarga del navegador (más confiable y evita problemas con el gestor de descargas del OS)
3. Comparar ambos enfoques (API vs. browser automation) en términos de robustez, mantenibilidad y riesgo de romperse ante cambios de UI, y proponer cuál usar para el MVP.

## Manejo de carga lenta / SPA

Coursera tarda en renderizar su DOM. El agente/script **no debe hacer scraping de páginas vacías**. Debe:
- Esperar explícitamente a que los elementos relevantes existan (esperas basadas en selectores/estado, no `sleep()` fijos y arbitrarios)
- Tener reintentos con backoff si un elemento no aparece
- Idealmente, esperar a que las peticiones de red relevantes (XHR/fetch) terminen antes de asumir que la página cargó

## Organización de archivos descargados

El script debe guardar el contenido en carpetas ordenadas, por ejemplo:
downloads/
<nombre-del-curso>/
<numero>-<nombre-del-modulo>/
<numero>-<nombre-de-la-leccion>/
video.mp4
subtitles.en.vtt
transcript.txt


(La convención exacta de nombres la puede proponer el agente, pero debe ser consistente y legible.)

## Experiencia de uso esperada

El script debe ser fácil de iniciar:
- El usuario debe poder indicar qué curso (y opcionalmente qué módulo) quiere descargar de forma simple (URL del curso, o slug, o selección interactiva)
- Configuración mínima para arrancar (idealmente un solo comando)
- Manejo claro de errores (ej. login fallido, contenido no descargable, video no disponible en cierta resolución)

## Notas finales

- Siéntete libre de preguntarme cualquier duda antes de o durante la implementación (credenciales, estructura de carpetas, formato de nombres, resolución preferida de video, si prefiero API vs. browser automation, etc.)
- Prioriza un MVP simple y funcional sobre una solución perfecta pero compleja
- Documenta las decisiones técnicas que tomes (por qué API vs. Playwright, por qué cierta estructura de carpetas, etc.)
