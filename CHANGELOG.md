# Novedades

Todos los cambios importantes del proyecto, del más reciente al más antiguo.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones, [SemVer](https://semver.org/lang/es/).

## [1.2.0] - 2026-10-22

### Añadido
- **Aplicación de escritorio.** El menú se abre en su propia ventana, sin navegador ni consola
  ([`menu/aplicacion.py`](menu/aplicacion.py), con pywebview y el motor WebView2 de Windows):
  - icono propio en la barra de título y en la de tareas;
  - tamaño ajustado a la pantalla y ventana centrada;
  - al cerrar la ventana se apaga el servidor; si hay tareas en marcha, pregunta antes y las cancela;
  - los enlaces externos (YouTube, Google Cloud…) se abren en el navegador;
  - recuerda el tema claro u oscuro entre sesiones;
  - si el menú ya estaba abierto, se conecta a él en vez de arrancar otro;
  - los errores quedan en `salida/_trabajo/menu.log` y se avisan con un cuadro de diálogo.
- **Lanzador `Mente Inquieta.exe`** de 78 KB, escrito en C# y compilado con el compilador que trae Windows
  ([`lanzador/crear_exe.bat`](lanzador/crear_exe.bat)). Usa el Python del entorno `.venv`, así que los cambios del
  código se aplican sin recompilarlo.
- Este archivo de novedades.

### Cambiado
- Instrucciones de instalación y uso del README y de `menu/LEEME.txt`.
- `requirements.txt` incluye `pywebview`.

## [1.1.0] - 2026-10-22

### Cambiado
- **Rediseño del menú, moderno y minimalista:**
  - barra lateral con iconos y contador de tareas en marcha;
  - identidad del canal (azul noche y dorado del logo) y tipografía Inter;
  - selector de modo segmentado (tema libre, efemérides, «Diario de…») y opciones como fichas;
  - etiquetas de estado discretas y menos emojis;
  - tema claro / oscuro (sigue al de Windows o se cambia con un botón);
  - versión adaptada al móvil.

## [1.0.0] - 2026-10-22

Primera versión publicada.

### Añadido
- **Guion:** material de Wikipedia, guion de 60-75 s en escenas escrito por un LLM (Groq) con gancho, tono musical
  y nombre corto; verificador frase a frase contra la fuente (*LLM-as-a-judge*); modelos de reserva cuando se agota el
  cupo diario.
- **Formatos:** tema libre, series de varias partes con índice previo, efemérides y «Diario de…» (humor histórico en
  primera persona con imágenes generadas por IA).
- **Voz:** edge-tts con tiempos por palabra; solo se regeneran las escenas cambiadas.
- **Vídeo:**
  - imágenes de Wikipedia, Wikimedia Commons, The Met y el Art Institute of Chicago, elegidas por relevancia;
  - subtítulos palabra a palabra con palabras clave resaltadas;
  - música sintetizada que baja sola cuando habla la voz;
  - toma final animada de «like y suscríbete»;
  - miniatura y textos para publicar;
  - segmentos en caché para rehacer en segundos.
- **Publicación:** subida a YouTube Shorts por la API oficial, con publicación programada y aviso de contenido
  sintético; texto preparado para TikTok.
- **Menú web** (Flask) con cola de tareas, selector de imágenes, ajustes de voz y música y conexión con YouTube.
- **Piloto automático** con el Programador de tareas de Windows.
- Acceso común a las APIs de Wikimedia con caché, ritmo por servidor y respeto a `Retry-After`.

[1.2.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/luukthegoat/pipeline-curiosidades/releases/tag/v1.0.0
