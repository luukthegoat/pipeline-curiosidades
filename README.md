<p align="center"><img src="docs/banner.png" alt="Mente Inquieta" width="720"></p>

# pipeline-curiosidades

**De un tema a un vídeo vertical publicado en YouTube Shorts, con IA y sin inventarse la historia.**

Escribes un tema («La caída de Constantinopla»), una fecha o un personaje, y el programa genera un vídeo de
~1 minuto para Shorts / TikTok / Reels: guion verificado contra Wikipedia, voz, imágenes, subtítulos animados,
música, miniatura, textos para publicar… y lo sube programado a YouTube. Todo se maneja desde un menú web local.

<p align="center"><img src="docs/demo.png" alt="Fotogramas de un vídeo generado" width="900"></p>

## Qué hace

| Paso | Qué ocurre |
|---|---|
| **1 · Guion** | Busca el material en Wikipedia y un LLM (Groq) escribe un guion de 60-75 s en escenas, con gancho, tono musical y nombre corto. Un **segundo LLM verifica cada frase contra la fuente** y marca las que no tienen respaldo. |
| **2 · Voz** | Cada escena se convierte en voz neuronal (edge-tts) con la duración y el tiempo **de cada palabra**. |
| **3 · Vídeo** | Imágenes reales de Wikipedia, Wikimedia Commons, The Met y el Art Institute of Chicago (dominio público), elegidas por relevancia, con zoom lento, subtítulos palabra a palabra, gancho en grande, música que baja sola cuando habla la voz y una toma final animada de «like y suscríbete». |
| **4 · Publicar** | Sube a YouTube por la API oficial (título, descripción, etiquetas, aviso de contenido sintético, publicación programada) y prepara el texto de TikTok. |

**Formatos:** tema libre, **series** de varias partes con índice previo (para que no se repitan ni destripen el final),
**efemérides** («tal día como hoy») y **«Diario de…»**: humor histórico en primera persona con imágenes generadas por IA.

## Decisiones técnicas

Lo interesante del proyecto no es llamar a un LLM, sino todo lo que hace falta alrededor para que el resultado sea
**fiable, barato y publicable**:

- **Que la IA no se invente datos.** El guion solo puede usar hechos del material descargado (*grounding*), y un
  segundo modelo actúa de verificador (*LLM-as-a-judge*) frase a frase. En el formato de humor, el verificador
  distingue los chistes de las afirmaciones históricas. Las dudas se muestran en el menú junto a las fuentes.
- **Revisión humana donde importa.** Solo se publican guiones verificados; si el verificador marca dudas, el vídeo se
  sube en privado. Cada vídeo se declara a YouTube como contenido sintético.
- **Cupos gratuitos de los LLM.** Groq limita los tokens por día *y por modelo*: si el principal se agota, el programa
  pasa a modelos de reserva y apunta hasta cuándo no reintentar, en vez de quedarse esperando.
- **Ser un buen cliente de las APIs.** Un módulo común ([`wikimedia.py`](wikimedia.py)) da a todas las peticiones
  caché en disco, ritmo máximo por servidor (compartido entre procesos), respeto a `Retry-After`/`maxlag` e
  identificación con contacto, como exige Wikimedia. Esto acabó con los bloqueos temporales.
- **Elegir imágenes que encajen.** Puntuación por palabras clave ponderadas por rareza (tipo IDF), penalización de
  imágenes de otra época y umbral mínimo: mejor repetir una imagen buena que poner una irrelevante. Se pueden
  cambiar a mano desde el menú.
- **Rehacer en segundos.** Cada escena es un segmento en caché identificado por una huella de sus entradas; las
  escenas se montan en paralelo y se unen sin recodificar. Un vídeo nuevo tarda ~1 min y rehacerlo tras cambiar una
  imagen, ~8 s (antes, ~3 min).
- **Licencias.** Solo imágenes con licencia libre o de dominio público, con los créditos generados automáticamente;
  música sintetizada por el propio programa (sin derechos de autor).

## Arquitectura

