"""pueblonet: la red social del pueblo, al estilo SpaceHey / MySpace de 2003.

Vive detrás del mismo código de acceso que el resto del sitio. Cada perfil tiene
su propia contraseña; el master puede entrar como cualquier perfil (para manejar
a los NPCs) sin contraseña.
"""
import json
import re
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps
from types import SimpleNamespace

from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db

bp = Blueprint("net", __name__, url_prefix="/red")
H = SimpleNamespace()  # helpers del sitio principal, se cargan en register()

PER_PAGE = 15
HANDLE_RE = re.compile(r"^[a-z0-9_.]{3,20}$")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

THEMES = {
    "clasico": ("clásico azul", dict(page="#e5e5e5", box="#d5e8fb", head="#6699cc", head_text="#ffffff",
                                    text="#1a1a1a", link="#003399", accent="#ff6600", font="verdana")),
    "niebla": ("niebla del bosque", dict(page="#9aa3a8", box="#dfe5e8", head="#5f6f7a", head_text="#ffffff",
                                        text="#222831", link="#24425c", accent="#2f2f2f", font="verdana")),
    "bosque": ("musgo y pino", dict(page="#2f3a26", box="#e3e8d2", head="#55663b", head_text="#f4f1df",
                                   text="#22281a", link="#3d5a1e", accent="#a0522d", font="romantica")),
    "gotico": ("gótico", dict(page="#0d0d0d", box="#1b1b1b", head="#5c0a14", head_text="#f2f2f2",
                             text="#e6e6e6", link="#ff8fa3", accent="#c40f2f", font="gotica")),
    "rosa": ("rosa glitter", dict(page="#ffd6e8", box="#fff0f7", head="#ff69b4", head_text="#ffffff",
                                 text="#4a2040", link="#c2185b", accent="#9c27b0", font="comic")),
    "papel": ("cuaderno", dict(page="#d8cfb6", box="#fbf8ee", head="#8a8461", head_text="#f4eedd",
                              text="#3b3725", link="#4e5a2a", accent="#b8412f", font="maquina")),
    "noche": ("medianoche", dict(page="#0b1630", box="#14254a", head="#2b4c8c", head_text="#ffffff",
                                text="#dfe8ff", link="#9ec5ff", accent="#ffd54f", font="pixel")),
}

FONTS = {
    "verdana": ("Verdana", "Verdana, Tahoma, sans-serif", None),
    "times": ("Times", "'Times New Roman', Times, serif", None),
    "comic": ("Comic Sans", "'Comic Sans MS', 'Chalkboard SE', cursive", None),
    "courier": ("Courier", "'Courier New', monospace", None),
    "gotica": ("gótica", "'UnifrakturMaguntia', serif", "UnifrakturMaguntia"),
    "manuscrita": ("manuscrita", "'Reenie Beanie', cursive", "Reenie+Beanie"),
    "pixel": ("pixel", "'Silkscreen', monospace", "Silkscreen"),
    "maquina": ("máquina de escribir", "'Special Elite', monospace", "Special+Elite"),
    "romantica": ("antigua", "'IM Fell English', serif", "IM+Fell+English:ital@0;1"),
}

DECORATIVE = {"gotica", "manuscrita", "pixel"}

PROFILE_FIELDS = ["display_name", "status_text", "mood", "headline", "age", "zodiac", "school",
                  "about_me", "want_to_meet", "int_general", "int_music", "int_movies", "int_tv",
                  "int_books", "int_heroes", "song"]


def register(app, **helpers):
    H.__dict__.update(helpers)
    app.register_blueprint(bp)
    app.jinja_env.globals.update(net_me=current_profile, net_avatar=avatar_url)


# ---------------------------------------------------------------- sesión y permisos


def current_profile():
    if "net_me" not in g:
        pid = session.get("net_pid")
        g.net_me = db.query("SELECT * FROM net_profiles WHERE id=%s", (pid,), one=True) if pid else None
        if pid and not g.net_me:
            session.pop("net_pid", None)
    return g.net_me


