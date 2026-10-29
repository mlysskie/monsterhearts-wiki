"""Wiki, blog, acceso por código y panel del master."""
import io
import re

from helpers import csrf, png, txt
from app import app

m = app.test_client()
r = m.get("/"); assert r.status_code == 302 and "/entrar" in r.location
t = csrf(m.get("/master/login"))
assert "incorrectos" in txt(m.post("/master/login", data={"csrf": t, "user": "master", "password": "mal"}))
assert m.post("/master/login", data={"csrf": t, "user": "master", "password": "secreto"}).status_code == 302
r = m.get("/master"); assert "luna-1996" in txt(r); t = csrf(r)
ids = []
for n in ["La Nueva", "El Chico Lobo", "Reina de las Hadas"]:
    r = m.post("/master/personaje/nuevo", data={"csrf": t, "name": n, "skin": "La Bruja", "visible": "1",
               "story": "vive en [[El Chico Lobo]].\n\n[b]ojo[/b] <script>x</script>",
               "image": (io.BytesIO(png()), "a.png")}, content_type="multipart/form-data")
    assert r.status_code == 302; ids.append(int(r.location.rsplit("/", 1)[1]))
assert m.post(f"/master/personaje/{ids[0]}", data={"csrf": t, "name": "La Nueva", "visible": "1", f"str_{ids[1]}": "2",
              f"note_{ids[1]}": "lo vio", "secrets": "es un fantasma"}, content_type="multipart/form-data").status_code == 302
r = m.post("/master/entrada/nueva", data={"csrf": t, "title": "sesión 01", "body": "[nota]hola[/nota] [[La Nueva]]",
           "tags": "Bosque, sesión 01", "published": "1", "created_at": "2003-10-14T23:10",
           "cover": (io.BytesIO(png()), "c.png"),
           "gallery": [(io.BytesIO(png()), "g1.png"), (io.BytesIO(png()), "g2.png")]}, content_type="multipart/form-data")
assert r.status_code == 302; pid = int(r.location.rsplit("/", 1)[1])
imgs = re.findall(r"\[img:(\d+)\]</code>", txt(m.get(f"/master/entrada/{pid}"))); assert len(imgs) == 2
assert m.post(f"/master/entrada/{pid}", data={"csrf": t, "title": "sesión 01", "body": f"texto [img:{imgs[0]}:izq]",
              "tags": "bosque", "published": "1", f"cap_{imgs[1]}": "el mirador"},
              content_type="multipart/form-data").status_code == 302
m.post("/master/entrada/nueva", data={"csrf": t, "title": "borrador secreto", "body": "x"}, content_type="multipart/form-data")
for path in ["/", "/elenco", "/wiki/la-nueva", "/lore", "/lore?tag=bosque", "/lore?mes=2003-10", f"/lore/{pid}",
             "/ayuda", "/wiki/nadie", "/master", f"/master/personaje/{ids[0]}", f"/master/entrada/{pid}"]:
    assert m.get(path).status_code in (200, 404), path
h = txt(m.get("/wiki/el-chico-lobo")); assert "&lt;script&gt;" in h and 'class="wikilink"' in h
h = txt(m.get(f"/lore/{pid}")); assert "el mirador" in h and "bb-img left" in h
assert '"amount": 2' in txt(m.get("/"))
p = app.test_client(); t2 = csrf(p.get("/entrar"))
assert "incorrecto" in txt(p.post("/entrar", data={"csrf": t2, "name": "Mili", "code": "mal"}))
assert p.post("/entrar", data={"csrf": t2, "name": "Mili", "code": "LUNA-1996"}).status_code == 302
assert "es un fantasma" not in txt(p.get("/wiki/la-nueva"))
h = txt(p.get("/lore")); assert "borrador secreto" not in h and "sesión 01" in h
assert p.get(f"/img/{imgs[1]}").status_code == 200 and app.test_client().get(f"/img/{imgs[1]}").status_code == 403
assert p.post(f"/lore/{pid}", data={"csrf": csrf(p.get(f"/lore/{pid}")), "body": "qué miedo"}).status_code == 302
assert p.post("/shout", data={"csrf": csrf(p.get("/")), "body": "holi", "next": "/"}).status_code == 302
h = txt(p.get("/")); assert "holi" in h and "Mili" in h
assert p.get("/master").status_code == 302 and p.post("/shout", data={"body": "x"}).status_code == 400
assert m.post("/master/codigo", data={"csrf": t, "code": "pino-2", "kick": "1"}).status_code == 302
assert p.get("/").status_code == 302
assert m.post(f"/master/entrada/{pid}/borrar", data={"csrf": t}).status_code == 302
assert m.post(f"/master/personaje/{ids[2]}/borrar", data={"csrf": t}).status_code == 302
m.post("/master/codigo", data={"csrf": t, "code": "luna-1996"})  # dejar el código como estaba
print("OK wiki")
