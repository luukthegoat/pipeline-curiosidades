# Novedades

Todos los cambios importantes del proyecto, del más reciente al más antiguo.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones, [SemVer](https://semver.org/lang/es/).

## [1.4.0] - 2026-10-23

### Añadido
- **Programados en modo mixto** ([`programados.py`](programados.py)). Programar ya no sube el vídeo al momento: queda
  en una cola del programa, que lo sube a YouTube entre 48 h y unos minutos antes de su hora, ya programado, y YouTube
  lo publica a su hora aunque el ordenador esté apagado.
  - Como mucho 3 subidas en 24 h (contando las manuales), para no chocar con el límite de subidas de YouTube; si
    YouTube frena igualmente, el vídeo sigue en cola y se reintenta solo.
  - Si un vídeo no llegó a subirse a tiempo (ordenador apagado), se publica en cuanto se sube.
  - Lo revisa el menú cada minuto mientras está abierto y una tarea de Windows que se reprograma sola para la próxima
    subida y también se lanza al iniciar sesión. Aviso de Windows tras cada subida o error.
- **Página «Programados»** en la barra lateral: todos los vídeos programados con su día, hora y estado (en cola, en
  YouTube, con error), cuánto falta y las subidas de las últimas 24 h. Desde ahí se puede publicar uno ya, cambiarle
  la hora o quitarlo (si ya estaba en YouTube, se cambia allí también), y ver el historial de publicados.
- Los guiones programados se marcan en el inicio y en su página.
- `subir_youtube.cambiar_publicacion()`: cambia la hora o la visibilidad de un vídeo ya subido.
- Ajustes `PROGRAMADOS_ANTELACION_H` y `PROGRAMADOS_MAX_DIA` en `.env`.

### Cambiado
- En la página del vídeo, «Publicar en YouTube» pide primero **Ahora** o **Programar**.
- «Programados y escalonados» (al publicar varios) usa la nueva cola.

## [1.3.1] - 2026-10-23

### Corregido
- **Solo una copia de la aplicación.** Abrir `Mente Inquieta.exe` cuando ya estaba abierta (o abriéndose) creaba una
  segunda ventana, que dejaba de funcionar al cerrar la primera. Ahora se trae al frente la ventana que ya había.
- **Arranque sin esperas a ciegas.** El `.exe` muestra al momento una pantalla de carga con el logo y la ventana
  aparece con otra mientras se carga el menú (antes tardaba unos 6 s sin dar ninguna señal).

## [1.3.0] - 2026-10-22

### Añadido
- **Acciones en lote en el inicio.** Casillas para seleccionar varios guiones (o todos) y una barra flotante con:
  - **Marcar como revisados:** verifica todos los seleccionados de una vez;
  - **Publicar en YouTube:** los sube uno tras otro en el orden de la lista (las partes de una serie, en orden),
    ahora o programados y escalonados (el primero a una hora y después uno cada X horas). Antes de confirmar se ve el
    orden, la hora de cada uno y cuáles se saltan y por qué; avisa si se pasa del cupo diario de YouTube.
- `subir_youtube.py --cada HORAS`: con varios guiones y `--publicar-el`, escalona las horas de publicación.

### Cambiado
- El CSS lleva su versión en la dirección, así que tras cambiarlo no se queda una copia vieja en caché.
- Los controles nativos (calendario, barras de desplazamiento) siguen el tema claro u oscuro.

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

[1.4.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.3.1...v1.4.0
[1.3.1]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/luukthegoat/pipeline-curiosidades/releases/tag/v1.0.0
