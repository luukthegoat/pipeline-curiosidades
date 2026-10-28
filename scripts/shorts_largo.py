"""Shorts sacados de un vídeo largo: anticipos verticales que llevan al vídeo completo.

La IA elige del guion 3 fragmentos de 25-50 s que se entienden solos y empiezan con gancho. Cada uno se monta en
vertical con lo que ya está hecho (la voz y los dibujos del vídeo largo): el gancho en grande arriba, la escena en
medio, subtítulos grandes debajo y «Vídeo completo en el canal» al pie. Así no cuestan ni voz ni dibujos nuevos.

Uso:
    python scripts/shorts_largo.py salida/largos/guerra-civil-espanola              # hace los Shorts
    python scripts/shorts_largo.py salida/largos/guerra-civil-espanola --subir 0 --privacidad unlisted
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from dotenv import load_dotenv

import dibujos
import paso1_guiones
import video_largo

load_dotenv()

CUANTOS = 3
DURACION = (25, 50)          # s de cada Short (voz incluida la pausa de cada escena)
VIDEO_Y, VIDEO_ALTO = 560, 608   # dónde va la escena (1080 de ancho, 16:9) en el lienzo vertical
SUBTITULOS_Y = 1290
PALABRAS_POR_LINEA = 3

PROMPT_FRAGMENTOS = """Eres editor de un canal de historia en español. Te paso el guion de un vídeo largo: escenas
numeradas, con su capítulo y su duración en segundos. Elige {cuantos} fragmentos para convertirlos en Shorts que lleven
al vídeo completo.

Cada fragmento:
- son escenas SEGUIDAS (de "desde" a "hasta") del mismo capítulo, que en total duren entre {minimo} y {maximo} segundos;
- se entiende solo, sin haber visto lo anterior (nada de «él», «aquello» o «entonces» sin decir quién o qué);
- su PRIMERA frase engancha por sí sola: un dato sorprendente, una contradicción o una pregunta;
- termina con algo que dé ganas de ver el resto.
No repitas escenas entre fragmentos. No elijas la introducción ni la última escena del vídeo.

