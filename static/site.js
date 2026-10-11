/* hilos rojos de la pizarra + botoneras del editor. sin librerías, como debe ser. */
(function () {
  function drawStrings() {
    var wrap = document.querySelector('.board-wrap');
    if (!wrap) return;
    var svg = wrap.querySelector('svg.strings');
    var links = [];
    try { links = JSON.parse(wrap.getAttribute('data-links') || '[]'); } catch (e) {}
    var box = wrap.getBoundingClientRect();
    svg.setAttribute('viewBox', '0 0 ' + box.width + ' ' + box.height);
    svg.innerHTML = '';
    var seen = {};
    links.forEach(function (l) {
      var a = wrap.querySelector('[data-id="' + l.from_id + '"] .pin');
      var b = wrap.querySelector('[data-id="' + l.to_id + '"] .pin');
      if (!a || !b) return;
      var key = Math.min(l.from_id, l.to_id) + '-' + Math.max(l.from_id, l.to_id);
      var ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      var x1 = ra.left + ra.width / 2 - box.left, y1 = ra.top + ra.height / 2 - box.top;
      var x2 = rb.left + rb.width / 2 - box.left, y2 = rb.top + rb.height / 2 - box.top;
      // si el hilo ya existe en sentido contrario, lo curvamos un poco para que se vean los dos
      var bend = seen[key] ? 18 : 0;
      seen[key] = true;
      var mx = (x1 + x2) / 2, my = (y1 + y2) / 2 + 22 + bend;
      var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', 'M' + x1 + ' ' + y1 + ' Q' + mx + ' ' + my + ' ' + x2 + ' ' + y2);
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke', '#B8362F');
      path.setAttribute('stroke-width', String(1 + Math.min(l.amount, 4) * 0.6));
      path.setAttribute('stroke-linecap', 'round');
      path.setAttribute('opacity', '0.85');
      svg.appendChild(path);
    });
  }

  window.addEventListener('load', drawStrings);
  window.addEventListener('resize', drawStrings);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(drawStrings);

  // botonera bbcode
  document.querySelectorAll('[data-bb-for]').forEach(function (bar) {
    var ta = document.getElementById(bar.getAttribute('data-bb-for'));
    bar.querySelectorAll('button[data-open]').forEach(function (btn) {
      btn.addEventListener('click', function (ev) {
        ev.preventDefault();
        var open = btn.getAttribute('data-open'), close = btn.getAttribute('data-close') || '';
        var s = ta.selectionStart, e = ta.selectionEnd, v = ta.value;
        ta.value = v.slice(0, s) + open + v.slice(s, e) + close + v.slice(e);
        ta.focus();
        ta.selectionStart = s + open.length;
        ta.selectionEnd = e + open.length;
      });
    });
  });

  // botón "insertar" junto a cada imagen subida
  document.querySelectorAll('[data-insert]').forEach(function (btn) {
    btn.addEventListener('click', function (ev) {
      ev.preventDefault();
      var ta = document.getElementById(btn.getAttribute('data-target'));
      var code = btn.getAttribute('data-insert');
      var s = ta.selectionStart;
      ta.value = ta.value.slice(0, s) + code + ta.value.slice(s);
      ta.focus();
    });
  });

  // confirmación sin confirm(): el botón pide un segundo click
  document.querySelectorAll('button[data-confirm]').forEach(function (btn) {
    btn.addEventListener('click', function (ev) {
      if (btn.getAttribute('data-armed')) return;
      ev.preventDefault();
      btn.setAttribute('data-armed', '1');
      var old = btn.textContent;
      btn.textContent = btn.getAttribute('data-confirm');
      setTimeout(function () { btn.removeAttribute('data-armed'); btn.textContent = old; }, 4000);
    });
  });

  // efecto de conexión por módem en el portal
  var dial = document.querySelector('.dialup');
  if (dial) {
    var steps = ['marcando 0-800-HOLLOW...', 'krrrrrr-iiiiii-shhhhh...', 'conectado a 33.6 kbps', 'conectado a 33.6 kbps. señal: débil'];
    var i = 0;
    var t = setInterval(function () {
      dial.textContent = steps[i++];
      if (i >= steps.length) clearInterval(t);
    }, 900);
  }
})();
