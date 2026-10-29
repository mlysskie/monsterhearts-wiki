import hmac
import os
import re
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, Response, abort, flash, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db
import markup

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or "dev-solo-local-cambiame",
    MAX_CONTENT_LENGTH=25 * 1024 * 1024,
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("RAILWAY_ENVIRONMENT") is not None,
)
app.teardown_appcontext(db.close_db)

MASTER_USER = os.environ.get("MASTER_USER", "master")
MASTER_PASSWORD = os.environ.get("MASTER_PASSWORD", "").strip()

# diagnóstico en los logs de Railway: qué variables encontró (sin mostrar valores)
print("[config] base de datos:", "postgres" if db.IS_PG else f"SQLITE TEMPORAL ({db.SQLITE_PATH}) — falta DATABASE_URL",
      flush=True)
for _var in ["DATABASE_URL", "SECRET_KEY", "MASTER_USER", "MASTER_PASSWORD", "INITIAL_ACCESS_CODE"]:
    print(f"[config] {_var}:", "ok" if os.environ.get(_var, "").strip() else "NO CONFIGURADA", flush=True)
_similar = [k for k in os.environ if "MASTER" in k.upper() and k not in ("MASTER_USER", "MASTER_PASSWORD")]
if _similar:
    print("[config] ojo, variables con nombre parecido (¿typo o espacios?):", [repr(k) for k in _similar], flush=True)

# En Railway el disco del contenedor se borra en cada deploy: sin Postgres se perdería todo.
# Mejor no arrancar que guardar datos en un lugar que desaparece.
if os.environ.get("RAILWAY_ENVIRONMENT") and not db.IS_PG and not os.environ.get("ALLOW_SQLITE"):
    raise RuntimeError(
        "DATABASE_URL no está configurada en el servicio web de Railway. Sin ella los datos se "
        "guardarían en un archivo temporal que se borra en cada deploy. Agregá la variable "
        "DATABASE_URL = ${{Postgres.DATABASE_URL}} en el servicio web y volvé a desplegar.")

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
POSTS_PER_PAGE = 6

DEFAULT_SETTINGS = {
    "site_title": "el pueblo duerme",
    "tagline": "— diario de campaña, Monsterhearts 2 —",
    "town_name": "PUEBLO DE HOLLOW PINE",
    "season": "temporada 2003",
    "now_playing": '"Obstacles" — Syd Matters',
    "town_mood": "tensión: alta\nrumor circulando: sí",
    "welcome": "bienvenidx al pueblo. acá no llega bien la señal, así que esta página se actualiza cuando alguien baja al cyber de la estación.",
    "visits": "4217",
    "access_code": "",
    "code_version": "1",
}

# ---------------------------------------------------------------- arranque

_initialized = False


@app.before_request
def ensure_db():
    global _initialized
    if _initialized:
        return
    db.init_db()
    for key, value in DEFAULT_SETTINGS.items():
        if key == "access_code":
            value = os.environ.get("INITIAL_ACCESS_CODE") or new_code()
        if db.query("SELECT 1 FROM settings WHERE key=%s", (key,), one=True) is None:
            db.execute("INSERT INTO settings (key, value) VALUES (%s, %s)", (key, value))
    _initialized = True


def new_code():
    words = ["luna", "pino", "niebla", "lobo", "cuervo", "faro", "musgo", "ceniza", "sombra", "hueso"]
    return f"{secrets.choice(words)}-{secrets.randbelow(9000) + 1000}"


def get_settings():
    rows = db.query("SELECT key, value FROM settings")
    data = dict(DEFAULT_SETTINGS)
    data.update({r["key"]: r["value"] for r in rows})
    return data


def set_setting(key, value):
    if db.query("SELECT 1 FROM settings WHERE key=%s", (key,), one=True):
        db.execute("UPDATE settings SET value=%s WHERE key=%s", (value, key))
    else:
        db.execute("INSERT INTO settings (key, value) VALUES (%s, %s)", (key, value))


# ---------------------------------------------------------------- acceso


def is_master():
    return session.get("master") is True


def has_access():
    if is_master():
        return True
    if not session.get("player"):
        return False
    return session.get("code_version") == get_settings()["code_version"]


def viewer_name():
    return "master" if is_master() else session.get("player", "")