Responde SOLO con un JSON: {{"fragmentos": [{{"desde": 12, "hasta": 15, "titulo": "título del Short, máx. 60
caracteres, que despierte curiosidad", "gancho": "1 a 4 palabras que se verán en grande arriba"}}]}}"""


def _ffmpeg(argumentos: list) -> None:
    resultado = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                                *map(str, argumentos)], capture_output=True, text=True)
    if resultado.returncode:
        raise RuntimeError(f"ffmpeg: {resultado.stderr[-800:]}")


def _escenas_numeradas(guion: dict) -> list:
    """[(número, capítulo, escena)] de todas las escenas con voz, en orden."""
    lista, numero = [], 0
    for parte in guion["partes"]:
        for escena in parte["escenas"]:
            numero += 1
            lista.append((numero, "Introducción" if parte.get("intro") else parte["titulo"], escena))
    return lista


def _segundos(escena: dict) -> float:
    return escena["duracion"] + video_largo.PAUSA_ESCENA


def elegir_fragmentos(guion: dict) -> list:
    """Los fragmentos que propone la IA, comprobados: escenas seguidas, del mismo capítulo, sin repetir y de buena
    duración. Si alguno no vale, se le piden otros distintos (una vez)."""
    escenas = _escenas_numeradas(guion)
    texto = "\n".join(f"{n}. [{capitulo}] ({_segundos(e):.0f} s) {e['narracion']}" for n, capitulo, e in escenas)
    usados, buenos = set(), []
    por_numero = {n: (capitulo, e) for n, capitulo, e in escenas}
    for intento in range(2):
        falta = CUANTOS - len(buenos)
        if falta <= 0:
            break
        sistema = PROMPT_FRAGMENTOS.format(cuantos=falta, minimo=DURACION[0], maximo=DURACION[1])
        aviso = f"\n\nYa están elegidas las escenas {sorted(usados)}: no las uses." if usados else ""
        respuesta = json.loads(paso1_guiones.llamar_groq(os.getenv("GROQ_API_KEY"), os.getenv("MODELO") or
                                                         paso1_guiones.MODELO_POR_DEFECTO, sistema,
                                                         f"GUION:\n{texto}{aviso}"))
        _validar(respuesta.get("fragmentos", []), por_numero, len(escenas), usados, buenos)
    return buenos[:CUANTOS]


def _validar(propuestos: list, por_numero: dict, total: int, usados: set, buenos: list) -> None:
    """Añade a `buenos` los fragmentos que cumplen las reglas y marca sus escenas como usadas."""
    for f in propuestos:
        try:
            desde, hasta = int(f["desde"]), int(f["hasta"])
        except (KeyError, TypeError, ValueError):
            continue
        numeros = list(range(desde, hasta + 1))
        if (not numeros or any(n not in por_numero for n in numeros) or usados & set(numeros)
                or len({por_numero[n][0] for n in numeros}) > 1 or numeros[-1] == total):
            continue
        while numeros and sum(_segundos(por_numero[n][1]) for n in numeros) > DURACION[1] + 8:
            numeros.pop()  # demasiado largo: se quitan escenas del final
        if not numeros or sum(_segundos(por_numero[n][1]) for n in numeros) < DURACION[0] - 8:
            continue
        usados |= set(numeros)
        buenos.append({"escenas": numeros, "titulo": str(f.get("titulo") or "")[:80],
                       "gancho": str(f.get("gancho") or "")[:40]})


def _cabecera(guion: dict, fragmento: dict) -> list:
    """Capas del lienzo vertical (1080×1920): gancho arriba, hueco para la escena y «vídeo completo» al pie."""
    t = dibujos
    capas = [f'<rect width="1080" height="{VIDEO_Y - 30}" fill="#ffd23f"/>',
             f'<rect width="1080" height="{VIDEO_Y - 30}" fill="url(#grano)"/>']
    lineas = t.partir((fragmento["gancho"] or fragmento["titulo"]).upper(), 12, 2)
    tam = min(150, 980 / (0.58 * max(len(l) for l in lineas)))
    y = 250 - (len(lineas) - 1) * tam * 0.55
    for i, linea in enumerate(lineas):
        capas.append(f'<text x="540" y="{y + i * tam * 1.05:.0f}" font-family="Lilita" font-size="{tam:.0f}" '
                     f'fill="{t.TINTA if i < len(lineas) - 1 else t.COLORES["rojo"]}" stroke="white" stroke-width="18" '
                     f'paint-order="stroke" stroke-linejoin="round" text-anchor="middle" dominant-baseline="middle">'
                     f'{t.esc(linea)}</text>')
    capas.append(t.texto(540, VIDEO_Y - 75, f"Del vídeo «{guion['titulo']}»", 38, 980, max_lineas=1))
    capas.append(f'<rect x="-6" y="{VIDEO_Y - 6}" width="1092" height="{VIDEO_ALTO + 12}" fill="{t.TINTA}"/>')
    capas.append(t.texto(540, 1750, "▶ Vídeo completo", 80, fuente="titulo", relleno=t.COLORES["rojo"]))
    capas.append(t.texto(540, 1840, "en el canal", 60, fuente="titulo"))
    return capas


def _tiempo_ass(segundos: float) -> str:
    h, resto = divmod(max(segundos, 0), 3600)
    m, s = divmod(resto, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _subtitulos(escenas: list, ruta: Path) -> None:
    """Subtítulos grandes (3 palabras por línea) con los tiempos de cada palabra de la voz."""
    lineas, inicio_escena = [], 0.0
    for escena in escenas:
        palabras = escena.get("palabras") or []
        for i in range(0, len(palabras), PALABRAS_POR_LINEA):
            grupo = palabras[i:i + PALABRAS_POR_LINEA]
            texto = " ".join(p[0] for p in grupo).upper().replace("{", "(").replace("}", ")")
            desde = inicio_escena + grupo[0][1]
            hasta = inicio_escena + (palabras[i + PALABRAS_POR_LINEA][1] if i + PALABRAS_POR_LINEA < len(palabras)
                                     else grupo[-1][2] + 0.3)
            lineas.append(f"Dialogue: 0,{_tiempo_ass(desde)},{_tiempo_ass(hasta)},Grande,,0,0,0,,{texto}")
        inicio_escena += _segundos(escena)
    ruta.write_text("\n".join([
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        f"Style: Grande,Lilita One,96,&H00FFFFFF,&H000000FF,&H00212326,&H64000000,0,0,0,0,100,100,1,0,1,9,0,8,50,50,"
        f"{SUBTITULOS_Y},1", "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text", *lineas, ""]),
        encoding="utf-8")


def hacer_shorts(carpeta: Path) -> list:
    """Hace los Shorts del vídeo largo (en su carpeta «shorts/») y los apunta en su guion."""
    ruta_guion = carpeta / "guion.json"
    guion = json.loads(ruta_guion.read_text(encoding="utf-8"))
    escenas = {n: e for n, _, e in _escenas_numeradas(guion)}
    if not all(e.get("imagenes") and e.get("audio") for e in escenas.values()):
        raise ValueError("primero haz el vídeo largo: los Shorts salen de su voz y sus dibujos")
    print("  eligiendo fragmentos…", flush=True)
    fragmentos = elegir_fragmentos(guion)
    if not fragmentos:
        raise RuntimeError("la IA no ha propuesto fragmentos que valgan; prueba otra vez")
    destino = carpeta / "shorts"
    destino.mkdir(exist_ok=True)
    trabajo = destino / "_trabajo"
    trabajo.mkdir(exist_ok=True)
    pista = Path("musica") / f"{guion.get('tono') or 'epico'}.mp3"
    subidos = [s for s in guion.get("shorts") or [] if s.get("youtube")]  # esos no se tocan
    ocupados = {s["archivo"] for s in subidos}
    hechos, numero = [], 1
    for indice, fragmento in enumerate(fragmentos):
        while f"shorts/short_{numero}.mp4" in ocupados:
            numero += 1
        lista = [escenas[n] for n in fragmento["escenas"]]
        print(f"  Short {indice + 1}: escenas {fragmento['escenas'][0]}-{fragmento['escenas'][-1]} · "
              f"«{fragmento['titulo']}»", flush=True)
        clips = [video_largo.clip_de_escena(carpeta, e) for e in lista]
        (trabajo / "lista.txt").write_text("".join(f"file '{c.resolve().as_posix()}'\n" for c in clips), encoding="utf-8")
        _ffmpeg(["-f", "concat", "-safe", "0", "-i", trabajo / "lista.txt", "-c", "copy", trabajo / "trozo.mp4"])
        fondo = trabajo / "fondo.png"
        dibujos.renderizar([(dibujos.documento(_cabecera(guion, fragmento), ancho=1080, alto=1920, vista=(1080, 1920)),
                             fondo, 1080, 1920)])
        _subtitulos(lista, trabajo / "subtitulos.ass")
        duracion = sum(_segundos(e) for e in lista)
        salida = destino / f"short_{numero}.mp4"
        numero += 1
        musica = ["-stream_loop", "-1", "-i", pista] if pista.exists() else []
        mezcla = (f"[1:a]volume=1[v1];[2:a]volume={video_largo.VOLUMEN_MUSICA},afade=t=out:st={max(duracion - 2, 0):.2f}:d=2[m];"
                  f"[v1][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]"
                  if musica else "[1:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")
        # Rutas relativas para el filtro de subtítulos (en Windows las letras de unidad lo confunden)
        relativa = os.path.relpath(trabajo / "subtitulos.ass").replace("\\", "/")
        fuentes = os.path.relpath(dibujos.DATOS / "fuentes").replace("\\", "/")
        _ffmpeg(["-loop", "1", "-framerate", "30", "-i", fondo, "-i", trabajo / "trozo.mp4", *musica,
                 "-filter_complex",
                 f"[1:v]scale=1080:{VIDEO_ALTO}[esc];[0:v][esc]overlay=0:{VIDEO_Y}:shortest=1,"
                 f"subtitles={relativa}:fontsdir={fuentes},format=yuv420p[v];{mezcla}",
                 "-map", "[v]", "-map", "[a]", "-t", f"{duracion:.2f}", "-r", "30", "-c:v", "libx264", "-preset",
                 "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "192k", salida])
        hechos.append({**fragmento, "archivo": f"shorts/{salida.name}", "duracion": round(duracion, 1)})
    guion = json.loads(ruta_guion.read_text(encoding="utf-8"))  # releer por si cambió mientras tanto
    guion["shorts"] = [s for s in guion.get("shorts") or [] if s.get("youtube")] + hechos
    ruta_guion.write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✔ {len(hechos)} Shorts en {destino}", flush=True)
    return hechos


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("carpeta", type=Path, help="carpeta del vídeo largo (salida/largos/…)")
    parser.add_argument("--subir", type=int, help="sube el Short número N (0, 1, 2) a YouTube")
    parser.add_argument("--privacidad", choices=("private", "unlisted", "public"), default="private")
    parser.add_argument("--publicar-el", default="", help="hora local (2026-11-02T18:00): queda privado y se publica solo")
    args = parser.parse_args(argv)
    if args.subir is not None:
        import subir_youtube
        from googleapiclient.errors import HttpError
        try:
            subir_youtube.subir_short_de_largo(args.carpeta, args.subir, args.privacidad, args.publicar_el)
        except HttpError as error:
            print(f"  ⚠ No se ha podido subir: {subir_youtube._explicar(error)}", flush=True)
            return 1
        except ValueError as error:
            print(f"  ⚠ No se ha podido subir: {error}", flush=True)
            return 1
        return 0
    hacer_shorts(args.carpeta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
