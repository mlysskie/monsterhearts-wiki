"""pueblonet: perfiles, posts, likes, comentarios, seguir, estilos y permisos."""
import io
import re

from helpers import csrf, png, txt
from app import app


def player(name):
    c = app.test_client(); t = csrf(c.get("/entrar"))
    assert c.post("/entrar", data={"csrf": t, "name": name, "code": "luna-1996"}).status_code == 302
    return c, csrf(c.get("/red/"))


assert app.test_client().get("/red/").status_code == 302
assert app.test_client().get("/red/u/x").status_code == 302
m = app.test_client(); t = csrf(m.get("/master/login"))
m.post("/master/login", data={"csrf": t, "user": "master", "password": "secreto"}); mt = csrf(m.get("/master"))
r = m.post("/master/personaje/nuevo", data={"csrf": mt, "name": "Dante", "visible": "1"}, content_type="multipart/form-data")
dante_id = int(r.location.rsplit("/", 1)[1])
a, at = player("Mili")
assert "crear perfil" in txt(a.get("/red/registro"))
assert "usuario tiene que" in txt(a.post("/red/registro", data={"csrf": at, "handle": "Mal Handle!", "display_name": "x", "password": "1234"}))
r = a.post("/red/registro", data={"csrf": at, "handle": "lanueva", "display_name": "✧ la nueva ✧", "password": "abcd", "character_id": str(dante_id)})
assert r.status_code == 302 and "/red/codigo" in r.location
assert a.post("/red/registro", data={"csrf": at, "handle": "lanueva", "display_name": "x", "password": "abcd"}).status_code == 200
r = a.post("/red/u/lanueva/editar", data={
    "csrf": at, "display_name": "✧ la nueva ✧", "status_text": "observando", "mood": "rara", "age": "16",
    "about_me": "[b]hola[/b] <script>alert(1)</script>", "int_music": "Syd Matters", "song": "Obstacles",
    "theme": "gotico", "font": "gotica", "use_custom_colors": "1", "c_accent": "#ff00ff", "c_page": "bad",
    "bg_mode": "tile", "box_alpha": "70",
    "custom_css": ".prof-name{color:red} </style><script>x</script> @import url(http://evil.com/a.css); "
                  "body{background:url(http://evil.com/x.png)} .a{background:url('/img/1')} \\3c script",
    "avatar": (io.BytesIO(png((200, 50, 50))), "a.png"), "cover": (io.BytesIO(png((50, 50, 200))), "c.png"),
    "bg": (io.BytesIO(png((10, 10, 10))), "b.png")}, content_type="multipart/form-data")
assert r.status_code == 302, txt(r)[:300]
h = txt(a.get("/red/u/lanueva"))
assert "<script>alert" not in h and "&lt;script&gt;" in h and "<strong>hola</strong>" in h
css = h.split("css propio de @lanueva")[1].split("</style>")[0]
assert "evil.com" not in css and "<script" not in css and "@import" not in css and "\\" not in css and "url('/img/1')" in css, css
assert "--p-accent:#ff00ff" in h and "--p-page:#0d0d0d" in h and "UnifrakturMaguntia" in h
assert "background-repeat:repeat" in h and "--p-alpha:70" in h
assert "ficha en la wiki" in h and "observando" in h and "¡ONLINE!" in h
assert "@lanueva" in txt(m.get("/wiki/dante"))
b, bt = player("Tomi")
b.post("/red/registro", data={"csrf": bt, "handle": "tomi", "display_name": "Tomi", "password": "qwer"})
b.get("/red/salir")
assert "incorrectos" in txt(b.post("/red/entrar", data={"csrf": bt, "handle": "tomi", "password": "mal"}, follow_redirects=True))
assert "hola de nuevo" in txt(b.post("/red/entrar", data={"csrf": bt, "handle": "@Tomi", "password": "qwer"}, follow_redirects=True))
assert a.post("/red/publicar", data={"csrf": at, "body": "primer día en el pueblo", "mood": "nerviosa",
              "image": (io.BytesIO(png()), "p.png"), "next": "/red/"}, content_type="multipart/form-data").status_code == 302
