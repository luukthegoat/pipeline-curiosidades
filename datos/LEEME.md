# Datos de los vídeos largos con dibujos

Material fijo que usa `scripts/dibujos.py` para dibujar las escenas de los vídeos largos.

## Fuentes tipográficas (`fuentes/`)

| Archivo | Uso | Licencia |
|---|---|---|
| `PatrickHand-Regular.ttf` | Textos con letra de rotulador | SIL Open Font License 1.1 (`OFL-PatrickHand.txt`) |
| `LilitaOne-Regular.ttf` | Títulos, fechas y cifras grandes | SIL Open Font License 1.1 (`OFL-LilitaOne.txt`) |

Descargadas de [Google Fonts](https://github.com/google/fonts). Se incrustan en cada escena, así que no hace falta
instalarlas en Windows.

## Mapas (`mapas/`)

Contornos simplificados (longitud y latitud) para que pesen poco:

| Archivo | Qué tiene | Origen y licencia |
|---|---|---|
| `espana.json` | Las 52 provincias, con su comunidad autónoma | [click_that_hood](https://github.com/codeforgermany/click_that_hood) (Code for America, licencia MIT) |
| `mundo.json` | Los países del mundo (sin la Antártida) | [Natural Earth](https://www.naturalearthdata.com/) 1:50m, dominio público |

Los mapas muestran fronteras actuales: en un vídeo de historia son una aproximación.

## Iconos

Los objetos de las escenas son dibujos de [Twemoji](https://github.com/jdecked/twemoji) (licencia CC-BY 4.0): se
descargan la primera vez que se usan y se guardan en `salida/twemoji/`. La descripción de cada vídeo lo menciona.
