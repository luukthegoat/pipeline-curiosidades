"""Horas recomendadas para publicar cada vídeo, según su tipo.

Son reglas generales para Shorts con público de España (no datos de tu canal). Cuando el canal tenga
estadísticas, conviene ajustarlas con YouTube Studio → Estadísticas → «Cuándo están conectados tus espectadores».

- Efeméride: SIEMPRE el día del aniversario, por la mañana («tal día como hoy» vale todo ese día). Si su día ya
  pasó este año, el del año que viene; si ese día está lleno, se busca otra hora del mismo día (nunca otro día).
- Serie: una parte al día, a la misma hora, para que quien vio la anterior vuelva a por la siguiente.
- Humor («Diario de…»): por la noche, cuando más entretenimiento se consume.
- Tema serio o de misterio: por la noche, con más calma para verlo entero.
- Divulgación general: a mediodía o por la noche, los dos picos de uso del móvil.
- En inglés: a la hora de comer en EE. UU. (tarde en España).
- Actualidad: en la primera franja libre, porque la noticia caduca en uno o dos días.

Además (salvo las efemérides, que mandan en su día): como mucho MAX_AL_DIA vídeos al día, separados al menos SEPARACION_H horas, sin pisar los ya
programados, y nunca antes de dentro de una hora.
"""
import json
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
GUIONES = RAIZ / "salida" / "guiones"
MAX_AL_DIA = 2
SEPARACION_H = 3
DIAS_BUSQUEDA = 45

# Franjas (hora en España): entre semana / fin de semana
FRANJAS = {
    "mañana": ("09:00", "10:30"),
    "mediodía": ("13:30", "12:30"),
    "tarde": ("18:00", "17:30"),
    "noche": ("20:30", "20:00"),
    "EE. UU.": ("19:00", "18:00"),  # 13:00 / 12:00 en Nueva York
}

MOTIVOS = {
    "efemeride": "Efeméride del {fecha}: ese mismo día y temprano, para que «tal día como hoy» valga todo el día.",
    "efemeride_pasada": "Su día ya pasó este año: sale en su aniversario del año que viene ({fecha}).",
    "efemeride_llena": "Efeméride del {fecha}: sus franjas de ese día estaban ocupadas; va a otra hora del mismo día.",
    "serie_1": "Serie: la parte 1 por la noche; las siguientes, una al día a la misma hora.",
    "serie_n": "Serie: un día después de la parte {anterior}, a la misma hora, para que quien la vio vuelva a por esta.",
    "humor": "Humor: mejor por la noche, cuando más entretenimiento se consume.",
    "serio": "Tema serio o de misterio: mejor por la noche, con más calma para verlo entero.",
    "general": "Divulgación: a mediodía o por la noche, los dos picos de uso del móvil en España.",
    "ingles": "En inglés: a la hora de comer en EE. UU. (tarde en España).",
    "actualidad": "Actualidad: cuanto antes, mientras la noticia sigue viva (en un par de días ya no interesa).",
}


def _leer(nombre: str) -> dict:
    return json.loads((GUIONES / f"{nombre}.json").read_text(encoding="utf-8"))


def tipo_de(guion: dict) -> str:
    if guion.get("actualidad"):
        return "actualidad"
    if guion.get("idioma") == "en":
        return "ingles"
    if guion.get("anio_evento"):
        return "efemeride"
    if guion.get("serie"):
        return "serie"
    if guion.get("diario") or guion.get("musica") == "comico":
        return "humor"
    if guion.get("musica") in ("triste", "misterio"):
        return "serio"
    return "general"


PREFERENCIAS = {
    "efemeride": ["mañana", "mediodía", "noche"],
    "serie": ["noche", "tarde"],
    "humor": ["noche", "mediodía"],
    "serio": ["noche", "tarde"],
    "general": ["mediodía", "noche"],
    "ingles": ["EE. UU."],
    "actualidad": ["mediodía", "tarde", "noche", "mañana"],  # la primera franja libre: la noticia caduca
}