def require_access(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not has_access():
            session.pop("player", None)
            return redirect(url_for("gate", next=request.full_path))
        touch_presence()
        return view(*args, **kwargs)
    return wrapped


def require_master(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_master():
            return redirect(url_for("master_login"))
        return view(*args, **kwargs)
    return wrapped


def touch_presence():
    name = viewer_name()
    if not name:
        return
    db.execute(
        "INSERT INTO presence (name, last_seen) VALUES (%s, %s) "
        "ON CONFLICT (name) DO UPDATE SET last_seen = EXCLUDED.last_seen",
        (name, datetime.utcnow()),
    )


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


@app.before_request
def check_csrf():
    if request.method == "POST":
        sent = request.form.get("csrf", "")
        if not sent or not hmac.compare_digest(sent, session.get("csrf", "")):
            abort(400, "formulario vencido, volvé atrás y recargá la página")


def safe_next(target):
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("index")


# ---------------------------------------------------------------- helpers de plantilla


def image_url(image_id):
    return url_for("image", image_id=image_id)


def character_url_by_name(name):
    return url_for("character", slug=markup.slugify(name))


def bb(text):
    return markup.render(text, image_url=image_url, character_url=character_url_by_name)


def fecha(value, long=False):
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    base = f"{value.day:02d} {MONTHS[value.month - 1].upper()} {value.year}"
    return f"{base} · {value:%H:%M}" if long else base


def as_bool(value):
    return bool(value) and value not in ("0", 0, False)


app.jinja_env.filters.update(bb=bb, fecha=fecha, excerpt=markup.excerpt)
app.jinja_env.globals.update(csrf_token=csrf_token, is_master=is_master,
                             viewer_name=viewer_name, image_url=image_url)


def sidebar_context():
    settings = get_settings()
    chars = db.query(
        "SELECT id, slug, name, skin, is_npc FROM characters WHERE visible=%s "
        "ORDER BY is_npc, sort_order, name",
        (True,),
    )
    cutoff = datetime.utcnow() - timedelta(minutes=10)
    online = [r["name"] for r in db.query(
        "SELECT name FROM presence WHERE last_seen > %s ORDER BY last_seen DESC", (cutoff,))]
    shouts = db.query("SELECT * FROM shouts ORDER BY id DESC LIMIT 12")
    posts = db.query("SELECT created_at FROM posts WHERE published=%s", (True,))
    archive = {}
    for p in posts:
        d = p["created_at"]
        if isinstance(d, str):
            d = datetime.fromisoformat(d)
        archive[(d.year, d.month)] = archive.get((d.year, d.month), 0) + 1
    archive_list = [
        {"year": y, "month": m, "label": f"{MONTHS[m - 1]} {y}", "count": c}
        for (y, m), c in sorted(archive.items(), reverse=True)
    ]
    tags = {}
    for p in db.query("SELECT tags FROM posts WHERE published=%s", (True,)):
        for t in split_tags(p["tags"]):
            tags[t] = tags.get(t, 0) + 1
    return dict(
        settings=settings,
        side_pcs=[c for c in chars if not as_bool(c["is_npc"])],
        side_npcs=[c for c in chars if as_bool(c["is_npc"])],
        online=online,
        shouts=shouts,
        archive=archive_list,
        tag_cloud=sorted(tags.items()),
    )


def page(template, **ctx):
    return render_template(template, **sidebar_context(), **ctx)


def split_tags(raw):
    return [t.strip().lower() for t in (raw or "").split(",") if t.strip()]


app.jinja_env.filters["tags"] = split_tags


# ---------------------------------------------------------------- imágenes

MAGIC = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
]


def sniff_mime(data):
    for sig, mime in MAGIC:
        if data.startswith(sig):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def save_upload(file_storage):
    """Guarda un archivo subido en la base. Devuelve el id o None."""
    if not file_storage or not file_storage.filename:
        return None
    data = file_storage.read()
    if not data:
        return None
    if len(data) > MAX_IMAGE_BYTES:
        flash(f"«{file_storage.filename}» pesa más de 5MB, no entra por el módem.")
        return None
    mime = sniff_mime(data)
    if not mime:
        flash(f"«{file_storage.filename}» no es una imagen (jpg, png, gif o webp).")
        return None
    row = db.execute(
        "INSERT INTO images (mime, filename, data) VALUES (%s, %s, %s) RETURNING id",
        (mime, file_storage.filename[:200], db.blob(data)),
        returning=True,
    )
    return row["id"]


def delete_image(image_id):
    if image_id:
        db.execute("DELETE FROM images WHERE id=%s", (image_id,))


@app.route("/img/<int:image_id>")
def image(image_id):
    if not has_access():
        abort(403)
    row = db.query("SELECT mime, data FROM images WHERE id=%s", (image_id,), one=True)
    if not row:
        abort(404)
    resp = Response(bytes(row["data"]), mimetype=row["mime"])
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp


# ---------------------------------------------------------------- portal de entrada


@app.route("/entrar", methods=["GET", "POST"])
def gate():
    if has_access():
        return redirect(safe_next(request.args.get("next")))
    error = None
    if request.method == "POST":
        code = request.form.get("code", "").strip().lower()
        name = request.form.get("name", "").strip()[:30]
        settings = get_settings()
        if not name:
            error = "poné un apodo, como en el messenger."
        elif name.lower() == "master":
            error = "ese apodo está reservado."
        elif not hmac.compare_digest(code, settings["access_code"].lower()):
            time.sleep(1)
            error = "código incorrecto. preguntale al master."
        else:
            session.clear()
            session.permanent = True
            session["player"] = name
            session["code_version"] = settings["code_version"]
            set_setting("visits", str(int(settings["visits"]) + 1))
            return redirect(safe_next(request.form.get("next")))
    return render_template("gate.html", settings=get_settings(), error=error,
                           next=request.args.get("next", ""))


@app.route("/salir")
def logout():
    session.clear()
    return redirect(url_for("gate"))


# ---------------------------------------------------------------- páginas públicas (con código)


@app.route("/")
@require_access
def index():
    chars = db.query(
        "SELECT * FROM characters WHERE visible=%s AND is_npc=%s ORDER BY sort_order, name",
        (True, False),
    )
    ids = {c["id"] for c in chars}
    links = [s for s in db.query("SELECT from_id, to_id, amount FROM strings WHERE amount > 0")
             if s["from_id"] in ids and s["to_id"] in ids]
    posts = db.query(
        "SELECT * FROM posts WHERE published=%s ORDER BY created_at DESC, id DESC LIMIT 4", (True,))
    return page("index.html", board=chars, links=links, posts=with_comment_counts(posts))


def with_comment_counts(posts):
    out = []
    for p in posts:
        p = dict(p)
        p["n_comments"] = db.query(
            "SELECT COUNT(*) AS n FROM comments WHERE post_id=%s", (p["id"],), one=True)["n"]
        out.append(p)
    return out


@app.route("/elenco")
@require_access
def characters():
    chars = db.query(
        "SELECT * FROM characters WHERE visible=%s OR %s ORDER BY is_npc, sort_order, name",
        (True, is_master()),
    )
    pcs = [c for c in chars if not as_bool(c["is_npc"])]
    npcs = [c for c in chars if as_bool(c["is_npc"])]
    return page("characters.html", pcs=pcs, npcs=npcs)


@app.route("/wiki/<slug>")
@require_access
def character(slug):
    c = db.query("SELECT * FROM characters WHERE slug=%s", (slug,), one=True)
    if not c or (not as_bool(c["visible"]) and not is_master()):
        return page("missing.html", slug=slug), 404
    out_strings = db.query(
        "SELECT s.amount, s.note, c.name, c.slug FROM strings s JOIN characters c ON c.id = s.to_id "
        "WHERE s.from_id=%s AND s.amount > 0 ORDER BY s.amount DESC", (c["id"],))
    in_strings = db.query(
        "SELECT s.amount, s.note, c.name, c.slug FROM strings s JOIN characters c ON c.id = s.from_id "
        "WHERE s.to_id=%s AND s.amount > 0 ORDER BY s.amount DESC", (c["id"],))
    mentions = db.query(
        "SELECT id, title, created_at FROM posts WHERE published=%s AND body LIKE %s "
        "ORDER BY created_at DESC LIMIT 10",
        (True, f"%[[{c['name']}]]%"),
    )
    net_profile = db.query("SELECT handle, display_name FROM net_profiles WHERE character_id=%s",
                           (c["id"],), one=True)
    return page("character.html", c=c, out_strings=out_strings, in_strings=in_strings,
                mentions=mentions, net_profile=net_profile)


@app.route("/lore")
@require_access
def blog():
    pg = max(1, request.args.get("p", 1, type=int))
    tag = request.args.get("tag", "").strip().lower()
    month = request.args.get("mes", "")
    where, params = ["(published=%s OR %s)"], [True, is_master()]
    if tag:
        where.append("LOWER(tags) LIKE %s")
        params.append(f"%{tag}%")
    posts = db.query(f"SELECT * FROM posts WHERE {' AND '.join(where)} "
                     "ORDER BY created_at DESC, id DESC", tuple(params))
    if tag:
        posts = [p for p in posts if tag in split_tags(p["tags"])]
    if month:
        posts = [p for p in posts if fecha_ym(p["created_at"]) == month]
    total_pages = max(1, (len(posts) + POSTS_PER_PAGE - 1) // POSTS_PER_PAGE)
    chunk = posts[(pg - 1) * POSTS_PER_PAGE: pg * POSTS_PER_PAGE]
    return page("blog.html", posts=with_comment_counts(chunk), pg=pg, total_pages=total_pages,
                tag=tag, month=month)


def fecha_ym(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return f"{value.year}-{value.month:02d}"


app.jinja_env.filters["ym"] = fecha_ym


@app.route("/lore/<int:post_id>", methods=["GET", "POST"])
@require_access
def post(post_id):
    p = db.query("SELECT * FROM posts WHERE id=%s", (post_id,), one=True)
    if not p or (not as_bool(p["published"]) and not is_master()):
        abort(404)
    if request.method == "POST":
        body = request.form.get("body", "").strip()[:3000]
        if body:
            db.execute("INSERT INTO comments (post_id, author, is_master, body) VALUES (%s, %s, %s, %s)",
                       (post_id, viewer_name(), is_master(), body))
            flash("comentario dejado. gracias por pasar ^_^")
        return redirect(url_for("post", post_id=post_id) + "#comentarios")
    gallery = db.query(
        "SELECT image_id, caption FROM post_images WHERE post_id=%s ORDER BY image_id", (post_id,))
    used = set(int(x) for x in re.findall(r"\[img:(\d+)", p["body"]))
    gallery = [g_ for g_ in gallery if g_["image_id"] not in used and g_["image_id"] != p["cover_id"]]
    comments = db.query("SELECT * FROM comments WHERE post_id=%s ORDER BY id", (post_id,))
    newer = db.query("SELECT id, title FROM posts WHERE published=%s AND id > %s ORDER BY id LIMIT 1",
                     (True, post_id), one=True)
    older = db.query("SELECT id, title FROM posts WHERE published=%s AND id < %s ORDER BY id DESC LIMIT 1",
                     (True, post_id), one=True)
    return page("post.html", p=p, gallery=gallery, comments=comments, newer=newer, older=older)


@app.route("/shout", methods=["POST"])
@require_access
def shout():
    body = request.form.get("body", "").strip()[:240]
    if body:
        db.execute("INSERT INTO shouts (author, is_master, body) VALUES (%s, %s, %s)",
                   (viewer_name(), is_master(), body))
    return redirect(safe_next(request.form.get("next")))


@app.route("/ayuda")
@require_access
def help_page():
    return page("help.html")


# ---------------------------------------------------------------- master


def master_password_state():
    """Qué contraseña vale para el master.

    Si el master la cambió desde el panel, vale esa (guardada con hash en settings).
    Para recuperarla alcanza con poner un MASTER_PASSWORD distinto en Railway: como
    guardamos con qué MASTER_PASSWORD se hizo el cambio, al detectar uno nuevo vuelve
    a valer la variable de entorno.
    """
    settings = get_settings()
    db_hash = settings.get("master_pw_hash", "")
    env_fp = settings.get("master_env_fp", "")
    env_changed = bool(MASTER_PASSWORD) and not (env_fp and check_password_hash(env_fp, MASTER_PASSWORD))
    if db_hash and not env_changed:
        return "db", db_hash
    return "env", None


def check_master_password(pw):
    mode, db_hash = master_password_state()
    if mode == "db":
        return check_password_hash(db_hash, pw)
    return bool(MASTER_PASSWORD) and hmac.compare_digest(pw, MASTER_PASSWORD)


@app.route("/master/login", methods=["GET", "POST"])
def master_login():
    error = None
    mode, _ = master_password_state()
    if mode == "env" and not MASTER_PASSWORD:
        error = "falta configurar MASTER_PASSWORD en las variables de entorno."
    elif request.method == "POST":
        user = request.form.get("user", "")
        pw = request.form.get("password", "")
        if hmac.compare_digest(user, MASTER_USER) and check_master_password(pw):
            session.clear()
            session.permanent = True
            session["master"] = True
            if mode == "env" and get_settings().get("master_pw_hash"):
                # entró con un MASTER_PASSWORD nuevo de Railway: recuperación
                set_setting("master_pw_hash", "")
                set_setting("master_env_fp", "")
                flash("recuperaste el acceso con la contraseña de Railway. podés elegir una nueva en el panel.")
            return redirect(url_for("master_home"))
        time.sleep(1.5)
        error = "usuario o contraseña incorrectos."
    return render_template("master/login.html", settings=get_settings(), error=error)


@app.route("/master/contrasena", methods=["POST"])
@require_master
def master_change_password():
    current = request.form.get("current", "")
    new = request.form.get("new", "")
    repeat = request.form.get("repeat", "")
    if not check_master_password(current):
        time.sleep(1)
        flash("la contraseña actual no es correcta.")
    elif len(new) < 6:
        flash("la contraseña nueva tiene que tener al menos 6 caracteres.")
    elif new != repeat:
        flash("las dos contraseñas nuevas no coinciden.")
    else:
        set_setting("master_pw_hash", generate_password_hash(new))
        set_setting("master_env_fp", generate_password_hash(MASTER_PASSWORD) if MASTER_PASSWORD else "")
        flash("contraseña del master cambiada. desde ahora entrás con la nueva.")
    return redirect(url_for("master_home") + "#contrasenas")


@app.route("/master/pueblonet-contrasena", methods=["POST"])
@require_master
def master_reset_net_password():
    pid = request.form.get("profile_id", type=int)
    new = request.form.get("new", "")
    p = db.query("SELECT handle FROM net_profiles WHERE id=%s", (pid,), one=True)
    if not p:
        flash("elegí un perfil.")
    elif len(new) < 4:
        flash("la contraseña nueva tiene que tener al menos 4 caracteres.")
    else:
        db.execute("UPDATE net_profiles SET password_hash=%s WHERE id=%s", (generate_password_hash(new), pid))
        flash(f"listo: @{p['handle']} ya puede entrar con la contraseña nueva. pasásela en privado.")
    return redirect(url_for("master_home") + "#contrasenas")


@app.route("/master")
@require_master
def master_home():
    stats = {
        "personajes": db.query("SELECT COUNT(*) AS n FROM characters", one=True)["n"],
        "entradas": db.query("SELECT COUNT(*) AS n FROM posts", one=True)["n"],
        "comentarios": db.query("SELECT COUNT(*) AS n FROM comments", one=True)["n"],
        "imagenes": db.query("SELECT COUNT(*) AS n FROM images", one=True)["n"],
    }
    chars = db.query("SELECT id, slug, name, skin, is_npc, visible FROM characters "
                     "ORDER BY is_npc, sort_order, name")
    posts = db.query("SELECT id, title, published, created_at FROM posts ORDER BY created_at DESC, id DESC")
    comments = db.query("SELECT c.*, p.title FROM comments c JOIN posts p ON p.id = c.post_id "
                        "ORDER BY c.id DESC LIMIT 15")
    net_profiles = db.query("SELECT id, handle, display_name FROM net_profiles ORDER BY display_name")
    return page("master/home.html", stats=stats, chars=chars, all_posts=posts, comments=comments,
                net_profiles=net_profiles, master_pw_mode=master_password_state()[0])


@app.route("/master/ajustes", methods=["POST"])
@require_master
def master_settings():
    for key in ["site_title", "tagline", "town_name", "season", "now_playing", "town_mood", "welcome"]:
        if key in request.form:
            set_setting(key, request.form[key].strip()[:2000])
    flash("ajustes guardados.")
    return redirect(url_for("master_home") + "#ajustes")


@app.route("/master/codigo", methods=["POST"])
@require_master
def master_code():
    code = request.form.get("code", "").strip().lower()[:60] or new_code()
    settings = get_settings()
    set_setting("access_code", code)
    if request.form.get("kick"):
        set_setting("code_version", str(int(settings["code_version"]) + 1))
        flash(f"código nuevo: {code} — todos los jugadores tienen que volver a entrar.")
    else:
        flash(f"código nuevo: {code} — quienes ya estaban adentro siguen adentro.")
    return redirect(url_for("master_home") + "#codigo")


# ---- personajes


CHAR_FIELDS = ["name", "skin", "player", "tagline", "look", "eyes", "origin", "conditions",
               "story", "secrets"]


@app.route("/master/personaje/nuevo", methods=["GET", "POST"])
@app.route("/master/personaje/<int:char_id>", methods=["GET", "POST"])
@require_master
def master_character(char_id=None):
    c = None
    if char_id:
        c = db.query("SELECT * FROM characters WHERE id=%s", (char_id,), one=True)
        if not c:
            abort(404)
    others = db.query("SELECT id, name FROM characters WHERE id <> %s ORDER BY is_npc, name",
                      (char_id or 0,))
    if request.method == "POST":
        data = {f: request.form.get(f, "").strip() for f in CHAR_FIELDS}
        if not data["name"]:
            flash("el personaje necesita un nombre.")
            return redirect(request.url)
        slug = markup.slugify(data["name"])
        clash = db.query("SELECT id FROM characters WHERE slug=%s AND id <> %s",
                         (slug, char_id or 0), one=True)
        if clash:
            flash("ya existe un personaje con ese nombre.")
            return redirect(request.url)
        is_npc = bool(request.form.get("is_npc"))
        visible = bool(request.form.get("visible"))
        sort_order = request.form.get("sort_order", 0, type=int)
        image_id = c["image_id"] if c else None
        new_img = save_upload(request.files.get("image"))
        if new_img or request.form.get("remove_image"):
            old = image_id
            image_id = new_img
            delete_image(old)
        values = [data[f] for f in CHAR_FIELDS] + [slug, image_id, is_npc, visible, sort_order]
        if c:
            db.execute(
                "UPDATE characters SET " + ", ".join(f"{f}=%s" for f in CHAR_FIELDS) +
                ", slug=%s, image_id=%s, is_npc=%s, visible=%s, sort_order=%s, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                tuple(values + [char_id]))
        else:
            row = db.execute(
                "INSERT INTO characters (" + ", ".join(CHAR_FIELDS) +
                ", slug, image_id, is_npc, visible, sort_order) VALUES (" +
                ", ".join(["%s"] * (len(CHAR_FIELDS) + 5)) + ") RETURNING id",
                tuple(values), returning=True)
            char_id = row["id"]
        db.execute("DELETE FROM strings WHERE from_id=%s", (char_id,))
        for o in others:
            amount = request.form.get(f"str_{o['id']}", 0, type=int) or 0
            note = request.form.get(f"note_{o['id']}", "").strip()[:200]
            if amount > 0 or note:
                db.execute("INSERT INTO strings (from_id, to_id, amount, note) VALUES (%s, %s, %s, %s)",
                           (char_id, o["id"], max(0, min(amount, 9)), note))
        flash(f"«{data['name']}» guardado en la wiki.")
        return redirect(url_for("master_character", char_id=char_id))
    strings = {}
    if c:
        strings = {s["to_id"]: s for s in db.query("SELECT * FROM strings WHERE from_id=%s", (char_id,))}
    return page("master/character_form.html", c=c, others=others, strings=strings)


@app.route("/master/personaje/<int:char_id>/borrar", methods=["POST"])
@require_master
def master_character_delete(char_id):
    c = db.query("SELECT name, image_id FROM characters WHERE id=%s", (char_id,), one=True)
    if c:
        db.execute("DELETE FROM characters WHERE id=%s", (char_id,))
        delete_image(c["image_id"])
        flash(f"«{c['name']}» borrado de la wiki.")
    return redirect(url_for("master_home"))


# ---- entradas del blog


@app.route("/master/entrada/nueva", methods=["GET", "POST"])
@app.route("/master/entrada/<int:post_id>", methods=["GET", "POST"])
@require_master
def master_post(post_id=None):
    p = None
    if post_id:
        p = db.query("SELECT * FROM posts WHERE id=%s", (post_id,), one=True)
        if not p:
            abort(404)
    if request.method == "POST":
        title = request.form.get("title", "").strip()[:200]
        if not title:
            flash("la entrada necesita un título.")
            return redirect(request.url)
        fields = (title, request.form.get("body", ""), request.form.get("mood", "").strip()[:120],
                  request.form.get("music", "").strip()[:200], request.form.get("tags", "").strip()[:300],
                  bool(request.form.get("published")))
        cover_id = p["cover_id"] if p else None
        new_cover = save_upload(request.files.get("cover"))
        if new_cover or request.form.get("remove_cover"):
            old = cover_id
            cover_id = new_cover
            delete_image(old)
        created = request.form.get("created_at", "").strip()
        try:
            created_dt = datetime.fromisoformat(created) if created else None
        except ValueError:
            created_dt = None
        if p:
            db.execute("UPDATE posts SET title=%s, body=%s, mood=%s, music=%s, tags=%s, published=%s, "
                       "cover_id=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                       fields + (cover_id, post_id))
        else:
            row = db.execute("INSERT INTO posts (title, body, mood, music, tags, published, cover_id) "
                             "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                             fields + (cover_id,), returning=True)
            post_id = row["id"]
        if created_dt:
            db.execute("UPDATE posts SET created_at=%s WHERE id=%s", (created_dt, post_id))
        for f in request.files.getlist("gallery"):
            img = save_upload(f)
            if img:
                db.execute("INSERT INTO post_images (post_id, image_id) VALUES (%s, %s)", (post_id, img))
        for key, value in request.form.items():
            if key.startswith("cap_"):
                db.execute("UPDATE post_images SET caption=%s WHERE post_id=%s AND image_id=%s",
                           (value.strip()[:200], post_id, int(key[4:])))
        for img in request.form.getlist("del_img"):
            db.execute("DELETE FROM post_images WHERE post_id=%s AND image_id=%s", (post_id, int(img)))
            delete_image(int(img))
        flash("entrada guardada.")
        return redirect(url_for("master_post", post_id=post_id))
    gallery = []
    if p:
        gallery = db.query("SELECT image_id, caption FROM post_images WHERE post_id=%s ORDER BY image_id",
                           (post_id,))
    return page("master/post_form.html", p=p, gallery=gallery)


@app.route("/master/entrada/<int:post_id>/borrar", methods=["POST"])
@require_master
def master_post_delete(post_id):
    p = db.query("SELECT title, cover_id FROM posts WHERE id=%s", (post_id,), one=True)
    if p:
        imgs = [r["image_id"] for r in db.query("SELECT image_id FROM post_images WHERE post_id=%s",
                                                 (post_id,))]
        db.execute("DELETE FROM posts WHERE id=%s", (post_id,))
        for i in imgs + [p["cover_id"]]:
            delete_image(i)
        flash(f"«{p['title']}» borrada.")
    return redirect(url_for("master_home"))


@app.route("/master/comentario/<int:comment_id>/borrar", methods=["POST"])
@require_master
def master_comment_delete(comment_id):
    db.execute("DELETE FROM comments WHERE id=%s", (comment_id,))
    flash("comentario borrado.")
    return redirect(safe_next(request.form.get("next")))


@app.route("/master/shout/<int:shout_id>/borrar", methods=["POST"])
@require_master
def master_shout_delete(shout_id):
    db.execute("DELETE FROM shouts WHERE id=%s", (shout_id,))
    return redirect(safe_next(request.form.get("next")))


# ---------------------------------------------------------------- pueblonet (red social)

import net  # noqa: E402

net.register(app, has_access=has_access, touch_presence=touch_presence, is_master=is_master,
             safe_next=safe_next, image_url=image_url, save_upload=save_upload,
             delete_image=delete_image, get_settings=get_settings, as_bool=as_bool)


# ---------------------------------------------------------------- errores


@app.errorhandler(404)
def not_found(_e):
    if has_access():
        return page("missing.html", slug=None), 404
    return redirect(url_for("gate"))


@app.errorhandler(413)
def too_big(_e):
    return "<h1>413</h1><p>archivo demasiado grande (máx 25MB por envío, 5MB por imagen).</p>", 413


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