```mermaid
flowchart LR
    A[Tema / fecha / personaje] --> B[paso1_guiones.py<br/>Wikipedia + LLM + verificador]
    B --> C[paso2_audio.py<br/>voz y tiempos por palabra]
    C --> D[paso3_video.py<br/>imágenes, subtítulos, música, cierre]
    D --> E[subir_youtube.py<br/>API de YouTube]
    D --> F[.txt para TikTok]
    W[wikimedia.py<br/>caché y ritmo] -.-> B
    W -.-> D
    M[menu/app.py<br/>menú web + cola de tareas] --> B & C & D & E
```

| Archivo | Función |
|---|---|
| [`paso1_guiones.py`](paso1_guiones.py) | Material de Wikipedia, guion con el LLM, índice de series, verificador, modelos de reserva |
| [`paso2_audio.py`](paso2_audio.py) | Voz por escena con tiempos por palabra; solo regenera las escenas cambiadas |
| [`paso3_video.py`](paso3_video.py) | Selección de imágenes, composición vertical, subtítulos ASS, segmentos en caché, música, miniatura, textos |
| [`cierre.py`](cierre.py) | Animación final de «like y suscríbete» dibujada fotograma a fotograma |
| [`wikimedia.py`](wikimedia.py) | Acceso a Wikipedia, Commons y museos: caché, límites, esperas |
| [`imagenes_ia.py`](imagenes_ia.py) | Imágenes generadas con IA para el formato «Diario de…» |
| [`musica.py`](musica.py) | Pistas de fondo sintetizadas con ffmpeg (épica, misterio, triste, neutra, cómica) |
| [`subir_youtube.py`](subir_youtube.py) | OAuth y subida a YouTube, programación, descripción del canal |
| [`automatico.py`](automatico.py) · [`programador.py`](programador.py) | Piloto automático diario con el Programador de tareas de Windows |
| [`menu/`](menu/) | Menú web (Flask): crear, revisar, elegir imágenes, ajustes, cola de tareas |

## Tecnologías

Python · Groq (gpt-oss-120b / gpt-oss-20b / Qwen) · Wikipedia y Wikimedia API · The Met y Art Institute of Chicago
APIs · edge-tts · ffmpeg (zoompan, subtítulos ASS, sidechain) · Pillow · Flask · YouTube Data API v3 (OAuth 2.0)

## Instalación

Requisitos: Windows y Python 3.11 o superior (ffmpeg viene incluido con `imageio-ffmpeg`).

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # y pon tu clave gratuita de Groq (console.groq.com/keys)
```

Abre el menú con doble clic en `menu\Abrir menu.bat` (o `python menu\app.py`) y sigue la ayuda integrada.
Para subir a YouTube hace falta crear unas credenciales OAuth en Google Cloud: la guía está en
[`menu/LEEME.txt`](menu/LEEME.txt) y en el propio menú (Ajustes → YouTube).

También se puede usar por línea de comandos:

```bash
python paso1_guiones.py --tema "La caída de Constantinopla" --partes 3
python paso2_audio.py
python paso3_video.py
python subir_youtube.py <guion> --privacidad private --publicar-el 2026-10-25T20:00
```

## Limitaciones conocidas

- Las imágenes de IA gratuitas (Pollinations) tienen calidad irregular, marca de agua y límite de 1 imagen / 45 s.
- edge-tts usa un servicio no oficial de Microsoft: para un canal monetizado convendría una voz con licencia comercial.
- YouTube deja en privado lo que sube un proyecto de Google Cloud sin auditar, aunque esté programado.
- El piloto automático usa el Programador de tareas de Windows.
- El verificador reduce mucho los errores, pero no es infalible: los vídeos deben revisarse antes de publicarse.

## Cómo se ha desarrollado

El proyecto se ha construido en *pair programming* con un asistente de IA (Claude Code, de Anthropic): yo definía
qué necesitaba el canal, probaba cada versión, detectaba lo que fallaba en la práctica (datos inventados, bloqueos de
APIs, imágenes que no encajaban, cupos agotados…) y decidía las prioridades; el asistente proponía e implementaba
las soluciones. Ha sido una forma de aprender cómo se lleva un sistema basado en LLM de la demo a algo que funciona
de verdad.

## Licencia

[MIT](LICENSE). Las imágenes que descarga el programa tienen sus propias licencias (se citan en cada vídeo).