DIAS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _hora_franja(dia: date, franja: str) -> datetime:
    texto = FRANJAS[franja][1 if dia.weekday() >= 5 else 0]
    return datetime.combine(dia, datetime.strptime(texto, "%H:%M").time())


def ocupadas(excluir=()) -> list:
    """Horas de publicación ya comprometidas: la cola de programados y lo programado directamente en YouTube.

    `excluir`: guiones que se van a reprogramar (su hora actual no cuenta como ocupada).
    """
    horas = []
    try:
        import programados
        horas += [datetime.strptime(v["hora"][:16], "%Y-%m-%dT%H:%M") for v in programados.leer()["videos"]
                  if v["nombre"] not in excluir]
    except Exception:  # noqa: BLE001 — sin cola, no hay nada ocupado
        pass
    for ruta in GUIONES.glob("*.json"):
        try:
            yt = json.loads(ruta.read_text(encoding="utf-8")).get("youtube") or {}
            if yt.get("publicar_el"):
                horas.append(datetime.strptime(yt["publicar_el"][:16], "%Y-%m-%dT%H:%M"))
        except (OSError, ValueError):
            continue
    return horas


def _partes_conocidas(ocupado_por_serie: dict) -> dict:
    """{tema de la serie: {parte: hora}} de las partes ya programadas o publicadas."""
    try:
        import programados
        cola = {v["nombre"]: v["hora"] for v in programados.leer()["videos"]}
    except Exception:  # noqa: BLE001
        cola = {}
    for ruta in GUIONES.glob("*.json"):
        try:
            guion = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        serie = guion.get("serie")
        if not serie:
            continue
        yt = guion.get("youtube") or {}
        hora = cola.get(ruta.stem) or yt.get("publicar_el") or yt.get("subido")
        if hora:
            clave = (serie["tema"], guion.get("idioma"))
            ocupado_por_serie.setdefault(clave, {})[serie["parte"]] = datetime.fromisoformat(hora[:16])
    return ocupado_por_serie


