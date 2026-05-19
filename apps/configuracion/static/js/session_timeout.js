/* Cierre de sesión por inactividad (lado navegador).
 *
 * Complementa el timeout del servidor: si el usuario deja la pantalla
 * abierta sin tocar nada, lo mandamos a /logout/ antes de que la pantalla
 * quede mostrando datos sensibles. Cualquier actividad (mouse, teclado,
 * scroll, touch) reinicia el contador.
 *
 * El tiempo se lee de <body data-session-timeout="SEGUNDOS">.
 * Muestra un aviso 60s antes de cerrar.
 *
 * IMPORTANTE — por qué NO usamos solo setTimeout:
 * Los navegadores CONGELAN setTimeout/setInterval cuando la pestaña está
 * en segundo plano o el equipo suspendido. Con setTimeout puro, dejar el
 * sistema abierto en otra pestaña hacía que el cierre NUNCA se disparara.
 * Solución: guardamos la marca de tiempo de la última actividad y
 * comprobamos el RELOJ REAL (Date.now) periódicamente y, sobre todo,
 * cada vez que la pestaña vuelve a primer plano (visibilitychange).
 * Así el tiempo transcurrido es real aunque los temporizadores se congelen.
 * Además sincronizamos la actividad entre pestañas vía localStorage.
 */
(function () {
  var body = document.body;
  var totalSeg = parseInt(body.getAttribute('data-session-timeout') || '0', 10);
  if (!totalSeg || totalSeg < 60) return;  // desactivado o muy corto

  var LIMITE_MS = totalSeg * 1000;
  var AVISO_MS = 60 * 1000;                 // avisar 1 min antes
  var CHEQUEO_MS = 15 * 1000;               // revisar el reloj cada 15s
  var LS_KEY = 'sessionLastActivity';       // compartido entre pestañas

  var aviso = null;
  var intervalo = null;
  var cerrando = false;

  function ahora() { return Date.now(); }

  function leerUltima() {
    var v = parseInt(localStorage.getItem(LS_KEY) || '0', 10);
    return isNaN(v) ? 0 : v;
  }

  function marcarActividad() {
    try { localStorage.setItem(LS_KEY, String(ahora())); } catch (e) {}
    quitarAviso();
  }

  function logout() {
    if (cerrando) return;
    cerrando = true;
    if (intervalo) { clearInterval(intervalo); intervalo = null; }
    window.location.href = '/logout/';
  }

  function quitarAviso() {
    if (aviso) { aviso.remove(); aviso = null; }
  }

  function mostrarAviso() {
    if (aviso || cerrando) return;
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
        .finally(function () {
          marcarActividad();
          evaluar();
        });
    });
    aviso.appendChild(texto);
    aviso.appendChild(btn);
    body.appendChild(aviso);
  }

  // Núcleo: compara el reloj real contra la última actividad.
  function evaluar() {
    if (cerrando) return;
    var transcurrido = ahora() - leerUltima();
    if (transcurrido >= LIMITE_MS) {
      logout();
    } else if (transcurrido >= LIMITE_MS - AVISO_MS) {
      mostrarAviso();
    } else {
      quitarAviso();
    }
  }

  // Throttle: registrar actividad a lo sumo 1 vez cada 5s.
  var ultimoRegistro = 0;
  function actividad() {
    var t = ahora();
    if (t - ultimoRegistro < 5000) return;
    ultimoRegistro = t;
    marcarActividad();
  }

  ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart', 'click']
    .forEach(function (ev) {
      window.addEventListener(ev, actividad, { passive: true });
    });

  // Clave anti-congelamiento: al volver la pestaña a primer plano,
  // evaluamos el tiempo real transcurrido inmediatamente.
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) evaluar();
  });
  window.addEventListener('focus', evaluar);
  window.addEventListener('pageshow', evaluar);

  // Sincronización entre pestañas: si en otra pestaña hubo actividad o
  // se cerró sesión, esta reacciona.
  window.addEventListener('storage', function (e) {
    if (e.key === LS_KEY) evaluar();
  });

  // Arranque: cargar esta página YA es actividad y el servidor acabó de
  // renovar la cookie de sesión, así que reiniciamos el contador. (Si no
  // lo hiciéramos, una marca vieja en localStorage cerraría al instante.)
  marcarActividad();
  intervalo = setInterval(evaluar, CHEQUEO_MS);
  evaluar();
})();
