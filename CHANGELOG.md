# Novedades

Todos los cambios importantes del proyecto, del más reciente al más antiguo.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones, [SemVer](https://semver.org/lang/es/).

## [1.12.1] - 2026-10-26

### Añadido
- **Botón «↻ Actualizar»** en Programados (Lista y Calendario): trae de YouTube lo cambiado en YouTube Studio (la hora,
  si se publicó antes o si se borró) sin esperar a la comprobación automática, dice qué ha cambiado y vuelve a la
  misma vista. Sustituye a «Revisar ahora».

## [1.12.0] - 2026-10-26

### Añadido
- **Escenas con vídeo real de archivo.** Además de fotos, cada vídeo puede llevar hasta 3 clips en movimiento: primero
  los que los editores de Wikipedia han puesto en el artículo (en español y en inglés) y, si no, los de Wikimedia
  Commons que nombren bien el tema. Se descarga solo el trozo que se usa, se coloca como las fotos (en la franja
  central, sobre un fondo desenfocado) y sin su sonido. Sus créditos van en la descripción marcados como «(vídeo)».
- En **Elegir imágenes** salen también los clips (con ▶ y su duración), siempre todos, para ponerlos a mano.

### Arreglado
- **Imágenes que no eran del tema** en la búsqueda de Commons: «11S» traía fotos de la proteína «11S proteasome».
  Ahora lo que llega de Commons tiene que nombrar el tema del artículo.

## [1.11.1] - 2026-10-26

### Arreglado
- **Vídeos atascados en «procesándose» en YouTube** (desde la 1.10.2): la subida con límite de espera trataba las
  respuestas 308 de YouTube como redirecciones y el vídeo llegaba incompleto (0 s). Ahora usa la conexión de la librería
  de Google con ese caso resuelto, manteniendo el límite de 3 minutos.

## [1.11.0] - 2026-10-26

### Cambiado
- **Nuevo diseño, más claro y dirigido.** Barra de arriba con solo cuatro secciones (**Crear**, **Mis vídeos**,
  **Programados** y **Ajustes**) y todo en una columna, de arriba abajo. Las tareas en marcha se ven arriba a la derecha y
  la Ayuda está dentro de Ajustes.
- **Tema Índigo** en lugar del dorado, en modo claro y oscuro.
- **Crear** es solo el formulario, en tres pasos (tipo, detalles y opciones), con lo último creado debajo.
- **Mis vídeos** junta la lista de vídeos y la antigua página Pendientes, con filtros (*Por revisar · Listos ·
  Programados · Publicados*) y la acción que toca en cada fila.
- **La página de cada vídeo va por pasos**: revisa el texto, genera el vídeo y publícalo. Lo que ya está hecho se marca
  y se pliega; lo secundario (texto para publicar, prompts, borrar) está en «Más opciones».

### Añadido
- **Resumen del día** en Mis vídeos: qué se publica hoy y a qué hora, cuántos quedan por revisar o listos, y cuántas
  subidas a YouTube llevas en 24 h.
- **«Revisado → programar»**: da el vídeo por revisado y lo programa a su hora recomendada con un solo clic, desde la
  lista o desde su página.
- **Aviso en todas las páginas** cuando un vídeo programado no se ha podido subir a YouTube.

### Arreglado
- **«Mente Inquieta.exe» a veces no abría nada**: si había otra ventana llamada «Mente Inquieta» (p. ej. una pestaña
  del navegador con el menú), creía que la app ya estaba abierta y se cerraba. Ahora lo comprueba con el bloqueo de la
  propia app. Vuelve a compilarse con `lanzador\crear_exe.bat`.

### Quitado
- **Piloto automático** (y sus dos tareas de Windows), los **recordatorios de TikTok** y la **selección múltiple** del
  inicio. Para programar varios a la vez está «Programar todos» en Mis vídeos → Listos.

## [1.10.2] - 2026-10-25

### Cambiado
- **Hasta 5 subidas en 24 h** desde Programados (antes 3), dentro del cupo diario de la API de YouTube.
  Se cambia con `PROGRAMADOS_MAX_DIA`.

### Arreglado
- **Subidas colgadas durante horas**: si YouTube deja de responder 3 minutos, la conexión se da por perdida
  en vez de esperar sin límite.
- **Duplicados cuando la conexión se corta al terminar una subida**: antes de darla por fallida, se mira en el canal
  si el vídeo llegó a crearse y, si está, se enlaza en lugar de volver a subirlo.

## [1.10.1] - 2026-10-24

### Arreglado
- **La cola de Programados se pone al día con YouTube.** Lo que se cambia en YouTube Studio (adelantar la publicación,
  cambiar la hora, borrar un vídeo) ya no deja la app desfasada: se comprueba cada 15 minutos, antes de cada subida y al
  pulsar «Revisar». Si un vídeo se ha borrado en YouTube, pasa a «error» y «Reintentar» lo vuelve a subir.
- **«Publicar ya» no hacía nada si se había llegado al máximo de subidas en 24 h del programa**: el vídeo se quedaba
  esperando sin avisar. Ahora se sube al momento (el límite de YouTube se sigue respetando) y no bloquea a los demás.
- El mensaje tras «Publicar ya» ya no dice que «el ordenador estaba apagado».

## [1.10.0] - 2026-10-24

### Añadido
- **Programar solos los vídeos sin avisos.** Al terminar de generar un vídeo, si el verificador no ha marcado ninguna
  frase, se da por revisado y se programa a su hora recomendada. No se aplica a los de actualidad (siempre a mano) ni a
  los que tienen frases dudosas. Se activa o desactiva en Ajustes (`AUTO_PROGRAMAR`).
- **Calendario** (Programados → Calendario): el mes con los vídeos de cada día y su hora, por colores (en cola, en
  YouTube programado, publicado, con error), navegable por meses; en el móvil, lista por días.

### Cambiado
- **Los programados se suben a YouTube en cuanto hay hueco** (hasta 30 días antes de su hora, antes 48 h), ya
  programados: así casi todo queda en YouTube y se publica aunque el ordenador esté apagado. Se sigue respetando el
  máximo de subidas en 24 h.

## [1.9.0] - 2026-10-23

### Añadido
- **Formato «Vídeo con IA»** ([`video_ia.py`](video_ia.py)): la app escribe el guion y un prompt de vídeo por escena;
  tú generas cada clip en una IA de vídeo y lo subes; la app lo monta.
  - Desplegable con Google Veo 3, Sora, Runway y Kling, con el enlace a la web de cada una, su consejo y la duración de
    sus clips.
  - Voz de la IA (el personaje dice su frase en el clip, para las que generan audio) o narración de la app sobre clips
    mudos (con el sonido del clip de fondo).
  - Prompts en inglés con formato vertical, estilo visual, personaje fijo en todas las escenas, acción y plano de cámara.
  - En la página del guion, cada escena con su prompt («Copiar»), «Subir clip», vista previa y «Quitar».
  - Montaje con los clips: recorte a 9:16, bucle o recorte para cuadrar con la escena, subtítulos, gancho, música,
    cierre, miniatura de un fotograma y aviso de «vídeo generado con IA» en la descripción.
  - Borrar un vídeo borra también sus clips.

### Corregido
- **Vídeos duplicados en YouTube.** Al subir los programados, un mensaje con «✔» rompía el proceso en algunas consolas
  justo después de que YouTube aceptara el vídeo: quedaba subido pero apuntado como «error», y al reintentarlo se
  subía otra vez. Ahora la subida se apunta en el guion en cuanto YouTube la confirma (antes de cualquier mensaje),
  los mensajes no pueden romper nada y, si algo falla después de subir, la cola lo da por subido.
- **«Reintentar»** en Programados mantiene la hora del vídeo; antes era «Reintentar ya» y lo publicaba al momento.
  «Publicar ya» es un botón aparte que pide confirmación.
- **Un guion nunca pisa a otro que ya existe** (p. ej. al volver a crear las efemérides de un día): el nuevo se guarda
  con «_2». Antes se perdía el guion anterior, aunque estuviera revisado o tuviera vídeo.

### Cambiado
- **Selector del tipo de vídeo** en Crear: tarjetas con el nombre completo, un icono y una línea de ayuda (2×2 en el
  móvil), en vez de pestañas recortadas.

## [1.8.1] - 2026-10-23

### Corregido
- Un corte breve de internet al escribir los guiones hacía fallar todas las partes de golpe («Failed to resolve
  api.groq.com»). Ahora se reintenta solo durante casi 2 minutos antes de dar el error, con un mensaje claro.

## [1.8.0] - 2026-10-23

### Añadido
- **Vídeos de actualidad** (Crear → Actualidad), para noticias que aún no están en Wikipedia:
  - [`actualidad.py`](actualidad.py) busca artículos recientes con Bing Noticias (gratis, sin clave) o con Tavily (si
    hay `TAVILY_API_KEY`), descarga su texto con `trafilatura`, se queda con uno por medio y marca los medios
    reconocidos.
  - Página para elegir los artículos (mínimo 2 medios) antes de escribir el guion.
  - Guion propio de noticias (`paso1_guiones.py --actualidad`): solo hechos de los artículos, cifras atribuidas
    («según…»), fechas, tono neutro, sin nombrar a particulares y con la fecha de los datos; todo traducido si los
    artículos están en otro idioma. El verificador lo compara con los artículos.
  - Imágenes de archivo de Wikimedia Commons (lugares e instituciones, nunca fotos de prensa) con el rótulo
    «IMAGEN DE ARCHIVO», o «FOTO: WIKIMEDIA COMMONS» si son de este año.
  - Descripción y texto de TikTok con los medios, la fecha de los datos y el aviso sobre las imágenes.
  - Hora recomendada para actualidad: la primera franja libre.
- Ajustes → Noticias de actualidad: clave opcional de Tavily.

## [1.7.0] - 2026-10-23

### Corregido
- **Piloto automático:**
  - La página tardaba unos 8 s en abrirse (consultaba las tareas de Windows con PowerShell) y parecía colgada; ahora
    usa `schtasks` y se abre al momento. Lo mismo al guardar la configuración.
  - «Ejecutar ahora» no hacía nada si el piloto estaba desactivado; ahora crea el vídeo siempre.
  - Si la efeméride del día ya existía (hecha a mano), la reescribía —perdiendo la revisión— y además daba el día por
    fallido. Ahora se salta las que ya tienen guion y coge el siguiente hecho del día (`paso1_guiones.py --sin-repetir`).
  - Subía directamente a YouTube y chocaba con el límite diario de subidas. Ahora deja el vídeo en Programados, que lo
    sube a su tiempo sin pasarse del límite.
  - Con frases dudosas subía un borrador privado (gastando una subida); ahora lo deja en Pendientes y avisa.
  - El estado avisa si la última ejecución falló o si la tarea de Windows y la configuración no coinciden.

### Añadido
- Piloto automático: opción de publicar a la hora recomendada para el tipo de vídeo (activada por defecto).

## [1.6.0] - 2026-10-23

### Añadido
- **Borrar un vídeo y todo lo suyo** ([`borrar.py`](borrar.py)), desde su página («Borrar…») o desde Pendientes:
  guion, voz y subtítulos, escenas en caché, imágenes de IA y propias, vídeo, miniatura y textos; también lo quita de
  Programados y de los recordatorios de TikTok, y borra la carpeta del tema si se queda vacía.
  - Todo va a la Papelera de reciclaje de Windows (se puede recuperar).
  - Antes de borrar se ve la lista exacta de lo que se va.
  - Opción de borrarlo también de YouTube; viene marcada si estaba programado allí y aún no se había publicado.
  - No deja borrar mientras haya tareas en marcha ni mientras se está subiendo a YouTube.

### Corregido
- Un mensaje con flechas o acentos en una consola que no es UTF-8 ya no impide abrir el menú.

## [1.5.0] - 2026-10-23

### Añadido
- **Página «Pendientes»** en la barra lateral, con contador: todos los vídeos que aún no están en YouTube ni programados.
  - **Por revisar:** tipo de vídeo, frases dudosas del verificador, «Revisar» y «Marcar revisado» (pide confirmación
    si hay dudas).
  - **Listos para programar:** cada uno con su hora recomendada y el motivo, editable, y «Programar todos a su hora
    recomendada».
  - **Revisados sin vídeo:** con un botón para generarlo.
- **Horas recomendadas según el tipo de vídeo** ([`horarios.py`](horarios.py)): efemérides el mismo día del
  aniversario por la mañana, series una parte al día a la misma hora, humor y temas serios por la noche, divulgación a
  mediodía o por la noche y vídeos en inglés a la hora de comer en EE. UU. Como mucho 2 al día, separados 3 h y sin
  pisar lo ya programado; si la franja ideal está ocupada, lo dice.
- La hora recomendada sale también al programar desde la página del vídeo y como opción «A las horas recomendadas» al
  publicar varios desde el inicio (con el motivo de cada una al pasar el ratón).

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

[1.12.1]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.12.0...v1.12.1
[1.12.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.11.1...v1.12.0
[1.11.1]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.11.0...v1.11.1
[1.11.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.10.2...v1.11.0
[1.10.2]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.10.1...v1.10.2
[1.10.1]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.10.0...v1.10.1
[1.10.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.9.0...v1.10.0
[1.9.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.8.1...v1.9.0
[1.8.1]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.8.0...v1.8.1
[1.8.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.4.0...v1.7.0
[1.6.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.4.0...v1.7.0
[1.5.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.4.0...v1.7.0
[1.4.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.3.1...v1.4.0
[1.3.1]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/luukthegoat/pipeline-curiosidades/releases/tag/v1.0.0
