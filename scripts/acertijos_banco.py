"""Acertijos clásicos ya escritos para vídeo: historia en viñetas, pistas, pregunta y solución.

La IA ya no recuerda más clásicos y, cuando los cuenta ella, se le escapa la solución en la historia; estos están
escritos a mano y comprobados: nada de la narración, los rótulos, las pistas ni los emojis delata la respuesta.
scripts/acertijos.py los usa por orden al azar y solo recurre a la IA cuando ya se han hecho todos.
"""


def _a(titulo, historia, pistas, pregunta, solucion, explicacion, icono):
    return {"titulo": titulo,
            "historia": [{"narracion": n, "iconos": i, "texto": t} for n, i, t in historia],
            "pistas": pistas, "pregunta": pregunta, "solucion": solucion, "explicacion": explicacion,
            "icono": icono}


BANCO = [
    _a("¿Por qué la policía no le multa?", [
        ("Un camionero va en dirección contraria por una calle de un solo sentido, a plena luz del día.",
         ["🚚", "⛔", "🏙️"], "Dirección prohibida"),
        ("Justo en la esquina hay un policía de tráfico que lo ve pasar perfectamente.", ["👮", "👀"],
         "El policía lo ve"),
        ("El policía no toca el silbato, no lo para y no le pone ninguna multa.", ["🚫", "📝"], "Ni multa ni nada")],
       ["Es camionero", "Calle de un solo sentido", "El policía lo ve todo"], "¿Por qué no le multa?",
       "Iba andando",
       "El camionero no iba conduciendo su camión: iba andando por la acera, y caminar en sentido contrario no es "
       "ninguna infracción.", "🚶"),
    _a("¿Quién es el cirujano?", [
        ("Un padre y su hijo tienen un accidente de coche. El padre sale ileso, pero el hijo va al hospital.",
         ["🚗", "🚑", "🏥"], "El accidente"),
        ("Lo llevan al quirófano y llaman a la mayor eminencia del hospital para operarlo.", ["🛏️", "😷"],
         "Al quirófano"),
        ("Al ver al chico, la eminencia dice: «No puedo operarlo. Es mi hijo».", ["😮", "🚫"], "«Es mi hijo»")],
       ["El padre está fuera, ileso", "«Es mi hijo»"], "¿Cómo es posible?", "Es su madre",
       "La eminencia que iba a operar era la madre del chico. Muchos imaginan a un hombre al oír «cirujano» y por eso "
       "no lo ven.", "👩‍⚕️"),
    _a("¿Por qué cenan juntos después?", [
        ("Una mujer apunta a su marido y dispara sin pensárselo dos veces.", ["👩", "🎯", "🧔"], "Dispara"),
        ("Después lo mete cinco minutos bajo el agua y, al sacarlo, lo cuelga.", ["💧", "⏱️", "🪝"],
         "Agua y colgado"),
        ("Esa misma noche cenan juntos tan tranquilos, y él está perfectamente.", ["🍝", "🕯️", "😊"],
         "Cena tranquila")],
       ["Ella dispara", "Cinco minutos bajo el agua", "Él está perfectamente"], "¿Qué ha pasado?", "Es fotógrafa",
       "Le dispara una foto, la revela metiéndola en agua y la cuelga a secar. A él no le ha pasado nada.", "📷"),
    _a("¿Por qué sabe que está arruinado?", [
        ("Un hombre empuja su coche calle abajo hasta llegar a la puerta de un hotel.", ["🚗", "🏨"],
         "Empuja el coche"),
        ("Nada más pararse delante del hotel, se lleva las manos a la cabeza y suspira.", ["🤦"], "Delante del hotel"),
        ("En ese mismo instante sabe que está arruinado, aunque nadie le ha pedido dinero todavía.", ["💸", "😩"],
         "Arruinado")],
       ["Empuja el coche", "Para ante un hotel", "Sabe que está arruinado"], "¿Por qué está arruinado?",
       "Juega al Monopoly",
       "Está jugando al Monopoly: su ficha es el coche, cae en una casilla con hotel y no tiene dinero para pagar.",
       "🎲"),
    _a("¿Cómo se reparten tres peces?", [
        ("Dos madres y dos hijas se van un domingo a pescar al lago.", ["🎣", "🏞️"], "Día de pesca"),
        ("Pasan toda la mañana con la caña y, al final, pescan tres peces.", ["🐟", "🐟", "🐟"], "Tres peces"),
        ("Se reparten la pesca y cada una se lleva un pez entero, sin cortar ninguno.", ["🧺", "👍"],
         "Uno para cada una")],
       ["Dos madres", "Dos hijas", "Tres peces, uno para cada una"], "¿Cómo es posible?", "Solo son tres",
       "Son abuela, madre e hija. La madre es a la vez madre e hija, así que solo son tres personas.", "👵"),
    _a("¿Cómo no se hizo daño?", [
        ("Un hombre está pintando la fachada de su casa subido a una escalera de diez metros.", ["🪜", "🎨", "🏠"],
         "Escalera de 10 m"),
        ("De repente pierde el equilibrio, resbala y se cae de la escalera.", ["😱", "⬇️"], "Se cae"),
        ("Se levanta, se sacude los pantalones y sigue pintando sin un solo rasguño.", ["🧍", "👍"], "Ni un rasguño")],
       ["Escalera de diez metros", "Se cae", "Ni un rasguño"], "¿Cómo no se hizo nada?",
       "Estaba en el primer peldaño",
       "La escalera medía diez metros, pero él estaba en el primer peldaño, a un palmo del suelo.", "🪜"),
    _a("¿Diez días sin dormir?", [
        ("Un hombre pasa diez días seguidos sin dormir ni una sola vez.", ["📅", "🧔"], "10 días"),
        ("Trabaja, sale, hace deporte… y nunca se echa una siesta ni da una cabezada.", ["💼", "🏃"], "Sin siesta"),
        ("Aun así está fresco como una lechuga y ni siquiera tiene ojeras.", ["😃", "✨"], "Ni ojeras")],
       ["Diez días sin dormir", "Ni una siesta", "No está cansado"], "¿Cómo lo consigue?", "Duerme de noche",
       "No duerme durante el día, pero cada noche duerme sus ocho horas. «Diez días sin dormir» no dice nada de las "
       "noches.", "🌙"),
    _a("¿Llega en viernes y se va en viernes?", [
        ("Un vaquero llega al pueblo en viernes, cubierto de polvo tras un largo viaje.", ["🤠", "🏜️"],
         "Llega en viernes"),
        ("Se queda tres días en el pueblo: duerme en la posada y come en la cantina.", ["🏚️", "🍲"], "Tres días"),
        ("Y se marcha del pueblo en viernes, tan tranquilo, sin hacer nada raro.", ["🌅", "👋"], "Se va en viernes")],
       ["Llega en viernes", "Se queda tres días", "Se va en viernes"], "¿Cómo es posible?",
       "Su caballo se llama Viernes",
       "Llega y se va montado en su caballo, que se llama Viernes. Los días de la semana no tienen nada que ver.",
       "🐎"),
    _a("¿Cómo puede cumplir 20?", [
        ("Una chica le dice a su amiga: «Anteayer tenía diecisiete años».", ["👧", "💬"], "Anteayer, 17"),
        ("Y añade muy segura: «Y el año que viene cumpliré veinte».", ["🎂"], "El año que viene, 20"),
        ("Su amiga piensa que se ha liado con las cuentas, pero la chica dice toda la verdad.", ["🤔", "✅"],
         "No miente")],
       ["Anteayer tenía 17", "El año que viene, 20", "No miente"], "¿Qué día lo dice?", "El 1 de enero",
       "Lo dice el 1 de enero y cumple el 31 de diciembre: anteayer tenía 17, ayer cumplió 18, este año 19 y el que "
       "viene 20.", "📅"),
    _a("¿Se afeita 20 veces y tiene barba?", [
        ("Un hombre se afeita más de veinte veces al día, todos los días de la semana.", ["🪒", "🔁"],
         "20 afeitados"),
        ("Usa buena cuchilla, espuma y agua caliente, y nunca se deja ni un pelo.", ["🧴", "💧"], "Bien apurado"),
        ("Sin embargo, todo el mundo le ve siempre con una barba larga y espesa.", ["🧔", "❓"], "Barba larga")],
       ["Se afeita 20 veces al día", "No se deja ni un pelo", "Tiene barba"], "¿Cómo es posible?", "Es barbero",
       "Es barbero: se pasa el día afeitando a sus clientes, no a sí mismo.", "💈"),
    _a("¿Qué compra a este precio?", [
        ("En una ferretería, una mujer pregunta cuánto cuesta una cosa que necesita para su casa.",
         ["🔩", "🏪", "👩"], "En la ferretería"),
        ("El dependiente le contesta: uno cuesta un euro, y doce cuestan dos euros.", ["💶"], "Uno, 1 €; doce, 2 €"),
        ("Y ciento cuarenta y cuatro cuestan tres euros. La mujer paga los tres euros, contenta.", ["💶", "😊"],
         "144, 3 €")],
       ["Uno: 1 €", "Doce: 2 €", "Ciento cuarenta y cuatro: 3 €"], "¿Qué está comprando?",
       "Números para el portal",
       "Compra números para el portal de casa: se paga por cifra. El 1 es una cifra, el 12 son dos y el 144 son tres.",
       "🔢"),
    _a("¿Hacia dónde va el humo?", [
        ("Un tren eléctrico avanza a toda velocidad hacia el norte.", ["🚆", "⬆️"], "Hacia el norte"),
        ("Ese día sopla un viento muy fuerte, justo en dirección contraria, hacia el sur.", ["💨", "⬇️"],
         "Viento al sur"),
        ("Desde el andén, un niño señala el tren y le pregunta a su padre por el humo.", ["🧒", "👉"],
         "Desde el andén")],
       ["Va hacia el norte", "El viento sopla al sur"], "¿Hacia dónde va el humo?", "No hay humo",
       "Es un tren eléctrico: no quema nada, así que no echa humo hacia ningún lado.", "⚡"),
    _a("¿Cómo vio al perro negro?", [
        ("Un coche negro va con las luces apagadas por una carretera sin farolas.", ["🚗", "🛣️"], "Sin luces"),
        ("No hay luna en el cielo y, de pronto, un perro negro cruza la carretera.", ["🐕"], "Un perro negro"),
        ("El conductor lo ve a tiempo, frena y el perro sigue su camino tan tranquilo.", ["🛑", "🐾"],
         "Frena a tiempo")],
       ["Sin luces ni farolas", "No hay luna", "Perro negro"], "¿Cómo lo vio?", "Era de día",
       "Era de día: nadie dijo que fuera de noche. Sin luna y sin farolas, se veía perfectamente con la luz del sol.",
       "☀️"),
    _a("¿Cómo sigue leyendo a oscuras?", [
        ("Un hombre está en el salón de su casa leyendo un libro muy gordo.", ["📖", "🛋️"], "Leyendo"),
        ("De repente se va la luz en todo el edificio y la casa se queda completamente a oscuras.", ["💡", "🌑"],
         "Se va la luz"),
        ("El hombre ni se inmuta: pasa la página y sigue leyendo como si nada.", ["📄", "😌"], "Sigue leyendo")],
       ["Se va la luz", "Todo a oscuras", "Sigue leyendo"], "¿Cómo puede leer?", "Es ciego",
       "Es ciego y lee en braille, con las yemas de los dedos: le da igual que haya luz o no.", "🤚"),
    _a("¿Cómo supo que era falsa?", [
        ("Un arqueólogo excava en unas ruinas y encuentra una moneda antigua enterrada.", ["⛏️", "🏛️", "🪙"],
         "Una moneda"),
        ("La limpia con cuidado y lee la fecha grabada: «año 150 antes de Cristo».", ["🔍", "🪙"], "150 a. C."),
        ("Sin hacer ninguna prueba en el laboratorio, dice muy seguro: «Es falsa».", ["🧑‍🔬", "❌"], "«Es falsa»")],
       ["Moneda antigua", "Fecha: 150 antes de Cristo", "Ninguna prueba"], "¿Cómo lo sabe?", "Por la fecha",
       "Nadie podía saber en aquella época que faltaban 150 años para que naciera Cristo, así que ninguna moneda "
       "auténtica lleva esa fecha.", "📅"),
    _a("¿Dos niños que no son gemelos?", [
        ("Una mujer da a luz a dos niños en el hospital.", ["🏥", "👶", "👶"], "Dos bebés"),
        ("Nacen el mismo día, a la misma hora, y son hijos del mismo padre y de la misma madre.", ["📅", "⏰"],
         "Mismo día y hora"),
        ("Pero cuando la enfermera los apunta en el registro, aclara: «No son gemelos».", ["📋", "❌"],
         "No son gemelos")],
       ["Mismo día y hora", "Misma madre", "No son gemelos"], "¿Qué son?", "Trillizos",
       "Son trillizos: nació un tercer bebé. Los dos niños no son gemelos porque en realidad nacieron tres.", "👶"),
    _a("¿Cómo llega al hueso?", [
        ("Un perro tiene una cuerda de dos metros atada al collar.", ["🐕", "🪢"], "Cuerda de 2 m"),
        ("A cinco metros de él, alguien deja en el suelo un hueso enorme.", ["🦴"], "Hueso a 5 m"),
        ("El perro corre, llega hasta el hueso sin romper la cuerda y se lo come tan feliz.", ["🐕", "💨", "🦴"],
         "Llega")],
       ["Cuerda de dos metros", "Hueso a cinco metros", "No rompe la cuerda"], "¿Cómo llega?",
       "La cuerda no está atada",
       "La cuerda está atada al collar, pero el otro extremo no está atado a nada: el perro la arrastra.", "🪢"),
    _a("¿Cómo vuelve la pelota?", [
        ("Una niña coge una pelota y la lanza con todas sus fuerzas.", ["👧", "⚽"], "La lanza"),
        ("No rebota en ninguna pared, ni en el suelo, ni hay nadie que se la devuelva.", ["🧱", "🚫"],
         "Sin rebotes"),
        ("La pelota se para un instante y vuelve sola a las manos de la niña.", ["🔁", "🙌"], "Vuelve sola")],
       ["Sin rebotes", "Nadie la toca", "Vuelve sola"], "¿Cómo vuelve?", "La lanzó hacia arriba",
       "La lanzó hacia arriba: la pelota sube, se para en lo más alto y la gravedad la devuelve a sus manos.", "⬆️"),
    _a("¿Qué pesa Juan?", [
        ("Juan mide un metro ochenta y calza un cuarenta y cuatro.", ["🧍", "📏", "👟"], "1,80 y un 44"),
        ("Trabaja todas las mañanas en la carnicería del mercado de su barrio.", ["🏪", "🥩"], "Carnicero"),
        ("Un cliente se acerca al mostrador y le pregunta: «Juan, ¿usted qué pesa?».", ["🙋", "❓"], "¿Qué pesa?")],
       ["Mide 1,80", "Calza un 44", "Es carnicero"], "¿Qué pesa Juan?", "Carne",
       "Juan es carnicero: lo que pesa en la báscula todo el día es carne. La pregunta no era cuántos kilos tiene.",
       "🥩"),
    _a("¿Cien personas y ni una sola?", [
        ("Un barco enorme sale del puerto con cien pasajeros a bordo.", ["🛳️", "⚓"], "100 pasajeros"),
        ("Hay gente en la cubierta, en el comedor y en todos los camarotes.", ["👥", "🍽️"], "Lleno"),
        ("Sin embargo, el capitán asegura: «En este barco no hay ni una sola persona».", ["🧑‍✈️", "❗"],
         "«Ni una sola»")],
       ["Cien pasajeros", "Barco lleno", "«Ni una sola persona»"], "¿Cómo puede ser?", "Todos están casados",
       "No hay ninguna persona «sola», es decir, soltera: todos los pasajeros van casados.", "💍"),
    _a("¿Cómo no se le moja el pelo?", [
        ("Un hombre sale a la calle en plena tormenta, con una lluvia tremenda.", ["⛈️", "🚶"], "Tormenta"),
        ("No lleva paraguas, ni gorro, ni capucha, ni se resguarda bajo ningún portal.", ["☂️", "🚫"],
         "Sin paraguas"),
        ("Llega a casa empapado, pero no se le ha mojado ni un pelo de la cabeza.", ["🏠", "💧"],
         "Ni un pelo mojado")],
       ["Sin paraguas", "Empapado", "Ni un pelo mojado"], "¿Por qué?", "Es calvo",
       "Es calvo: no tiene ni un pelo en la cabeza, así que no se le puede mojar ninguno.", "👨‍🦲"),
    _a("¿En qué puesto vas?", [
        ("Estás corriendo una carrera popular y vas muy bien, con fuerza en las piernas.", ["🏃", "🏁"],
         "La carrera"),
        ("En la última recta aprietas y adelantas al corredor que va en segunda posición.", ["💨"],
         "Adelantas al 2.º"),
        ("Tu familia te grita desde la grada para que sigas así hasta la meta.", ["📣", "👨‍👩‍👧"], "¡Sigue!")],
       ["Adelantas al segundo", "Nadie más te adelanta"], "¿En qué puesto vas?", "Segundo",
       "Si adelantas al segundo, ocupas su lugar: vas segundo. Casi todo el mundo responde «primero» sin pensar.",
       "🥈"),
    _a("¿Cuánto te duran las pastillas?", [
        ("Vas al médico porque te duele la cabeza y te receta tres pastillas.", ["🧑‍⚕️", "💊"], "Tres pastillas"),
        ("Te dice: tómate una cada media hora, sin saltarte ninguna.", ["⏰", "💊"], "Cada media hora"),
        ("Sales de la consulta, te tomas la primera y empiezas a contar el tiempo.", ["🚪", "⏱️"], "Empiezas")],
       ["Tres pastillas", "Una cada media hora"], "¿Cuánto te duran?", "Una hora",
       "La primera la tomas al empezar, la segunda a la media hora y la tercera a la hora. Se acaban en una hora, no "
       "en hora y media.", "💊"),
    _a("¿De quién es el retrato?", [
        ("Un hombre está en su casa mirando un retrato colgado en la pared.", ["🖼️", "🧔"], "El retrato"),
        ("Un amigo le pregunta quién es, y él contesta: «Hermanos y hermanas no tengo».", ["💬"], "Sin hermanos"),
        ("«Pero el padre de este hombre es el hijo de mi padre».", ["❓"], "«El hijo de mi padre»")],
       ["No tiene hermanos", "«El hijo de mi padre»"], "¿Quién sale en el retrato?", "Su hijo",
       "Si no tiene hermanos, «el hijo de mi padre» es él mismo. Así que el padre del retrato es él: el del retrato "
       "es su hijo.", "👦"),
    _a("¿Cómo ganan los dos?", [
        ("Dos hombres pasan la tarde entera jugando al ajedrez en el parque.", ["♟️", "🌳"], "Ajedrez"),
        ("Cada uno juega cinco partidas, y en ninguna de ellas hay tablas.", ["🚫"], "5 partidas, sin tablas"),
        ("Al terminar, resulta que cada uno de los dos ha ganado tres partidas.", ["🏆", "🏆"], "Tres cada uno")],
       ["Cinco partidas cada uno", "Sin tablas", "Tres victorias cada uno"], "¿Cómo es posible?",
       "No jugaban entre ellos",
       "No jugaban el uno contra el otro: cada uno jugaba con otros rivales del parque.", "♟️"),
    _a("¿Cuántos hijos tienen?", [
        ("Un matrimonio tiene siete hijas y está muy orgulloso de su gran familia.", ["👨‍👩‍👧", "🏠"],
         "Siete hijas"),
        ("Cada una de las siete hijas tiene un hermano, y todos viven en la misma casa.", ["👦"], "Un hermano"),
        ("En las comidas de los domingos se sientan todos a la mesa con sus padres.", ["🍽️", "❓"],
         "Comida familiar")],
       ["Siete hijas", "Cada una, un hermano"], "¿Cuántos hijos son?", "Ocho",
       "Son siete hijas y un solo hijo: el hermano es el mismo para todas ellas. Ocho, no catorce.", "8️⃣"),
]