def need_access(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not H.has_access():
            return redirect(url_for("gate", next=request.full_path))
        H.touch_presence()
        me = current_profile()
        if me:
            db.execute("UPDATE net_profiles SET last_seen=%s WHERE id=%s", (datetime.utcnow(), me["id"]))
        return view(*args, **kwargs)
    return wrapped


def need_profile(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_profile():
            flash("primero entrá a tu perfil de pueblonet.")
            return redirect(url_for("net.home"))
        return view(*args, **kwargs)
    return wrapped


def can_edit(profile):
    me = current_profile()
    return H.is_master() or (me is not None and me["id"] == profile["id"])


def back(default):
    return redirect(H.safe_next(request.form.get("next") or default))


# ---------------------------------------------------------------- helpers


def avatar_url(profile_or_id):
    image_id = profile_or_id.get("avatar_id") if isinstance(profile_or_id, dict) else profile_or_id
    return H.image_url(image_id) if image_id else None


def is_online(profile):
    seen = profile.get("last_seen")
    if not seen:
        return False
    if isinstance(seen, str):
        seen = datetime.fromisoformat(seen)
    return seen > datetime.utcnow() - timedelta(minutes=10)


def get_profile(handle):
    p = db.query("SELECT * FROM net_profiles WHERE handle=%s", (handle.lower(),), one=True)
    if not p:
        abort(404)
    return p


def count(sql, params):
    return db.query(sql, params, one=True)["n"]


def profile_stats(pid):
    return dict(
        followers=count("SELECT COUNT(*) AS n FROM net_follows WHERE followee_id=%s", (pid,)),
        following=count("SELECT COUNT(*) AS n FROM net_follows WHERE follower_id=%s", (pid,)),
        posts=count("SELECT COUNT(*) AS n FROM net_posts WHERE profile_id=%s", (pid,)),
        likes=count("SELECT COUNT(*) AS n FROM net_likes l JOIN net_posts p ON p.id=l.post_id "
                    "WHERE p.profile_id=%s", (pid,)),
    )


POST_SELECT = (
    "SELECT p.*, pr.handle, pr.display_name, pr.avatar_id, pr.last_seen, "
    "(SELECT COUNT(*) FROM net_likes l WHERE l.post_id=p.id) AS likes, "
    "(SELECT COUNT(*) FROM net_comments c WHERE c.post_id=p.id) AS ncomments, "
    "(SELECT COUNT(*) FROM net_likes l2 WHERE l2.post_id=p.id AND l2.profile_id=%s) AS liked "
    "FROM net_posts p JOIN net_profiles pr ON pr.id=p.profile_id "
)


def fetch_posts(where="", params=(), limit=PER_PAGE, offset=0, with_comments=3):
    me = current_profile()
    posts = db.query(POST_SELECT + where + " ORDER BY p.created_at DESC, p.id DESC LIMIT %s OFFSET %s",
                     (me["id"] if me else 0,) + tuple(params) + (limit, offset))
    posts = [dict(p) for p in posts]
    if with_comments and posts:
        ids = [p["id"] for p in posts]
        marks = ",".join(["%s"] * len(ids))
        rows = db.query(
            "SELECT c.*, pr.handle, pr.display_name, pr.avatar_id FROM net_comments c "
            f"JOIN net_profiles pr ON pr.id=c.author_id WHERE c.post_id IN ({marks}) ORDER BY c.id",
            tuple(ids))
        by_post = {}
        for r in rows:
            by_post.setdefault(r["post_id"], []).append(r)
        for p in posts:
            p["comments"] = by_post.get(p["id"], [])[-with_comments:]
    return posts


def resolve_style(p):
    """Une el tema elegido con los colores/fuente personalizados del perfil."""
    base = dict(THEMES.get(p["theme"], THEMES["clasico"])[1])
    try:
        custom = json.loads(p["style_json"] or "{}")
    except ValueError:
        custom = {}
    for key in ["page", "box", "head", "head_text", "text", "link", "accent"]:
        if HEX_RE.match(custom.get(key, "")):
            base[key] = custom[key]
    if custom.get("font") in FONTS:
        base["font"] = custom["font"]
    base["bg_mode"] = custom.get("bg_mode") if custom.get("bg_mode") in ("tile", "cover") else "cover"
    try:
        base["box_alpha"] = max(40, min(100, int(custom.get("box_alpha", 100))))
    except (TypeError, ValueError):
        base["box_alpha"] = 100
    base["font_label"], base["font_stack"], base["font_google"] = FONTS[base["font"]]
    # las fuentes decorativas van solo en títulos; el texto corrido queda legible
    base["body_stack"] = "Verdana, Tahoma, sans-serif" if base["font"] in DECORATIVE else base["font_stack"]
    base["custom"] = custom
    return base


def clean_css(css):
    """CSS propio estilo MySpace, pero sin nada que pueda escaparse de la hoja de estilos."""
    css = (css or "")[:8000]
    css = css.replace("\\", "")
    css = re.sub(r"<[^>]*>?", "", css)
    css = re.sub(r"@import[^;]*;?|@charset[^;]*;?", "", css, flags=re.IGNORECASE)
    css = re.sub(r"expression\s*\(|behavior\s*:|-moz-binding|javascript:", "", css, flags=re.IGNORECASE)

    def safe_url(m):
        inner = m.group(1).strip("'\" ")
        return f"url('{inner}')" if re.fullmatch(r"/img/\d+", inner) else "none"

    return re.sub(r"url\(([^)]*)\)", safe_url, css, flags=re.IGNORECASE)


def top_friends(p, limit=8):
    ids = [int(x) for x in (p["top_friends"] or "").split(",") if x.strip().isdigit()][:limit]
    found = []
    for i in ids:
        r = db.query("SELECT id, handle, display_name, avatar_id, last_seen FROM net_profiles WHERE id=%s",
                     (i,), one=True)
        if r:
            found.append(r)
    if not found:  # sin top elegido: los primeros seguidores
        found = db.query(
            "SELECT pr.id, pr.handle, pr.display_name, pr.avatar_id, pr.last_seen FROM net_follows f "
            "JOIN net_profiles pr ON pr.id=f.follower_id WHERE f.followee_id=%s "
            "ORDER BY f.created_at LIMIT %s", (p["id"], limit))
    return found


def activity(me, limit=20):
    pid = me["id"]
    events = []
    for r in db.query(
            "SELECT l.created_at, pr.handle, pr.display_name, l.post_id FROM net_likes l "
            "JOIN net_posts p ON p.id=l.post_id JOIN net_profiles pr ON pr.id=l.profile_id "
            "WHERE p.profile_id=%s AND l.profile_id<>%s ORDER BY l.created_at DESC LIMIT %s",
            (pid, pid, limit)):
        events.append(dict(r, kind="like"))
    for r in db.query(
            "SELECT c.created_at, pr.handle, pr.display_name, c.post_id, c.body FROM net_comments c "
            "JOIN net_posts p ON p.id=c.post_id JOIN net_profiles pr ON pr.id=c.author_id "
            "WHERE p.profile_id=%s AND c.author_id<>%s ORDER BY c.created_at DESC LIMIT %s",
            (pid, pid, limit)):
        events.append(dict(r, kind="comment"))
    for r in db.query(
            "SELECT c.created_at, pr.handle, pr.display_name, c.body FROM net_comments c "
            "JOIN net_profiles pr ON pr.id=c.author_id "
            "WHERE c.wall_id=%s AND c.author_id<>%s ORDER BY c.created_at DESC LIMIT %s",
            (pid, pid, limit)):
        events.append(dict(r, kind="wall"))
    for r in db.query(
            "SELECT f.created_at, pr.handle, pr.display_name FROM net_follows f "
            "JOIN net_profiles pr ON pr.id=f.follower_id WHERE f.followee_id=%s "
            "ORDER BY f.created_at DESC LIMIT %s", (pid, limit)):
        events.append(dict(r, kind="follow"))

    def key(e):
        d = e["created_at"]
        return datetime.fromisoformat(d) if isinstance(d, str) else d

    return sorted(events, key=key, reverse=True)[:limit]


def render(template, **ctx):
    ctx.setdefault("is_online", is_online)
    return render_template(template, settings=H.get_settings(), **ctx)


# ---------------------------------------------------------------- inicio, entrar, registrarse


@bp.route("/")
@need_access
def home():
    me = current_profile()
    ctx = {}
    if me:
        ctx["stats"] = profile_stats(me["id"])
        ctx["events"] = activity(me)
        ctx["posts"] = fetch_posts(
            "WHERE p.profile_id=%s OR p.profile_id IN (SELECT followee_id FROM net_follows WHERE follower_id=%s)",
            (me["id"], me["id"]), limit=10)
    else:
        ctx["posts"] = fetch_posts(limit=6)
    ctx["newest"] = db.query("SELECT * FROM net_profiles ORDER BY id DESC LIMIT 8")
    if H.is_master():
        ctx["all_profiles"] = db.query("SELECT id, handle, display_name, is_npc FROM net_profiles "
                                       "ORDER BY is_npc DESC, display_name")
    return render("net/home.html", **ctx)


@bp.route("/entrar", methods=["POST"])
@need_access
def login():
    handle = request.form.get("handle", "").strip().lower().lstrip("@")
    pw = request.form.get("password", "")
    p = db.query("SELECT * FROM net_profiles WHERE handle=%s", (handle,), one=True)
    if not p or not p["password_hash"] or not check_password_hash(p["password_hash"], pw):
        flash("usuario o contraseña de pueblonet incorrectos.")
        return redirect(url_for("net.home"))
    session["net_pid"] = p["id"]
    flash(f"hola de nuevo, {p['display_name']} :)")
    return redirect(url_for("net.home"))


@bp.route("/entrar-como/<int:pid>", methods=["POST"])
@need_access
def login_as(pid):
    if not H.is_master():
        abort(403)
    p = db.query("SELECT id, display_name FROM net_profiles WHERE id=%s", (pid,), one=True)
    if p:
        session["net_pid"] = p["id"]
        flash(f"ahora estás usando el perfil de {p['display_name']}.")
    return back(url_for("net.home"))


@bp.route("/salir")
def logout():
    session.pop("net_pid", None)
    return redirect(url_for("net.home"))


@bp.route("/registro", methods=["GET", "POST"])
@need_access
def signup():
    chars = db.query(
        "SELECT c.id, c.name, c.is_npc FROM characters c WHERE c.visible=%s OR %s "
        "ORDER BY c.is_npc, c.name", (True, H.is_master()))
    taken = {r["character_id"] for r in db.query("SELECT character_id FROM net_profiles "
                                                 "WHERE character_id IS NOT NULL")}
    chars = [c for c in chars if c["id"] not in taken]
    if request.method == "POST":
        handle = request.form.get("handle", "").strip().lower().lstrip("@")
        name = request.form.get("display_name", "").strip()[:60]
        pw = request.form.get("password", "")
        char_id = request.form.get("character_id", type=int)
        error = None
        if not HANDLE_RE.match(handle):
            error = "el usuario tiene que tener 3 a 20 caracteres: letras minúsculas, números, _ o ."
        elif db.query("SELECT 1 FROM net_profiles WHERE handle=%s", (handle,), one=True):
            error = "ese usuario ya existe."
        elif not name:
            error = "poné un nombre para mostrar."
        elif len(pw) < 4 and not H.is_master():
            error = "la contraseña tiene que tener al menos 4 caracteres."
        elif char_id and char_id not in {c["id"] for c in chars}:
            error = "ese personaje ya tiene perfil."
        if error:
            flash(error)
            return render("net/signup.html", chars=chars, form=request.form)
        is_npc = H.is_master() and bool(request.form.get("is_npc"))
        code = new_recovery_code()
        row = db.execute(
            "INSERT INTO net_profiles (handle, display_name, password_hash, recovery_hash, character_id, "
            "is_npc, theme) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (handle, name, generate_password_hash(pw) if pw else None, generate_password_hash(code),
             char_id or None, is_npc, "niebla" if is_npc else "clasico"),
            returning=True)
        session["net_pid"] = row["id"]
        session["net_new_code"] = code
        return redirect(url_for("net.show_code", siguiente="editar"))
    return render("net/signup.html", chars=chars, form={})


# ---------------------------------------------------------------- gente, feed, explorar


@bp.route("/gente")
@need_access
def people():
    q = request.args.get("q", "").strip().lower()
    rows = db.query("SELECT * FROM net_profiles ORDER BY last_seen DESC, id DESC")
    if q:
        rows = [r for r in rows if q in r["handle"] or q in r["display_name"].lower()]
    people_ = []
    for r in rows:
        r = dict(r)
        r["followers"] = count("SELECT COUNT(*) AS n FROM net_follows WHERE followee_id=%s", (r["id"],))
        people_.append(r)
    return render("net/people.html", people=people_, q=q)


@bp.route("/feed")
@need_access
@need_profile
def feed():
    me = current_profile()
    pg = max(1, request.args.get("p", 1, type=int))
    posts = fetch_posts(
        "WHERE p.profile_id=%s OR p.profile_id IN (SELECT followee_id FROM net_follows WHERE follower_id=%s)",
        (me["id"], me["id"]), limit=PER_PAGE + 1, offset=(pg - 1) * PER_PAGE)
    return render("net/feed.html", posts=posts[:PER_PAGE], more=len(posts) > PER_PAGE, pg=pg, mode="feed")


@bp.route("/explorar")
@need_access
def explore():
    pg = max(1, request.args.get("p", 1, type=int))
    posts = fetch_posts(limit=PER_PAGE + 1, offset=(pg - 1) * PER_PAGE)
    return render("net/feed.html", posts=posts[:PER_PAGE], more=len(posts) > PER_PAGE, pg=pg, mode="explorar")


# ---------------------------------------------------------------- posts


@bp.route("/publicar", methods=["POST"])
@need_access
@need_profile
def new_post():
    me = current_profile()
    body = request.form.get("body", "").strip()[:4000]
    mood = request.form.get("mood", "").strip()[:80]
    image_id = H.save_upload(request.files.get("image"))
    if not body and not image_id:
        flash("el post está vacío.")
    else:
        db.execute("INSERT INTO net_posts (profile_id, body, mood, image_id) VALUES (%s, %s, %s, %s)",
                   (me["id"], body, mood, image_id))
        flash("publicado ♥")
    return back(url_for("net.home"))


@bp.route("/post/<int:post_id>")
@need_access
def post(post_id):
    rows = fetch_posts("WHERE p.id=%s", (post_id,), limit=1, with_comments=1000)
    if not rows:
        abort(404)
    likers = db.query("SELECT pr.handle, pr.display_name FROM net_likes l JOIN net_profiles pr "
                      "ON pr.id=l.profile_id WHERE l.post_id=%s ORDER BY l.created_at", (post_id,))
    return render("net/post.html", p=rows[0], likers=likers)


@bp.route("/post/<int:post_id>/like", methods=["POST"])
@need_access
@need_profile
def like(post_id):
    me = current_profile()
    if not db.query("SELECT 1 FROM net_posts WHERE id=%s", (post_id,), one=True):
        abort(404)
    if db.query("SELECT 1 FROM net_likes WHERE post_id=%s AND profile_id=%s", (post_id, me["id"]), one=True):
        db.execute("DELETE FROM net_likes WHERE post_id=%s AND profile_id=%s", (post_id, me["id"]))
    else:
        db.execute("INSERT INTO net_likes (post_id, profile_id) VALUES (%s, %s)", (post_id, me["id"]))
    return back(url_for("net.post", post_id=post_id))


@bp.route("/post/<int:post_id>/comentar", methods=["POST"])
@need_access
@need_profile
def comment_post(post_id):
    body = request.form.get("body", "").strip()[:2000]
    if not db.query("SELECT 1 FROM net_posts WHERE id=%s", (post_id,), one=True):
        abort(404)
    if body:
        db.execute("INSERT INTO net_comments (post_id, author_id, body) VALUES (%s, %s, %s)",
                   (post_id, current_profile()["id"], body))
    return back(url_for("net.post", post_id=post_id))


@bp.route("/post/<int:post_id>/borrar", methods=["POST"])
@need_access
def delete_post(post_id):
    p = db.query("SELECT p.*, pr.handle FROM net_posts p JOIN net_profiles pr ON pr.id=p.profile_id "
                 "WHERE p.id=%s", (post_id,), one=True)
    if not p:
        abort(404)
    if not can_edit({"id": p["profile_id"]}):
        abort(403)
    db.execute("DELETE FROM net_posts WHERE id=%s", (post_id,))
    H.delete_image(p["image_id"])
    flash("post borrado.")
    return back(url_for("net.profile", handle=p["handle"]))


@bp.route("/comentario/<int:comment_id>/borrar", methods=["POST"])
@need_access
def delete_comment(comment_id):
    c = db.query("SELECT c.*, p.profile_id AS post_owner FROM net_comments c "
                 "LEFT JOIN net_posts p ON p.id=c.post_id WHERE c.id=%s", (comment_id,), one=True)
    if not c:
        abort(404)
    me = current_profile()
    mine = me is not None and me["id"] in (c["author_id"], c["wall_id"], c["post_owner"])
    if not (H.is_master() or mine):
        abort(403)
    db.execute("DELETE FROM net_comments WHERE id=%s", (comment_id,))
    return back(url_for("net.home"))


# ---------------------------------------------------------------- perfiles


@bp.route("/u/<handle>")
@need_access
def profile(handle):
    p = get_profile(handle)
    me = current_profile()
    viewed = session.get("net_viewed", [])
    if (not me or me["id"] != p["id"]) and p["id"] not in viewed:
        db.execute("UPDATE net_profiles SET views = views + 1 WHERE id=%s", (p["id"],))
        session["net_viewed"] = (viewed + [p["id"]])[-200:]
        p = dict(p, views=p["views"] + 1)
    following = bool(me and db.query("SELECT 1 FROM net_follows WHERE follower_id=%s AND followee_id=%s",
                                     (me["id"], p["id"]), one=True))
    follows_me = bool(me and db.query("SELECT 1 FROM net_follows WHERE follower_id=%s AND followee_id=%s",
                                      (p["id"], me["id"]), one=True))
    wall = db.query("SELECT c.*, pr.handle, pr.display_name, pr.avatar_id FROM net_comments c "
                    "JOIN net_profiles pr ON pr.id=c.author_id WHERE c.wall_id=%s ORDER BY c.id DESC LIMIT 50",
                    (p["id"],))
    character = None
    if p["character_id"]:
        character = db.query("SELECT name, slug, visible FROM characters WHERE id=%s", (p["character_id"],), one=True)
        if character and not H.as_bool(character["visible"]) and not H.is_master():
            character = None
    photos = db.query("SELECT id, image_id FROM net_posts WHERE profile_id=%s AND image_id IS NOT NULL "
                      "ORDER BY id DESC LIMIT 9", (p["id"],))
    return render("net/profile.html", p=p, style=resolve_style(p), css=clean_css(p["custom_css"]),
                  stats=profile_stats(p["id"]), following=following, follows_me=follows_me,
                  posts=fetch_posts("WHERE p.profile_id=%s", (p["id"],), limit=5),
                  wall=wall, top=top_friends(p), character=character, photos=photos,
                  can_edit=can_edit(p), online=is_online(p))


@bp.route("/u/<handle>/posts")
@need_access
def profile_posts(handle):
    p = get_profile(handle)
    pg = max(1, request.args.get("p", 1, type=int))
    posts = fetch_posts("WHERE p.profile_id=%s", (p["id"],), limit=PER_PAGE + 1, offset=(pg - 1) * PER_PAGE)
    return render("net/feed.html", posts=posts[:PER_PAGE], more=len(posts) > PER_PAGE, pg=pg,
                  mode="perfil", owner=p)


@bp.route("/u/<handle>/seguidores")
@need_access
def followers(handle):
    p = get_profile(handle)
    which = request.args.get("ver", "seguidores")
    if which == "siguiendo":
        rows = db.query("SELECT pr.* FROM net_follows f JOIN net_profiles pr ON pr.id=f.followee_id "
                        "WHERE f.follower_id=%s ORDER BY f.created_at DESC", (p["id"],))
    else:
        rows = db.query("SELECT pr.* FROM net_follows f JOIN net_profiles pr ON pr.id=f.follower_id "
                        "WHERE f.followee_id=%s ORDER BY f.created_at DESC", (p["id"],))
    return render("net/people.html", people=rows, q="", owner=p, which=which)


@bp.route("/u/<handle>/seguir", methods=["POST"])
@need_access
@need_profile
def follow(handle):
    p = get_profile(handle)
    me = current_profile()
    if p["id"] != me["id"]:
        if db.query("SELECT 1 FROM net_follows WHERE follower_id=%s AND followee_id=%s",
                    (me["id"], p["id"]), one=True):
            db.execute("DELETE FROM net_follows WHERE follower_id=%s AND followee_id=%s", (me["id"], p["id"]))
        else:
            db.execute("INSERT INTO net_follows (follower_id, followee_id) VALUES (%s, %s)", (me["id"], p["id"]))
    return back(url_for("net.profile", handle=handle))


@bp.route("/u/<handle>/comentar", methods=["POST"])
@need_access
@need_profile
def comment_wall(handle):
    p = get_profile(handle)
    body = request.form.get("body", "").strip()[:2000]
    if body:
        db.execute("INSERT INTO net_comments (wall_id, author_id, body) VALUES (%s, %s, %s)",
                   (p["id"], current_profile()["id"], body))
    return redirect(url_for("net.profile", handle=handle) + "#comentarios")


@bp.route("/u/<handle>/editar", methods=["GET", "POST"])
@need_access
def edit(handle):
    p = get_profile(handle)
    if not can_edit(p):
        abort(403)
    if request.method == "POST":
        data = {f: request.form.get(f, "").strip()[:4000] for f in PROFILE_FIELDS}
        if not data["display_name"]:
            data["display_name"] = p["display_name"]
        theme = request.form.get("theme") if request.form.get("theme") in THEMES else "clasico"
        style = {}
        if request.form.get("use_custom_colors"):
            for key in ["page", "box", "head", "head_text", "text", "link", "accent"]:
                v = request.form.get(f"c_{key}", "")
                if HEX_RE.match(v):
                    style[key] = v
        if request.form.get("font") in FONTS:
            style["font"] = request.form["font"]
        style["bg_mode"] = "tile" if request.form.get("bg_mode") == "tile" else "cover"
        style["box_alpha"] = request.form.get("box_alpha", 100, type=int)
        top = [x for x in request.form.getlist("top") if x.isdigit()][:8]
        images = {}
        for field, key in [("avatar", "avatar_id"), ("cover", "cover_id"), ("bg", "bg_id")]:
            new_id = H.save_upload(request.files.get(field))
            images[key] = p[key]
            if new_id or request.form.get(f"remove_{field}"):
                H.delete_image(p[key])
                images[key] = new_id
        db.execute(
            "UPDATE net_profiles SET " + ", ".join(f"{f}=%s" for f in PROFILE_FIELDS) +
            ", theme=%s, style_json=%s, custom_css=%s, top_friends=%s, avatar_id=%s, cover_id=%s, bg_id=%s "
            "WHERE id=%s",
            tuple(data[f] for f in PROFILE_FIELDS) + (
                theme, json.dumps(style), request.form.get("custom_css", "")[:8000], ",".join(top),
                images["avatar_id"], images["cover_id"], images["bg_id"], p["id"]))
        if H.is_master():
            char_id = request.form.get("character_id", type=int)
            db.execute("UPDATE net_profiles SET is_npc=%s, character_id=%s WHERE id=%s",
                       (bool(request.form.get("is_npc")), char_id or None, p["id"]))
        flash("perfil guardado.")
        return redirect(url_for("net.profile", handle=p["handle"]))
    others = db.query("SELECT id, handle, display_name FROM net_profiles WHERE id<>%s ORDER BY display_name",
                      (p["id"],))
    chars = db.query("SELECT id, name FROM characters ORDER BY is_npc, name") if H.is_master() else []
    top = [int(x) for x in (p["top_friends"] or "").split(",") if x.isdigit()]
    return render("net/edit.html", p=p, style=resolve_style(p), themes=THEMES, fonts=FONTS,
                  others=others, top=top, chars=chars)


@bp.route("/u/<handle>/borrar", methods=["POST"])
@need_access
def delete_profile(handle):
    p = get_profile(handle)
    if not can_edit(p):
        abort(403)
    imgs = [p["avatar_id"], p["cover_id"], p["bg_id"]] + [
        r["image_id"] for r in db.query("SELECT image_id FROM net_posts WHERE profile_id=%s AND image_id IS NOT NULL",
                                        (p["id"],))]
    db.execute("DELETE FROM net_profiles WHERE id=%s", (p["id"],))
    for i in imgs:
        H.delete_image(i)
    if session.get("net_pid") == p["id"]:
        session.pop("net_pid", None)
    flash(f"el perfil @{p['handle']} fue borrado.")
    return redirect(url_for("net.home"))


# ---------------------------------------------------------------- contraseñas y recuperación

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I para que no se confundan


def new_recovery_code():
    return "-".join("".join(secrets.choice(CODE_ALPHABET) for _ in range(4)) for _ in range(3))


def normalize_code(code):
    raw = re.sub(r"[^A-Za-z0-9]", "", code or "").upper()
    return "-".join(raw[i:i + 4] for i in range(0, len(raw), 4))


def check_new_password(new, repeat):
    if len(new) < 4:
        return "la contraseña nueva tiene que tener al menos 4 caracteres."
    if new != repeat:
        return "las dos contraseñas nuevas no coinciden."
    return None


@bp.route("/codigo")
@need_access
@need_profile
def show_code():
    """Muestra una sola vez el código de recuperación recién generado."""
    code = session.pop("net_new_code", None)
    if not code:
        return redirect(url_for("net.account"))
    nxt = url_for("net.edit", handle=current_profile()["handle"]) if request.args.get("siguiente") == "editar" \
        else url_for("net.account")
    return render("net/code.html", code=code, nxt=nxt)


@bp.route("/cuenta", methods=["GET", "POST"])
@need_access
@need_profile
def account():
    me = current_profile()
    master = H.is_master()
    if request.method == "POST":
        action = request.form.get("action")
        current = request.form.get("current", "")
        # el master (manejando npcs) no necesita la contraseña actual; un perfil sin contraseña tampoco
        if not master and me["password_hash"] and not check_password_hash(me["password_hash"], current):
            time.sleep(1)
            flash("la contraseña actual no es correcta.")
            return redirect(url_for("net.account"))
        if action == "password":
            error = check_new_password(request.form.get("new", ""), request.form.get("repeat", ""))
            if error:
                flash(error)
            else:
                db.execute("UPDATE net_profiles SET password_hash=%s WHERE id=%s",
                           (generate_password_hash(request.form["new"]), me["id"]))
                flash("contraseña cambiada ♥")
        elif action == "code":
            code = new_recovery_code()
            db.execute("UPDATE net_profiles SET recovery_hash=%s WHERE id=%s",
                       (generate_password_hash(code), me["id"]))
            session["net_new_code"] = code
            return redirect(url_for("net.show_code"))
        return redirect(url_for("net.account"))
    return render("net/account.html", me=me, needs_current=not master and bool(me["password_hash"]))


@bp.route("/recuperar", methods=["GET", "POST"])
@need_access
def recover():
    if request.method == "POST":
        handle = request.form.get("handle", "").strip().lower().lstrip("@")
        code = normalize_code(request.form.get("code", ""))
        p = db.query("SELECT * FROM net_profiles WHERE handle=%s", (handle,), one=True)
        if not p or not p["recovery_hash"] or not check_password_hash(p["recovery_hash"], code):
            time.sleep(1)
            flash("ese usuario y código no coinciden. si perdiste el código, pedile al master una contraseña nueva.")
            return render("net/recover.html", form=request.form)
        error = check_new_password(request.form.get("new", ""), request.form.get("repeat", ""))
        if error:
            flash(error)
            return render("net/recover.html", form=request.form)
        # el código se usa una sola vez: se reemplaza por uno nuevo
        fresh = new_recovery_code()
        db.execute("UPDATE net_profiles SET password_hash=%s, recovery_hash=%s WHERE id=%s",
                   (generate_password_hash(request.form["new"]), generate_password_hash(fresh), p["id"]))
        session["net_pid"] = p["id"]
        session["net_new_code"] = fresh
        flash("¡listo! contraseña nueva guardada. tu código viejo ya no sirve: guardá este nuevo.")
        return redirect(url_for("net.show_code"))
    return render("net/recover.html", form={})