def recomendar(nombres: list, desde: datetime = None) -> dict:
    """{nombre: {"hora": "AAAA-MM-DDTHH:MM", "bonita", "motivo", "tipo"}} para los guiones dados.

    Se reparten juntos: no se pisan entre sí ni con lo ya programado.
    """
    ahora = desde or datetime.now()
    primera = ahora + timedelta(hours=1)
    usadas = ocupadas(excluir=set(nombres))
    series = _partes_conocidas({})
    guiones = {}
    for nombre in nombres:
        try:
            guiones[nombre] = _leer(nombre)
        except (OSError, ValueError):
            continue

    def libre(hora: datetime) -> bool:
        if hora < primera:
            return False
        mismo_dia = [u for u in usadas if u.date() == hora.date()]
        if len(mismo_dia) >= MAX_AL_DIA:
            return False
        return all(abs((u - hora).total_seconds()) >= SEPARACION_H * 3600 for u in usadas)

    def buscar(desde_dia: date, franjas: list, hora_preferida: datetime = None):
        for desplazamiento in range(DIAS_BUSQUEDA):
            dia = desde_dia + timedelta(days=desplazamiento)
            candidatas = []
            if hora_preferida:  # misma hora que la parte anterior
                candidatas.append(datetime.combine(dia, hora_preferida.time()))
            candidatas += [_hora_franja(dia, f) for f in franjas]
            for hora in candidatas:
                if libre(hora):
                    return hora
        return None

    def es_efemeride(g) -> bool:  # también las de inglés (su tipo es «ingles», pero van atadas a su día igual)
        return bool(g.get("anio_evento")) and bool(g.get("fecha")) and not g.get("actualidad")

    def aniversario(g, anio: int) -> date:
        original = date.fromisoformat(g["fecha"])
        try:
            return original.replace(year=anio)
        except ValueError:  # 29 de febrero en un año que no es bisiesto
            return date(anio, 2, 28)

    def hora_en_su_dia(g, franjas: list) -> tuple:
        """(hora, motivo) en el día de la efeméride: este año si aún llega (hoy incluido); si no, el que viene."""
        dia = aniversario(g, ahora.year)
        if dia < ahora.date() or (dia == ahora.date() and primera.date() != dia):
            dia = aniversario(g, ahora.year + 1)
        fecha_bonita = f"{dia.day} {MESES[dia.month - 1]}" + (f" de {dia.year}" if dia.year != ahora.year else "")
        motivo = MOTIVOS["efemeride_pasada" if dia.year != ahora.year else "efemeride"].format(fecha=fecha_bonita)
        hora = buscar(dia, franjas)
        if hora and hora.date() == dia:
            return hora, motivo
        # Lleno con las reglas normales: otra hora de ese mismo día, aunque se pase del máximo diario.
        candidatas = [_hora_franja(dia, f) for f in franjas + PREFERENCIAS["general"]]
        candidatas += [datetime.combine(dia, datetime.min.time()) + timedelta(hours=h) for h in range(8, 23)]
        validas = [c for c in candidatas if c >= primera]
        if not validas:  # es hoy y ya es tarde: lo antes posible
            return primera.replace(second=0, microsecond=0), motivo
        sin_choque = [c for c in validas if all(abs((u - c).total_seconds()) >= 3600 for u in usadas)]
        return (sin_choque or validas)[0], MOTIVOS["efemeride_llena"].format(fecha=fecha_bonita)

    # Primero las efemérides que aún pueden salir en su día (van atadas a él), luego las series en orden,
    # luego el resto (incluidas las efemérides cuya fecha ya pasó).
    def prioridad(nombre):
        g = guiones[nombre]
        serie = g.get("serie") or {}
        return (0 if es_efemeride(g) else 1 if serie else 2, serie.get("tema", ""), serie.get("parte", 0), nombre)

    resultado = {}
    for nombre in sorted(guiones, key=prioridad):
        g = guiones[nombre]
        tipo = tipo_de(g)
        franjas = PREFERENCIAS[tipo]
        motivo = MOTIVOS[tipo] if tipo in MOTIVOS else ""
        hora = None

        if es_efemeride(g):
            hora, motivo = hora_en_su_dia(g, PREFERENCIAS["ingles"] if tipo == "ingles" else PREFERENCIAS["efemeride"])

        elif g.get("serie"):
            serie = g["serie"]
            clave = (serie["tema"], g.get("idioma"))
            anteriores = {p: h for p, h in series.get(clave, {}).items() if p < serie["parte"]}
            if anteriores:
                parte, previa = max(anteriores.items())
                dias_hasta = serie["parte"] - parte
                # Misma hora que la anterior, si era una hora normal (no una subida a deshoras).
                normal = 8 <= previa.hour + previa.minute / 60 <= 22.5
                hora = buscar((previa + timedelta(days=dias_hasta)).date(), franjas,
                              hora_preferida=previa if normal else None)
                motivo = MOTIVOS["serie_n"].format(anterior=parte)
            else:
                motivo = MOTIVOS["serie_1"] if serie["parte"] == 1 else MOTIVOS["serio"]

        if not hora:
            hora = buscar(primera.date(), franjas)
            ideal = franjas[0]
            if hora and hora != _hora_franja(hora.date(), ideal) and not g.get("serie"):
                motivo += f" La franja ideal ({ideal}) ya está ocupada esos días: va en la siguiente mejor."
        if not hora:
            continue
        usadas.append(hora)
        if g.get("serie"):
            series.setdefault((g["serie"]["tema"], g.get("idioma")), {})[g["serie"]["parte"]] = hora
        resultado[nombre] = {
            "hora": hora.strftime("%Y-%m-%dT%H:%M"),
            "bonita": f"{DIAS[hora.weekday()]} {hora.day} {MESES[hora.month - 1]} · {hora:%H:%M}",
            "motivo": motivo,
            "tipo": tipo,
        }
    return resultado


if __name__ == "__main__":
    import sys
    nombres = sys.argv[1:] or [r.stem for r in GUIONES.glob("*.json")
                               if not json.loads(r.read_text(encoding="utf-8")).get("youtube")]
    for nombre, r in recomendar(nombres).items():
        print(f"{r['bonita']:<20} {nombre[:50]:<50} {r['motivo']}")
