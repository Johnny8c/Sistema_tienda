/* Comprime imágenes en el navegador antes de subirlas al servidor.
 * Reemplaza el archivo seleccionado por una versión JPG (max 1200x1200, q=0.85)
 * para que la subida a Cloudinary sea mucho más rápida desde celular.
 *
 * Uso: agregar `data-compress` al <input type="file" accept="image/*">.
 * Opcional: data-compress-max="1600" data-compress-quality="0.9"
 */
(function () {
  function readFile(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  function loadImage(src) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = src;
    });
  }

  async function compressImage(file, maxSize, quality) {
    const dataUrl = await readFile(file);
    const img = await loadImage(dataUrl);

    let { width, height } = img;
    if (width > maxSize || height > maxSize) {
      const scale = Math.min(maxSize / width, maxSize / height);
      width  = Math.round(width  * scale);
      height = Math.round(height * scale);
    }

    const canvas = document.createElement('canvas');
    canvas.width  = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    // Fondo blanco por si la imagen original es PNG transparente
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(0, 0, width, height);
    ctx.drawImage(img, 0, 0, width, height);

    const blob = await new Promise(r => canvas.toBlob(r, 'image/jpeg', quality));
    if (!blob) return null;

    const baseName = file.name.replace(/\.[^.]+$/, '') || 'imagen';
    return new File([blob], baseName + '.jpg', {
      type: 'image/jpeg',
      lastModified: Date.now(),
    });
  }

  function attach(input) {
    if (input.dataset.compressBound === '1') return;
    input.dataset.compressBound = '1';

    const maxSize = parseInt(input.dataset.compressMax || '1200', 10);
    const quality = parseFloat(input.dataset.compressQuality || '0.85');
    let processing = false;

    input.addEventListener('change', async function () {
      if (processing) return;
      const file = input.files && input.files[0];
      if (!file || !file.type.startsWith('image/')) return;
      // Si ya es chica, no toca
      if (file.size < 200 * 1024) return;

      processing = true;
      input.disabled = true;
      try {
        const compressed = await compressImage(file, maxSize, quality);
        if (!compressed) return;
        const dt = new DataTransfer();
        dt.items.add(compressed);
        input.files = dt.files;
        // Re-disparar change para que previews/handlers se actualicen
        input.dispatchEvent(new Event('change', { bubbles: true }));
      } catch (e) {
        console.warn('No se pudo comprimir la imagen, se sube original.', e);
      } finally {
        processing = false;
        input.disabled = false;
      }
    }, { capture: true });
  }

  function init() {
    document.querySelectorAll('input[type="file"][data-compress]').forEach(attach);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Re-bind para inputs montados después (htmx, modales, etc.)
  document.addEventListener('htmx:load', init);
})();
