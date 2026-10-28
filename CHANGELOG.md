# Novedades

Todos los cambios importantes del proyecto, del más reciente al más antiguo.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones, [SemVer](https://semver.org/lang/es/).

## [1.19.0] - 2026-10-28

### Añadido
- **Vídeos largos explicados con dibujos** (apartado «Vídeos largos» del menú): vídeos horizontales de unos 10 minutos,
  por capítulos, al estilo «X en 10 minutos». A partir de un artículo de Wikipedia, el LLM escribe el índice y cada
  capítulo (en orden cronológico estricto), y el verificador lo comprueba y hace reescribir las frases sin respaldo.
- **Dibujos propios en vez de fotos** (`scripts/dibujos.py`): cada escena es un SVG con estilo de rotulador y trazo a
  mano: el narrador Bonesy en varias posturas, personajes históricos sencillos con su nombre, mapas de España (con
  Canarias en su recuadro) y del mundo con las zonas de colores, flechas y puntos, calendarios, cifras, líneas de
  tiempo y comparaciones; los objetos son dibujos de Twemoji. Edge, mediante Playwright, convierte cada escena en
  imagen (unos 50 s para todo un vídeo).
- **Las cosas aparecen cuando la voz las nombra:** cada escena se dibuja por pasos y cada elemento entra, con un
  fundido corto, en la palabra en que lo dice la voz.
- **Revisar el guion en la app antes de dibujar:** cada escena con su texto, su dibujo y las dudas del verificador; se
  puede corregir el texto, el título, los capítulos y la miniatura, y cambiar el dibujo. No deja subirlo a YouTube sin
  marcarlo como revisado: en el primer vídeo la IA cometió una quincena de errores de fechas, cifras y orden.
- **Solo se rehace lo que cambia:** voz, dibujos y clips se guardan por su contenido; corregir una frase rehace solo
  esa escena (unos segundos en vez de minutos).
- **Subida como vídeo normal** (no Short), ya o programada, con la miniatura dibujada, los capítulos en la descripción
  y el comentario con la pregunta para fijar.
- Volumen de los vídeos largos al nivel de YouTube (-14 LUFS).

### Cambiado
- El menú de arriba cabe en cualquier ancho de ventana: en las medianas se oculta el nombre junto al logo y en las
  estrechas quedan solo los iconos (con su nombre al pasar el ratón).

## [1.18.0] - 2026-10-28

### Añadido
- **Apartado «Estadísticas»** en el menú: vistas, «me gusta» y comentarios totales; cuánta gente se queda y cuánto ve
  (media del canal); comparación por tipo de vídeo y por duración; conclusiones automáticas («lo que más vistas da»,
  «el que más retiene», «en N vídeos se ve menos de la mitad»…), y la lista de vídeos con barras, ordenable. Con su
  botón «↻ Actualizar», que trae de YouTube las vistas y la retención al momento.

### Arreglado
- **Retención engañosa en vídeos recientes:** YouTube la da con días de retraso, y un vídeo con 500 vistas podía salir
  con «100 % se queda» por tener datos de una sola. Ahora solo se muestra (y cuenta en las medias) cuando YouTube ya
  tiene datos de 50 vistas o más.

## [1.17.0] - 2026-10-28

Mejoras a partir de las estadísticas de la primera semana: lo que mejor funciona es la actualidad y la historia de
España; las series largas y el final de los vídeos pierden público.

### Cambiado
- **Series de 3 partes como mucho** (antes hasta 10): en las de 4-5 partes cada una tenía menos vistas que la anterior.
- **Cierre más corto:** la toma final dura unos 2,5 s (antes unos 4,5 s), con una frase breve («¿Parte 2? Suscríbete.»)
  y sin el silencio que añadía la voz sintética.
- **Más actualidad española:** el radar de noticias elige la noticia de España antes que una internacional, salvo que
  la internacional sea lo más comentado aquí.
- **Sin rótulos sobre las imágenes:** las noticias ya no llevan «IMÁGENES DE ARCHIVO» encima; la descripción y el texto
  de TikTok e Instagram avisan de que son imágenes de archivo que no muestran los hechos.

## [1.16.1] - 2026-10-27

### Arreglado
- **Instagram, plan B:** si Meta rechaza la subida directa del vídeo (a veces da un error 500 sin motivo), se sube sin
  publicar a la página de Facebook, se crea el Reel desde ahí y se borra de la página. Necesita el permiso
  `pages_manage_posts` en el token (los pasos de Ajustes ya lo incluyen).
- **Reintentos de Instagram más pacientes:** tras un fallo se reintenta a los 10 min, 30 min, 1 h y media, 4 h y 8 h,
  en vez de 3 veces seguidas cada 5 minutos.
- **La tarea de Windows se prepara para la hora del Reel** al activar Instagram (antes solo se despertaba para la
  siguiente subida a YouTube, y con el menú cerrado el Reel se retrasaba), y nunca se queda con una hora ya pasada,
  que no llegaba a saltar.

## [1.16.0] - 2026-10-27

### Añadido
- **Instagram (Reels):** en Ajustes → Instagram se conecta la cuenta profesional. Con «Publicar también en Instagram»,
  cada vídeo programado sale también como Reel a su misma hora, con el texto de TikTok (fuentes, créditos y hashtags).
  Instagram no deja programar: el programa lo publica a la hora, con el ordenador encendido.
- **Retención en Publicados:** junto a las vistas, cuánta gente se queda a ver cada vídeo (frente a la que desliza) y
  qué parte ve de media, la media del canal y el orden «Mejor retención primero». Hay que volver a conectar YouTube una
  vez (pide un permiso nuevo, solo de lectura).
- **Pregunta final y comentario para fijar:** cada guion acaba con una pregunta al espectador, que también va en la
  descripción de YouTube, en el texto de TikTok/Instagram y en la ficha del vídeo, lista para copiarla y fijarla como
  comentario.

### Cambiado
- **Vídeos de 40-45 s** (antes 60-75 s): 5-6 escenas, directos al grano. Los Shorts que se ven enteros son los que
  YouTube reparte.
- **Gancho más exigente:** además de saludos y fechas sueltas, se rechaza empezar presentando al protagonista como una
  enciclopedia («X, figura clave de…»).
- **Series que se entienden solas:** cada parte arranca con su propio gancho y sitúa en media frase de qué va, sin «en
  la parte anterior».
- **Temas que funcionan en el canal:** al elegir efemérides pesan más las de España y el mundo hispano y las de
  deportistas, músicos, actores y científicos.
- **Noticias con Bing y Tavily juntos:** con la clave de Tavily, antes solo se buscaba en Tavily, y salían medios pequeños
  y en inglés. Ahora va primero Bing Noticias (ABC, La Vanguardia, elDiario.es…), Tavily añade lo que falte y, si Bing
  falla, lo sustituye.
- **Clips elegidos por la IA:** un modelo revisa qué clips de vídeo encajan de verdad con cada escena y la época del
  vídeo; los que no, se descartan. Si alguno encaja razonablemente, pone al menos uno: los clips retienen más que las fotos.
- **Ayuda e información al día:** la ayuda de la app (con una sección nueva, «Cómo se hacen para que la gente se
  quede»), Crear, Ajustes, el LEEME, el README, la web y la política de privacidad (permiso de retención e Instagram)
  explican cómo son ahora los vídeos.

## [1.15.0] - 2026-10-27

### Cambiado
- **Los clips de vídeo libres van primero:** antes de elegir las fotos se reservan 1-2 clips por vídeo (los de los
  artículos de Wikipedia y los de Commons que nombran el tema) en las escenas donde mejor encajan. Antes podían
  quedarse fuera aunque fueran del tema, por pesar poco frente a las fotos.
- **También en las noticias:** se buscan clips con licencia libre del propio suceso y de sus lugares (nunca vídeo de
  televisiones o agencias, que tiene derechos), con el rótulo «IMÁGENES DE ARCHIVO» (o «VÍDEO: WIKIMEDIA COMMONS» si
  son de este año), igual que las fotos.

## [1.14.2] - 2026-10-26

### Cambiado
- **El piloto de actualidad no repite tus noticias:** además de las suyas, tiene en cuenta las que hiciste tú desde el menú
  en los últimos 5 días.
- **Carpeta principal más limpia:** todos los scripts de Python están ahora en `scripts/`. Para usarlos a mano desde
  la carpeta principal: `python scripts\paso1_guiones.py …`. El menú, el .exe y las tareas de Windows (publicar
  programados y piloto de actualidad) ya apuntan a la nueva carpeta.

## [1.14.1] - 2026-10-26

### Cambiado
- **Las efemérides se programan siempre en su día.** Antes, si ese día ya tenía sus franjas llenas o su fecha había
  pasado, se programaban como un vídeo normal en otro día. Ahora, con el día lleno van a otra hora de ese mismo día
  (aunque pase del máximo diario), y si su día ya pasó este año, salen en su aniversario del año que viene. También
  vale para las efemérides en inglés.

## [1.14.0] - 2026-10-26

### Añadido
- **Piloto de actualidad** (Ajustes → Piloto de actualidad, desactivado de entrada): a sus horas (09:30, 13:30, 18:00 y
  21:00) busca la noticia de la que más se habla en España, hace el vídeo y lo publica en YouTube al momento, como
  mucho 2 al día. El radar (`radar.py`) junta las tendencias de Google en España y los titulares de Bing Noticias, y
  el modelo elige polémicas de política, sucesos y sociedad que cuentan varios medios, sin repetir lo de los últimos
  5 días. Descarta deportes, famosos, encuestas y crímenes con particulares señalados.
- **Salvaguarda del piloto:** solo publica si la noticia la cuentan al menos 3 medios reconocidos y el verificador no
  marca ninguna frase. Si no, el vídeo queda en Mis vídeos sin revisar y llega un aviso de Windows. El día antes y el
  día de las elecciones de la lista (29-N) no hace política.

### Cambiado
- **Guiones de actualidad con los dos bandos:** si hay polémica, recogen las posturas enfrentadas, cada una atribuida,
  y acaban con una pregunta al espectador para que opine en los comentarios. Las fechas se dan tal y como vienen en
  los artículos (nada de calcular «el sábado 19» a partir de «el sábado»).
- El verificador de noticias sabe la fecha de hoy y ya no marca la fecha del cierre ni la pregunta final.

## [1.13.0] - 2026-10-26

### Añadido
- **Vistas de YouTube por vídeo.** Cada vídeo subido muestra sus vistas y «me gusta» en Mis vídeos y en su página
  (con los comentarios). Se actualizan cada 15 min junto con la sincronización de Programados (1 unidad de cuota por
  cada 50 vídeos) y con «↻ Actualizar». En «Publicados» salen las vistas totales y se puede ordenar por «Más vistos».
- **Planos de ambiente de Pexels** (opcional, con una clave gratuita en Ajustes): cuando ninguna foto encaja bien con
  una escena, puede ir un plano en movimiento de lo que pide (mar, tormenta, fuego, humo, mapas antiguos, ruinas…),
  como mucho 2 por vídeo. Solo cosas que no delatan la época: nunca personas, ciudades ni coches. No se usan en las
  noticias de actualidad ni en los «Diario de…».

### Cambiado
- **La primera frase del guion es siempre el gancho.** Además de pedirlo, ahora se comprueba: si empieza con un
  saludo, «Hoy te voy a contar», «¿Sabías que…?», «Érase una vez», una fecha suelta («En 1936, …») o pasa de 18
  palabras, se pide otro guion diciéndole qué falla. Si tras 3 intentos no sale, se guarda el mejor avisando. No se
  aplica a los «Diario de…», que ya empiezan con su «Día X como…».

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

[1.13.0]: https://github.com/luukthegoat/pipeline-curiosidades/compare/v1.12.1...v1.13.0
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
