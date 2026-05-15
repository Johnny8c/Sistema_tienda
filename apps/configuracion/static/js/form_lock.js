/* Previene doble-submit de formularios.
 *
 * Si el usuario hace doble-click en "Crear" / "Guardar" muy rápido (o le
 * llega un latigazo de red lento), evitamos que el formulario se envíe
 * dos veces y se creen registros duplicados.
 *
 * Mientras el form esta en vuelo:
 *   - Cualquier nuevo submit se cancela.
 *   - Los botones submit quedan deshabilitados con un spinner.
 *
 * Si el usuario vuelve via boton "atras" del navegador (bfcache), todo se
 * resetea para que el form sea usable de nuevo.
 *
 * Opt-out: agregar `data-allow-double="1"` al <form>.
 */
(function () {
  const SPINNER_HTML =
    '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>';

  function lock(form) {
    form.dataset.submitting = '1';
    // Diferimos el disable hasta el proximo tick: el navegador ya recolecto
    // los datos del form (incluyendo name/value del boton submitter) y arranco
    // la peticion. Si deshabilitamos ANTES, el boton no envia su name/value.
    setTimeout(function () {
      form.querySelectorAll('button[type="submit"], input[type="submit"]').forEach(function (b) {
        if (b.disabled) return;
        b.dataset.lockedByFormLock = '1';
        if (b.tagName === 'BUTTON' && !b.dataset.originalHtml) {
          b.dataset.originalHtml = b.innerHTML;
          // Mantenemos el texto pero anteponemos un spinner
          b.innerHTML = SPINNER_HTML + b.textContent.trim();
        }
        b.disabled = true;
      });
    }, 0);
  }

  function unlock(form) {
    form.dataset.submitting = '';
    form.querySelectorAll('[data-locked-by-form-lock="1"]').forEach(function (b) {
      b.disabled = false;
      delete b.dataset.lockedByFormLock;
      if (b.dataset.originalHtml) {
        b.innerHTML = b.dataset.originalHtml;
        delete b.dataset.originalHtml;
      }
    });
  }

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.dataset.allowDouble === '1') return;

    if (form.dataset.submitting === '1') {
      e.preventDefault();
      e.stopImmediatePropagation();
      return;
    }
    lock(form);
  }, true);

  // bfcache: al volver con boton atras el form aun marca submitting=1
  // pero la peticion ya termino. Reactivar todo.
  window.addEventListener('pageshow', function (e) {
    if (e.persisted) {
      document.querySelectorAll('form[data-submitting="1"]').forEach(unlock);
    }
  });
})();
