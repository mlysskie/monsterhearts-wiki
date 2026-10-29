# el pueblo duerme — sitio de campaña para Monsterhearts 2

Sitio privado con estética de blog/wiki de principios de los 2000 para una campaña de
Monsterhearts ambientada en un pueblo con bosque. Hecho con Flask + PostgreSQL, listo para Railway.

## Qué tiene

- **Entrada privada**: los jugadores entran con un **código de acceso** + un apodo. El master
  cambia el código desde su panel y puede "echar a todos" para que tengan que volver a entrar.
- **Login del master** (`/master/login`) con usuario y contraseña definidos en variables de entorno.
- **Wiki de personajes**: ficha con foto, skin, jugadx, look, ojos, origen, condiciones, historia,
  strings hacia otros personajes y secretos que solo ve el master. Protagonistas y NPCs.
- **Pizarra de corcho**: en el inicio, las polaroids del elenco unidas con hilos rojos según sus strings.
- **Blog de lore**: entradas con portada, galería de fotos, imágenes dentro del texto, etiquetas,
  archivo por mes, "humor actual" y "escuchando", borradores, fechas retroactivas y comentarios.
- **Tagboard** (shoutbox), "en línea ahora", contador de visitas, marquesina y badges 88x31.
- Texto con **BBCode** estilo foro: `[b]`, `[i]`, `[color=red]`, `[quote]`, `[nota]`, `[spoiler]`,
  `[blink]`, `[url=...]`, `[img:12]`, `[[Nombre del personaje]]`… (ver `/ayuda` logueado como master).
- Las imágenes se guardan **en Postgres**, así no se pierden en los redeploys de Railway
  (el disco de Railway es efímero). Máx 5MB por imagen.

## pueblonet (la red social del pueblo)

En `/red` hay una red social estilo SpaceHey/MySpace de 2003, dentro del mismo sitio privado:

- Cada jugador crea su perfil con **usuario y contraseña propios** (distintos del código del sitio)
  y lo puede vincular a su personaje de la wiki.
- El **master** crea perfiles de NPCs (con o sin contraseña) y puede **entrar como cualquier perfil**
  desde el inicio de pueblonet para comentar, postear o seguir como ese NPC. También puede borrar
  cualquier post o comentario.
- Perfil con foto, portada, fondo, estado, humor, edad, signo, escuela, canción, "acerca de mí",
  "a quién me gustaría conocer", intereses, **Top 8**, fotos, contador de vistas y "¡ONLINE!".
- **Posts** con foto y humor, **me gusta** con contador, comentarios, **seguir** con contador de
  seguidores/siguiendo, **feed** de la gente que seguís, **explorar** todo, buscador de gente y
  **actividad** (quién te dio me gusta, te comentó o te empezó a seguir).
- Cada perfil se decora: 7 temas, colores propios, fuente, opacidad de cajas, fondo estirado o en
  mosaico y **CSS propio** (filtrado: no permite scripts ni cargar cosas de afuera).

Las tablas nuevas (`net_*`) se crean solas al arrancar, también en una base que ya existía.

## Deploy en Railway

1. En Railway: **New Project → Deploy from GitHub repo** y elegí este repo.
2. En el mismo proyecto: **New → Database → PostgreSQL**.
3. En el servicio web, pestaña **Variables**, agregá:
   | variable | valor |
   |---|---|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (referencia a la base) |
   | `SECRET_KEY` | una cadena larga al azar |
   | `MASTER_USER` | el usuario del master (por defecto `master`) |
   | `MASTER_PASSWORD` | la contraseña del master |
   | `INITIAL_ACCESS_CODE` | *(opcional)* el primer código para jugadores |
4. En **Settings → Networking**, generá un dominio público.
5. Entrá a `https://tu-dominio/master/login`, y desde el panel copiá el código de acceso para pasárselo a los jugadores.

Las tablas se crean solas en el primer request. Railway usa `railway.json` / `Procfile`
(gunicorn) y detecta Python por `requirements.txt`.

## Correr en local

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
MASTER_PASSWORD=secreto INITIAL_ACCESS_CODE=luna-1996 python app.py
```

Sin `DATABASE_URL` usa un SQLite local (`local.db`) para probar. Con `DATABASE_URL` usa Postgres.

## Estructura

```
app.py          rutas, acceso, panel del master
db.py           conexión y esquema (Postgres en Railway, SQLite en local)
markup.py       BBCode → HTML seguro
templates/      páginas (Jinja)
static/         style.css y site.js (hilos de la pizarra, botonera del editor)
docs/           mockup original de diseño
```
