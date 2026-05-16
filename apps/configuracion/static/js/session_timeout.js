/* Cierre de sesión por inactividad (lado navegador).
 *
 * Complementa el timeout del servidor: si el usuario deja la pantalla
 * abierta sin tocar nada, lo mandamos a /logout/ antes de que la pantalla
 * quede mostrando datos sensibles. Cualquier actividad (mouse, teclado,
 * scroll, touch) reinicia el contador.
 *
 * El tiempo se lee de <body data-session-timeout="SEGUNDOS">.
 * Muestra un aviso 60s antes de cerrar.
 */
(function () {
  var body = document.body;
  var totalSeg = parseInt(body.getAttribute('data-session-timeout') || '0', 10);
  if (!totalSeg || totalSeg < 60) return;  // desactivado o muy corto

  var AVISO_SEG = 60;                       // avisar 1 min antes
  var timerCierre = null;
  var timerAviso = null;
  var aviso = null;

  function logout() {
    window.location.href = '/logout/';
  }

  function quitarAviso() {
    if (aviso) { aviso.remove(); aviso = null; }
  }

  function mostrarAviso() {
    if (aviso) return;
    aviso = document.createElement('div');
    aviso.setAttribute('role', 'alert');
    aviso.style.cssText =
      'position:fixed;top:16px;left:50%;transform:translateX(-50%);' +
      'z-index:99999;background:#1E293B;color:#fff;padding:14px 20px;' +
      'border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.35);' +
      'font-size:14px;font-family:inherit;display:flex;align-items:center;gap:14px;' +
      'max-width:92vw';
    var texto = document.createElement('span');
    texto.textContent = 'Tu sesión se cerrará pronto por inactividad.';
    var btn = document.createElement('button');
    btn.textContent = 'Seguir conectado';
    btn.style.cssText =
      'background:#4F46E5;color:#fff;border:none;padding:7px 14px;' +
      'border-radius:8px;font-weight:600;cursor:pointer;font-size:13px;white-space:nowrap';
    btn.addEventListener('click', function () {
      // Un fetch ligero al servidor renueva la cookie de sesión (sliding)
      fetch('/dashboard/', { method: 'HEAD', credentials: 'same-origin' })
        .catch(function () {})
        .finally(reiniciar);
    });
    aviso.appendChild(texto);
    aviso.appendChild(btn);
    body.appendChild(aviso);
  }

  function reiniciar() {
    clearTimeout(timerCierre);
    clearTimeout(timerAviso);
    quitarAviso();
    timerAviso = setTimeout(mostrarAviso, (totalSeg - AVISO_SEG) * 1000);
    timerCierre = setTimeout(logout, totalSeg * 1000);
  }

  // Throttle: no reiniciar más de 1 vez cada 5s para no castigar el CPU
  var ultimo = 0;
  function actividad() {
    var ahora = Date.now();
    if (ahora - ultimo < 5000) return;
    ultimo = ahora;
    reiniciar();
  }

  ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart', 'click']
    .forEach(function (ev) {
      window.addEventListener(ev, actividad, { passive: true });
    });

  reiniciar();
})();
