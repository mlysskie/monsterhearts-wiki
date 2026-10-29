"""Contraseñas: master (cambio y recuperación por Railway) y pueblonet (cuenta, código, reseteo)."""
import os, re, sqlite3
from helpers import csrf, txt
if not os.environ.get("DATABASE_URL"):
    # base "vieja": net_profiles sin la columna recovery_hash, como la que ya está en Railway
    c=sqlite3.connect(os.environ["SQLITE_PATH"]); c.execute("CREATE TABLE net_profiles (id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL, password_hash TEXT, character_id INTEGER, is_npc INTEGER NOT NULL DEFAULT 0, avatar_id INTEGER, cover_id INTEGER, bg_id INTEGER, status_text TEXT NOT NULL DEFAULT '', mood TEXT NOT NULL DEFAULT '', headline TEXT NOT NULL DEFAULT '', age TEXT NOT NULL DEFAULT '', zodiac TEXT NOT NULL DEFAULT '', school TEXT NOT NULL DEFAULT '', about_me TEXT NOT NULL DEFAULT '', want_to_meet TEXT NOT NULL DEFAULT '', int_general TEXT NOT NULL DEFAULT '', int_music TEXT NOT NULL DEFAULT '', int_movies TEXT NOT NULL DEFAULT '', int_tv TEXT NOT NULL DEFAULT '', int_books TEXT NOT NULL DEFAULT '', int_heroes TEXT NOT NULL DEFAULT '', song TEXT NOT NULL DEFAULT '', top_friends TEXT NOT NULL DEFAULT '', theme TEXT NOT NULL DEFAULT 'clasico', style_json TEXT NOT NULL DEFAULT '{}', custom_css TEXT NOT NULL DEFAULT '', views INTEGER NOT NULL DEFAULT 0, last_seen TIMESTAMP, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    c.execute("INSERT INTO net_profiles (handle, display_name) VALUES ('viejo', 'perfil viejo')"); c.commit(); c.close()
import app as appmod
from app import app
def player(name):
    c=app.test_client(); t=csrf(c.get("/entrar")); c.post("/entrar", data={"csrf":t,"name":name,"code":"luna-1996"}); return c, csrf(c.get("/red/"))
def code_of(r): return re.search(r'class="code-big">([A-Z0-9-]+)<', txt(r)).group(1)
def net_login(c,t,h,pw): return "hola de nuevo" in txt(c.post("/red/entrar", data={"csrf":t,"handle":h,"password":pw}, follow_redirects=True))
a,at=player("Mili")
if not os.environ.get("DATABASE_URL"):
    assert "perfil viejo" in txt(a.get("/red/gente"))  # la migración no rompió perfiles existentes
# registro -> código una sola vez
r=a.post("/red/registro", data={"csrf":at,"handle":"mili","display_name":"Mili","password":"vieja1"}, follow_redirects=True)
code=code_of(r); assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", code)
assert "/red/u/mili/editar" in txt(r)
assert "code-big" not in txt(a.get("/red/codigo", follow_redirects=True))  # no se vuelve a mostrar
# cambiar contraseña desde la cuenta
assert "contraseña actual no es correcta" in txt(a.post("/red/cuenta", data={"csrf":at,"action":"password","current":"mal","new":"nueva1","repeat":"nueva1"}, follow_redirects=True))
assert "no coinciden" in txt(a.post("/red/cuenta", data={"csrf":at,"action":"password","current":"vieja1","new":"nueva1","repeat":"otra"}, follow_redirects=True))
assert "contraseña cambiada" in txt(a.post("/red/cuenta", data={"csrf":at,"action":"password","current":"vieja1","new":"nueva1","repeat":"nueva1"}, follow_redirects=True))
a.get("/red/salir"); assert not net_login(a,at,"mili","vieja1") and net_login(a,at,"mili","nueva1")
# recuperar con el código (minúsculas y sin guiones también vale)
a.get("/red/salir")
assert "no coinciden" in txt(a.post("/red/recuperar", data={"csrf":at,"handle":"mili","code":"AAAA-BBBB-CCCC","new":"x1234","repeat":"x1234"}))
r=a.post("/red/recuperar", data={"csrf":at,"handle":"@Mili","code":code.replace("-","").lower(),"new":"recuperada","repeat":"recuperada"}, follow_redirects=True)
code2=code_of(r); assert code2!=code and "@mili" in txt(r)
a.get("/red/salir"); assert net_login(a,at,"mili","recuperada")
assert "no coinciden" in txt(a.post("/red/recuperar", data={"csrf":at,"handle":"mili","code":code,"new":"x1234","repeat":"x1234"}))  # el viejo ya no sirve
# generar código nuevo invalida el anterior
assert "contraseña actual no es correcta" in txt(a.post("/red/cuenta", data={"csrf":at,"action":"code","current":"mal"}, follow_redirects=True))
code3=code_of(a.post("/red/cuenta", data={"csrf":at,"action":"code","current":"recuperada"}, follow_redirects=True))
assert "no coinciden" in txt(a.post("/red/recuperar", data={"csrf":at,"handle":"mili","code":code2,"new":"x1234","repeat":"x1234"}))
assert "code-big" in txt(a.post("/red/recuperar", data={"csrf":at,"handle":"mili","code":code3,"new":"x1234","repeat":"x1234"}, follow_redirects=True))
# links visibles
b,bt=player("Tomi"); assert "¿olvidaste tu contraseña?" in txt(b.get("/red/"))
# master
m=app.test_client(); t=csrf(m.get("/master/login"))
assert "MASTER_PASSWORD" in txt(m.get("/master/login"))
m.post("/master/login", data={"csrf":t,"user":"master","password":"secreto"}); mt=csrf(m.get("/master"))
h=txt(m.get("/master")); assert "contraseñas de pueblonet" in h and "la de Railway" in h
# master resetea la de un jugador; un jugador no puede usar esa ruta
mid=re.search(r'<option value="(\d+)">Mili \(@mili\)', h).group(1)
assert b.post("/master/pueblonet-contrasena", data={"csrf":bt,"profile_id":mid,"new":"hackeo"}).status_code==302
a.get("/red/salir"); assert not net_login(a,at,"mili","hackeo")
assert "ya puede entrar" in txt(m.post("/master/pueblonet-contrasena", data={"csrf":mt,"profile_id":mid,"new":"delmaster"}, follow_redirects=True))
assert net_login(a,at,"mili","delmaster")
# master manejando un npc: no necesita contraseña actual
m.post("/red/registro", data={"csrf":mt,"handle":"pratt","display_name":"Sra. Pratt","password":"","is_npc":"1"})
assert 'name="current"' not in txt(m.get("/red/cuenta"))
assert "contraseña cambiada" in txt(m.post("/red/cuenta", data={"csrf":mt,"action":"password","new":"npc123","repeat":"npc123"}, follow_redirects=True))
assert net_login(b,bt,"pratt","npc123")
# contraseña del master: cambiar
assert "no es correcta" in txt(m.post("/master/contrasena", data={"csrf":mt,"current":"mal","new":"nuevamaster","repeat":"nuevamaster"}, follow_redirects=True))
assert "al menos 6" in txt(m.post("/master/contrasena", data={"csrf":mt,"current":"secreto","new":"corta","repeat":"corta"}, follow_redirects=True))
assert "cambiada" in txt(m.post("/master/contrasena", data={"csrf":mt,"current":"secreto","new":"nuevamaster","repeat":"nuevamaster"}, follow_redirects=True))
assert "la que elegiste" in txt(m.get("/master"))
def master_login(pw):
    c=app.test_client(); t=csrf(c.get("/master/login")); r=c.post("/master/login", data={"csrf":t,"user":"master","password":pw}); return r.status_code==302, c
assert not master_login("secreto")[0] and master_login("nuevamaster")[0]
# recuperación: en Railway se cambia MASTER_PASSWORD
appmod.MASTER_PASSWORD="otra-de-railway"
assert not master_login("nuevamaster")[0]
ok,c=master_login("otra-de-railway"); assert ok and "recuperaste el acceso" in txt(c.get("/master"))
assert master_login("otra-de-railway")[0] and "la de Railway" in txt(c.get("/master"))
# y la wiki sigue andando
for path in ["/","/elenco","/lore","/red/","/red/gente"]:
    assert c.get(path).status_code==200, path
print("OK contraseñas")