pid = int(re.search(r'id="post-(\d+)"', txt(a.get("/red/u/lanueva"))).group(1))
assert b.post(f"/red/post/{pid}/like", data={"csrf": bt}).status_code == 302
h = txt(b.get(f"/red/post/{pid}")); assert "1</b> me gusta" in h and "♥ me gusta" in h
b.post(f"/red/post/{pid}/like", data={"csrf": bt}); assert "0</b> me gustan" in txt(b.get(f"/red/post/{pid}"))
b.post(f"/red/post/{pid}/like", data={"csrf": bt})
b.post(f"/red/post/{pid}/comentar", data={"csrf": bt, "body": "bienvenida!!"})
assert "bienvenida!!" in txt(a.get(f"/red/post/{pid}"))
assert b.post("/red/u/lanueva/seguir", data={"csrf": bt}).status_code == 302
b.post("/red/u/lanueva/comentar", data={"csrf": bt, "body": "te vi en el mirador"})
h = txt(a.get("/red/u/lanueva")); assert "te vi en el mirador" in h and '<span class="accent">1</span> seguidor.' in h
assert "primer día" in txt(b.get("/red/feed"))
h = txt(a.get("/red/")); assert "empezó a seguirte" in h and "le dio ♥" in h and "comentó" in h and "te dejó un" in h
v1 = int(re.search(r'class="views">(\d+)', txt(b.get("/red/u/lanueva"))).group(1))
v2 = int(re.search(r'class="views">(\d+)', txt(b.get("/red/u/lanueva"))).group(1)); assert v1 == v2 >= 1
tomi_id = int(re.search(r'name="top">.*?<option value="(\d+)"', txt(a.get("/red/u/lanueva/editar")), re.S).group(1))
a.post("/red/u/lanueva/editar", data={"csrf": at, "display_name": "✧ la nueva ✧", "theme": "clasico", "top": [str(tomi_id)]},
       content_type="multipart/form-data")
assert 'href="/red/u/tomi"' in txt(a.get("/red/u/lanueva"))
for path in ["/red/gente", "/red/gente?q=tom", "/red/explorar", "/red/u/lanueva/posts", "/red/u/lanueva/seguidores",
             "/red/u/tomi/seguidores?ver=siguiendo", "/red/feed?p=2"]:
    assert a.get(path).status_code == 200, path
h = txt(a.get("/red/gente?q=tom")); assert "Tomi" in h and "la nueva" not in h
assert b.get("/red/u/lanueva/editar").status_code == 403
assert b.post(f"/red/post/{pid}/borrar", data={"csrf": bt}).status_code == 403
assert b.post("/red/u/lanueva/borrar", data={"csrf": bt}).status_code == 403
assert b.post("/red/entrar-como/1", data={"csrf": bt}).status_code == 403
c, ct = player("Anon")
assert c.post(f"/red/post/{pid}/like", data={"csrf": ct}).status_code == 302 and "1</b> me gusta" in txt(c.get(f"/red/post/{pid}"))
assert m.post("/red/registro", data={"csrf": mt, "handle": "srapratt", "display_name": "Sra. Pratt", "password": "", "is_npc": "1"}).status_code == 302
assert "incorrectos" in txt(b.post("/red/entrar", data={"csrf": bt, "handle": "srapratt", "password": ""}, follow_redirects=True))
assert "master: usar un perfil" in txt(m.get("/red/"))
m.post(f"/red/entrar-como/{tomi_id}", data={"csrf": mt})
assert "@tomi" in txt(m.get("/red/"))
npc_id = int(re.search(r'entrar-como/(\d+)"[^<]*<input[^>]*>\s*<button[^>]*>★ Sra', txt(m.get("/red/")), re.S).group(1))
m.post(f"/red/entrar-como/{npc_id}", data={"csrf": mt})
m.post("/red/u/lanueva/comentar", data={"csrf": mt, "body": "silencio en la biblioteca."})
assert "silencio en la biblioteca" in txt(a.get("/red/u/lanueva"))
assert m.get("/red/u/lanueva/editar").status_code == 200
cid = int(re.search(r'comentario/(\d+)/borrar', txt(m.get("/red/u/lanueva"))).group(1))
assert m.post(f"/red/comentario/{cid}/borrar", data={"csrf": mt}).status_code == 302
assert a.post(f"/red/post/{pid}/borrar", data={"csrf": at}).status_code == 302 and a.get(f"/red/post/{pid}").status_code == 404
assert a.post("/red/u/lanueva/borrar", data={"csrf": at}).status_code == 302 and a.get("/red/u/lanueva").status_code == 404
assert "@lanueva" not in txt(m.get("/wiki/dante"))
for path in ["/", "/elenco", "/lore", "/master"]:
    assert m.get(path).status_code == 200
print("OK pueblonet")
