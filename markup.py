"""Mini BBCode al estilo foro de los 2000.

Todo el texto se escapa primero; después se convierten unas pocas etiquetas
conocidas a HTML. Nunca se deja pasar HTML escrito a mano.
"""
import re
import unicodedata

from markupsafe import Markup, escape

COLOR_RE = r"(#[0-9a-fA-F]{3,6}|[a-zA-Z]{3,20})"

SIMPLE_TAGS = [
    (r"\[b\](.+?)\[/b\]", r"<strong>\1</strong>"),
    (r"\[i\](.+?)\[/i\]", r"<em>\1</em>"),
    (r"\[u\](.+?)\[/u\]", r"<u>\1</u>"),
    (r"\[s\](.+?)\[/s\]", r"<s>\1</s>"),
    (r"\[tachado\](.+?)\[/tachado\]", r"<s>\1</s>"),
    (r"\[center\](.+?)\[/center\]", r'<div class="bb-center">\1</div>'),
    (r"\[quote\](.+?)\[/quote\]", r'<blockquote class="bb-quote">\1</blockquote>'),
    (r"\[nota\](.+?)\[/nota\]", r'<div class="bb-note">\1</div>'),
    (r"\[spoiler\](.+?)\[/spoiler\]", r'<details class="bb-spoiler"><summary>spoiler (click)</summary>\1</details>'),
    (r"\[blink\](.+?)\[/blink\]", r'<span class="blink">\1</span>'),
    (r"\[marquee\](.+?)\[/marquee\]", r'<div class="bb-marquee"><span>\1</span></div>'),
    (r"\[color=" + COLOR_RE + r"\](.+?)\[/color\]", r'<span style="color:\1">\2</span>'),
    (r"\[h\](.+?)\[/h\]", r'<h4 class="bb-h">\1</h4>'),
]


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "sin-nombre"


def render(text, image_url=None, character_url=None):
    """Convierte BBCode a HTML seguro.

    image_url(id) -> url de una imagen subida, para [img:ID]
    character_url(nombre) -> url de la wiki, para [[Nombre]]
    """
    if not text:
        return Markup("")
    html = str(escape(text.replace("\r\n", "\n")))

    for pattern, repl in SIMPLE_TAGS:
        # repetir para soportar anidado sencillo
        for _ in range(3):
            html = re.sub(pattern, repl, html, flags=re.IGNORECASE | re.DOTALL)

    def url_tag(m):
        href, label = m.group(1), m.group(2)
        if not re.match(r"^https?://", href, re.IGNORECASE):
            return m.group(0)
        return f'<a href="{href}" target="_blank" rel="noopener nofollow">{label}</a>'

    html = re.sub(r"\[url=([^\]\s]+)\](.+?)\[/url\]", url_tag, html, flags=re.IGNORECASE | re.DOTALL)

    if image_url:
        def img_tag(m):
            img_id = int(m.group(1))
            pos = (m.group(2) or "").lower()
            cls = {"izq": "bb-img left", "der": "bb-img right"}.get(pos, "bb-img")
            return f'<img class="{cls}" src="{image_url(img_id)}" alt="imagen {img_id}" loading="lazy">'

        html = re.sub(r"\[img:(\d+)(?::(izq|der))?\]", img_tag, html, flags=re.IGNORECASE)

    if character_url:
        def wiki_tag(m):
            name = m.group(1).strip()
            return f'<a class="wikilink" href="{character_url(name)}">{name}</a>'

        html = re.sub(r"\[\[([^\[\]]{1,80})\]\]", wiki_tag, html)

    # como en los foros: cada salto de línea es un <br>, salvo el que va pegado a un bloque
    html = re.sub(r"(</?(?:h4|blockquote|div|details)[^>]*>)[ \t]*\n", r"\1", html)
    html = re.sub(r"\n[ \t]*(<(?:h4|blockquote|div|details)[ >])", r"\1", html)
    html = html.strip().replace("\n", "<br>\n")
    return Markup(html)


def excerpt(text, length=260):
    plain = re.sub(r"\[\[([^\[\]]{1,80})\]\]", r"\1", text or "")
    plain = re.sub(r"\[/?[a-zA-Z]+(=[^\]]*)?\]|\[img:\d+(:\w+)?\]", "", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain if len(plain) <= length else plain[:length].rsplit(" ", 1)[0] + "…"
