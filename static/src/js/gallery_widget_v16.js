// sat/static/src/js/gallery_widget_v16.js
// Galería: cámara continua + lote + pCloud directo + eliminar + visor con zoom + compartir + modales propios
(function () {
  'use strict';

  // --- Se ejecuta SOLO en /gallery/<id> ---
  document.addEventListener('DOMContentLoaded', function () {
    const path = window.location.pathname;
    if (!/^\/gallery\/\d+\/?$/.test(path)) return;
    galleryApp.init();
  });

  const galleryApp = {
    // ---- estado ----
    capturedPhotos: [],           // [{file, previewUrl, name, size}]
    reparacionId: null,
    continuousMode: true,         // reabrir cámara tras cada captura
    uploadingBatch: false,
    viewer: { list: null, index: 0 },

    // ---- elementos ----
    els: {},

    // ---------------- init ----------------
    init() {
      this.reparacionId = Number(location.pathname.split('/').filter(Boolean).pop());
      this.qs();
      this.ensureAuxUI();
      this.bindEvents();
      this.initializeCameraSession();
    },

    qs() {
      this.els.cameraBtn        = document.getElementById('cameraBtn');
      this.els.cameraInput      = document.getElementById('cameraCapture');
      this.els.photoGrid        = document.getElementById('photoGrid');
      this.els.loading          = document.getElementById('loadingOverlay');
      this.els.shareGalleryBtn  = document.getElementById('shareGalleryBtn');
      // modal visor
      this.els.modal       = document.getElementById('slideshowModal');
      this.els.modalImg    = document.getElementById('slideshowImage');
      this.els.modalClose  = document.getElementById('slideshowClose');
      this.els.modalPrev   = document.getElementById('slideshowPrev');
      this.els.modalNext   = document.getElementById('slideshowNext');
      // modal genérico
      this.els.appModal        = document.getElementById('appModal');
      this.els.appModalIcon    = document.getElementById('appModalIcon');
      this.els.appModalTitle   = document.getElementById('appModalTitle');
      this.els.appModalMessage = document.getElementById('appModalMessage');
      this.els.appModalOk      = document.getElementById('appModalOk');
      this.els.appModalCancel  = document.getElementById('appModalCancel');
    },

    ensureAuxUI() {
      // Barra de lote
      let header = document.querySelector('.header-card .action-buttons') ||
                   document.querySelector('.header-card') ||
                   document.body;

      let batchBar = document.getElementById('batchBar');
      if (!batchBar) {
        batchBar = document.createElement('div');
        batchBar.id = 'batchBar';
        batchBar.className = 'd-flex flex-wrap align-items-center gap-2 mt-2';
        header.appendChild(batchBar);
      }

      // toggle modo continuo
      let toggle = document.getElementById('toggleContinuous');
      if (!toggle) {
        toggle = document.createElement('button');
        toggle.id = 'toggleContinuous';
        toggle.className = 'btn btn-outline-secondary btn-sm';
        toggle.title = 'Modo continuo';
        toggle.innerHTML = '<i class="fa-solid fa-repeat"></i> Continuo';
        batchBar.appendChild(toggle);
      }
      this.els.toggleContinuous = toggle;

      // indicador cola
      let badge = document.getElementById('batchCount');
      if (!badge) {
        badge = document.createElement('span');
        badge.id = 'batchCount';
        badge.className = 'badge bg-secondary';
        badge.textContent = 'Lote: 0';
        batchBar.appendChild(badge);
      }
      this.els.batchCount = badge;

      // enviar lote
      let sendBtn = document.getElementById('sendBatch');
      if (!sendBtn) {
        sendBtn = document.createElement('button');
        sendBtn.id = 'sendBatch';
        sendBtn.className = 'btn btn-success btn-sm';
        sendBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> Enviar';
        sendBtn.disabled = true;
        batchBar.appendChild(sendBtn);
      }
      this.els.sendBatch = sendBtn;

      // descartar lote
      let clearBtn = document.getElementById('clearBatch');
      if (!clearBtn) {
        clearBtn = document.createElement('button');
        clearBtn.id = 'clearBatch';
        clearBtn.className = 'btn btn-outline-danger btn-sm';
        clearBtn.innerHTML = '<i class="fa-solid fa-trash"></i> Limpiar';
        clearBtn.disabled = true;
        batchBar.appendChild(clearBtn);
      }
      this.els.clearBatch = clearBtn;

      // tira de miniaturas pendientes
      let strip = document.getElementById('pendingStrip');
      if (!strip) {
        strip = document.createElement('div');
        strip.id = 'pendingStrip';
        strip.className = 'd-flex flex-nowrap overflow-auto gap-2 py-2';
        const headerCard = document.querySelector('.header-card');
        (headerCard || document.body).appendChild(strip);
      }
      this.els.pendingStrip = strip;

      // Si el template NO trae modal de visor, lo creamos
      if (!this.els.modal) {
        const m = document.createElement('div');
        m.id = 'slideshowModal';
        m.className = 'slideshow-modal';
        m.innerHTML = `
          <div class="slideshow-content">
            <button id="slideshowClose" class="slideshow-close" title="Cerrar"><i class="fa-solid fa-xmark"></i></button>
            <button id="slideshowPrev" class="slideshow-prev" title="Anterior"><i class="fa-solid fa-chevron-left"></i></button>
            <div class="slideshow-image-container">
              <img id="slideshowImage" alt="Foto" style="cursor:grab;">
            </div>
            <button id="slideshowNext" class="slideshow-next" title="Siguiente"><i class="fa-solid fa-chevron-right"></i></button>
          </div>
        `;
        document.body.appendChild(m);
        this.els.modal = m;
        this.els.modalImg = m.querySelector('#slideshowImage');
        this.els.modalClose = m.querySelector('#slideshowClose');
        this.els.modalPrev  = m.querySelector('#slideshowPrev');
        this.els.modalNext  = m.querySelector('#slideshowNext');
      }
      this._attachZoomHandlers();
    },

    bindEvents() {
      // Botón cámara
      if (this.els.cameraBtn) {
        this.els.cameraBtn.addEventListener('click', () => {
          this.els.cameraInput?.click();
        });
      }
      
      // Input cámara
      if (this.els.cameraInput) {
        this.els.cameraInput.setAttribute('accept', 'image/*');
        this.els.cameraInput.setAttribute('capture', 'environment');
        this.els.cameraInput.addEventListener('change', (e) => this.handleCameraCapture(e));
      }

      // Compartir galería
      if (this.els.shareGalleryBtn) {
        this.els.shareGalleryBtn.addEventListener('click', () => this.handleShareGallery());
      }
      
      // Toggle continuo
      if (this.els.toggleContinuous) {
        this.els.toggleContinuous.addEventListener('click', () => {
          this.continuousMode = !this.continuousMode;
          this.els.toggleContinuous.classList.toggle('btn-outline-secondary',  this.continuousMode);
          this.els.toggleContinuous.classList.toggle('btn-secondary',         !this.continuousMode);
          this.els.toggleContinuous.innerHTML = this.continuousMode
            ? '<i class="fa-solid fa-repeat"></i> Continuo'
            : '<i class="fa-solid fa-hand"></i> Manual';
        });
      }
      
      // Enviar / Descartar lote
      this.els.sendBatch?.addEventListener('click', () => this.uploadBatch());
      this.els.clearBatch?.addEventListener('click', () => this.clearPending());

      // Visor, compartir y eliminar en grid existente
      this.els.photoGrid?.addEventListener('click', (e) => {
        // Abrir visor
        const cont = e.target.closest('[data-open-viewer="1"]');
        if (cont) {
          const fotoCard = cont.closest('.photo-card');
          const fotoId = fotoCard?.getAttribute('data-foto-id');
          const downloadUrl = cont.getAttribute('data-download-url');
          if (downloadUrl) this.openViewer(fotoId, downloadUrl);
          return;
        }

        // Compartir / copiar enlace de foto
        const shareBtn = e.target.closest('.btn-share-photo');
        if (shareBtn) {
          this.handleShareClick(shareBtn);
          return;
        }

        // Eliminar
        const delBtn = e.target.closest('.btn-delete-photo');
        if (delBtn) this.handleDeleteClick(e);
      });

      // Controles del modal de visor
      this.els.modalClose?.addEventListener('click', () => this.closeViewer());
      this.els.modalPrev ?.addEventListener('click', () => this.navigateViewer(-1));
      this.els.modalNext ?.addEventListener('click', () => this.navigateViewer(1));
      this.els.modal?.addEventListener('click', (e) => {
        if (e.target === this.els.modal) this.closeViewer();
      });
    },

    // --------------- auth ---------------
    async ensureAuthOrRedirect() {
      try {
        const r = await fetch('/web/session/check', { method: 'POST' });
        const data = await r.json();
        if (data?.success && data?.is_authenticated) return true;
      } catch (e) {
        console.error('Error checking session:', e);
      }
      const redirect = `/web/login?redirect=${encodeURIComponent(location.pathname)}`;
      window.location.href = redirect;
      return false;
    },

    // ---------------- bootstrapping ----------------
    initializeCameraSession() {
      this.capturedPhotos = [];
      this.updateBatchUI();
    },

    // --------------- captura & cola ---------------
    async compressImage(file, maxMB = 5, quality = 0.85) {
      return new Promise((resolve) => {
        const img = new Image();
        img.onload = () => {
          const canvas = document.createElement('canvas');
          const ctx = canvas.getContext('2d');
          let { width, height } = img;
          const maxDim = 1600;
          if (width > height) {
            if (width > maxDim) { height = Math.round(height * (maxDim / width)); width = maxDim; }
          } else {
            if (height > maxDim) { width = Math.round(width * (maxDim / height)); height = maxDim; }
          }
          canvas.width = width; 
          canvas.height = height;
          ctx.drawImage(img, 0, 0, width, height);
          canvas.toBlob((blob) => {
            const name = (file.name || `image_${Date.now()}.jpg`).replace(/\s+/g, '_');
            const f = new File([blob], name, { type: 'image/jpeg', lastModified: Date.now() });
            resolve(f);
          }, 'image/jpeg', quality);
        };
        img.src = URL.createObjectURL(file);
      });
    },

    async handleCameraCapture(e) {
      const files = Array.from(e.target.files || []);
      if (!files.length) return;
      
      const inputFile = files[0];
      this.showLoading(true, 'Comprimiendo imagen...');
      
      try {
        const compressed = await this.compressImage(inputFile, 5, 0.85);
        this.enqueue(compressed);
      } catch (error) {
        console.error('Error comprimiendo imagen:', error);
        await this.showModal({
          title: 'Error',
          message: 'Ocurrió un problema al procesar la imagen.',
          variant: 'error',
        });
      } finally {
        this.showLoading(false);
      }

      // reabrir cámara si está activo el modo continuo
      this.els.cameraInput.value = '';
      if (this.continuousMode) {
        setTimeout(() => this.els.cameraInput.click(), 500);
      }
    },

    enqueue(file) {
      const previewUrl = URL.createObjectURL(file);
      this.capturedPhotos.push({ file, previewUrl, name: file.name, size: file.size });
      this.renderPendingItem(this.capturedPhotos.length - 1);
      this.updateBatchUI();
    },

    renderPendingItem(idx) {
      if (!this.els.pendingStrip) return;
      const item = this.capturedPhotos[idx];
      const wrap = document.createElement('div');
      wrap.className = 'pending-item position-relative';
      wrap.style.cssText = 'width:80px;height:80px;border-radius:8px;overflow:hidden;box-shadow:0 2px 4px rgba(0,0,0,.12);flex-shrink:0;';
      wrap.dataset.idx = String(idx);

      const img = document.createElement('img');
      img.src = item.previewUrl;
      img.alt = item.name || 'foto';
      img.style.cssText = 'width:100%;height:100%;object-fit:cover;cursor:zoom-in;';
      img.addEventListener('click', () => this.openTempZoom(img.src));

      const rm = document.createElement('button');
      rm.type = 'button';
      rm.title = 'Quitar de lote';
      rm.className = 'btn btn-sm btn-danger position-absolute';
      rm.style.cssText = 'right:4px;top:4px;padding:2px 6px;line-height:1;';
      rm.innerHTML = '<i class="fa-solid fa-xmark"></i>';
      rm.addEventListener('click', () => this.removePending(wrap));

      wrap.appendChild(img);
      wrap.appendChild(rm);
      this.els.pendingStrip.appendChild(wrap);
    },

    removePending(wrap) {
      const idx = parseInt(wrap.dataset.idx || '-1', 10);
      if (idx >= 0 && idx < this.capturedPhotos.length) {
        try { URL.revokeObjectURL(this.capturedPhotos[idx].previewUrl); } catch (e) {}
      }
      this.capturedPhotos = this.capturedPhotos.filter((_, i) => i !== idx);
      this.rebuildPendingStrip();
      this.updateBatchUI();
    },

    rebuildPendingStrip() {
      if (!this.els.pendingStrip) return;
      this.els.pendingStrip.innerHTML = '';
      this.capturedPhotos.forEach((_, i) => this.renderPendingItem(i));
    },

    clearPending() {
      this.capturedPhotos.forEach(p => { try { URL.revokeObjectURL(p.previewUrl); } catch (e) {} });
      this.capturedPhotos = [];
      this.rebuildPendingStrip();
      this.updateBatchUI();
    },

    updateBatchUI() {
      const n = this.capturedPhotos.length;
      if (this.els.batchCount) this.els.batchCount.textContent = `Lote: ${n}`;
      if (this.els.sendBatch)  this.els.sendBatch.disabled  = (n === 0 || this.uploadingBatch);
      if (this.els.clearBatch) this.els.clearBatch.disabled = (n === 0 || this.uploadingBatch);
    },

    showLoading(show, text) {
      if (!this.els.loading) return;
      if (text) this.els.loading.textContent = text;
      this.els.loading.classList.toggle('hidden', !show);
    },

    // --------------- subida DIRECTA ---------------
    async uploadBatch() {
      if (!(await this.ensureAuthOrRedirect())) return;

      if (this.uploadingBatch || this.capturedPhotos.length === 0) return;

      this.uploadingBatch = true;
      this.updateBatchUI();
      this.showLoading(true, 'Subiendo lote...');

      try {

        const uploads = this.capturedPhotos.map(item =>
          this.uploadOneDirectToPcloud(item.file)
        );

        await Promise.all(uploads);

        this.clearPending();

        await this.showModal({
          title: 'Lote subido',
          message: 'Las fotos fueron subidas correctamente.',
          variant: 'success',
        });

        setTimeout(() => window.location.reload(), 400);

      } catch (e) {
        console.error('Error en subida por lotes', e);
      } finally {
        this.uploadingBatch = false;
        this.updateBatchUI();
        this.showLoading(false);
      }
    },

    async uploadOneDirectToPcloud(file) {

      try {

        const fd = new FormData();
        fd.append('file', file);

        const url = `/gallery/pcloud/upload-direct/${this.reparacionId}`;

        const resp = await fetch(url, {
          method: 'POST',
          body: fd
        });

        if (!resp.ok) {
          const errorText = await resp.text();
          throw new Error(`HTTP ${resp.status}: ${errorText}`);
        }

        const result = await resp.json();

        if (!result.success) {
          throw new Error(result.error || 'Error desconocido al subir');
        }

        console.log('✓ Subida exitosa:', result);

        return result;

      } catch (error) {

        console.error('Error en uploadOneDirectToPcloud:', error);

        throw error;

      }
    },

   

    // --------------- UI: grid existente ---------------
    appendPhotoCard(f) {
      if (!this.els.photoGrid || !f) return;
      const div = document.createElement('div');
      div.className = 'photo-card';
      div.setAttribute('data-foto-id', f.id);
      div.innerHTML = `
        <div class="photo-container" data-open-viewer="1" data-download-url="/gallery/download/${f.id}">
          <span class="photo-badge"><i class="fa-solid fa-image"></i> Foto</span>
          <img src="${f.thumb_url || ('/gallery/preview/' + f.id)}" alt="Foto" loading="lazy"/>
        </div>
        <div class="photo-info">
          <span>#${f.sequence || 0} — ${this.escapeHtml(f.nombre_foto || '')}</span>
          <div class="d-flex gap-2">
            <button type="button"
                    class="btn btn-sm btn-outline-secondary btn-share-photo"
                    data-download-url="/gallery/download/${f.id}"
                    title="Compartir / Copiar enlace">
              <i class="fa-solid fa-share-nodes"></i>
            </button>
            <a class="btn btn-sm btn-outline-secondary" href="/gallery/download/${f.id}" target="_blank" title="Descargar">
              <i class="fa-solid fa-download"></i>
            </a>
            <button type="button" class="btn btn-sm btn-outline-danger btn-delete-photo" title="Eliminar">
              <i class="fa-solid fa-trash"></i>
            </button>
          </div>
        </div>`;
      this.els.photoGrid.prepend(div);
    },

    // --------------- eliminar ---------------
    async handleDeleteClick(e) {
      if (!(await this.ensureAuthOrRedirect())) return;

      const card = e.target.closest('.photo-card');
      const fotoId = card?.getAttribute('data-foto-id');
      if (!fotoId) return;

      const confirm = await this.showModal({
        title: 'Eliminar foto',
        message: '¿Seguro que deseas eliminar esta foto?',
        variant: 'warning',
        showCancel: true,
      });
      if (!confirm) return;

      try {
        const res = await fetch(`/gallery/delete/${fotoId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
        const j = await res.json().catch(() => null);
        if (j?.success) {
          card.remove();
          await this.showModal({
            title: 'Foto eliminada',
            message: 'La foto se eliminó correctamente.',
            variant: 'success',
          });
        } else {
          await this.showModal({
            title: 'No se pudo eliminar',
            message: j?.error || 'Ocurrió un error al eliminar la foto.',
            variant: 'error',
          });
        }
      } catch (err) {
        console.error('Error eliminando la foto', err);
        await this.showModal({
          title: 'Error',
          message: 'Error al intentar eliminar la foto.',
          variant: 'error',
        });
      }
    },

    // --------------- compartir galería ---------------
    async handleShareGallery() {
      const url = location.href.split('#')[0];
      try {
        // Web Share API donde esté disponible
        if (navigator.share) {
          await navigator.share({
            title: document.title || 'Galería de Fotos',
            text: 'Te comparto la galería de fotos.',
            url: url,
          });
          return;
        }

        // Copiar al portapapeles
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(url);
        } else {
          const temp = document.createElement('input');
          temp.value = url;
          document.body.appendChild(temp);
          temp.select();
          document.execCommand('copy');
          document.body.removeChild(temp);
        }

        await this.showModal({
          title: 'URL Copiada',
          message: 'El enlace de la galería ha sido copiado al portapapeles.',
          variant: 'success',
        });
      } catch (err) {
        console.error('Error al compartir galería', err);
        await this.showModal({
          title: 'Error',
          message: 'No se pudo compartir/copiar la URL de la galería.',
          variant: 'error',
        });
      }
    },

    // --------------- compartir / copiar url de foto ---------------
    async handleShareClick(btn) {
      try {
        const relUrl = btn.getAttribute('data-download-url');
        if (!relUrl) return;

        const fullUrl = location.origin + relUrl;

        // Web Share API (móviles / navegadores modernos)
        if (navigator.share) {
          await navigator.share({
            title: 'Foto de la reparación',
            text: 'Te comparto esta foto de la reparación.',
            url: fullUrl,
          });
          return;
        }

        // Copiar al portapapeles
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(fullUrl);
        } else {
          // Fallback básico
          const temp = document.createElement('input');
          temp.value = fullUrl;
          document.body.appendChild(temp);
          temp.select();
          document.execCommand('copy');
          document.body.removeChild(temp);
        }

        await this.showModal({
          title: 'URL Copiada',
          message: 'El enlace de la foto ha sido copiado al portapapeles.',
          variant: 'success',
        });
      } catch (err) {
        console.error('Error al compartir/copiar enlace', err);
        await this.showModal({
          title: 'Error',
          message: 'No se pudo compartir/copiar el enlace de la foto.',
          variant: 'error',
        });
      }
    },

    // --------------- Visor con zoom ---------------
    openViewer(fotoId, url) {
      this.viewer.list = Array.from(document.querySelectorAll('.photo-card'));
      this.viewer.index = this.viewer.list.findIndex(c => c.getAttribute('data-foto-id') === String(fotoId));
      if (this.viewer.index < 0) this.viewer.index = 0;

      this._resetZoom();
      if (this.els.modalImg) this.els.modalImg.src = url;
      if (this.els.modal) {
        this.els.modal.classList.add('show');
        document.body.style.overflow = 'hidden';
      }
    },

    closeViewer() {
      if (this.els.modal) {
        this.els.modal.classList.remove('show');
        document.body.style.overflow = '';
      }
    },

    navigateViewer(delta) {
      if (!this.viewer.list?.length) return;
      this.viewer.index = (this.viewer.index + delta + this.viewer.list.length) % this.viewer.list.length;
      const card = this.viewer.list[this.viewer.index];
      const cont = card.querySelector('[data-open-viewer="1"]');
      const full = cont?.getAttribute('data-download-url');
      this._resetZoom();
      if (full && this.els.modalImg) this.els.modalImg.src = full;
    },

    openTempZoom(src) {
      this.openViewer('pending', src);
    },

    _attachZoomHandlers() {
      if (!this.els.modalImg) return;
      const img = this.els.modalImg;
      let scale = 1, originX = 0, originY = 0, lastX = 0, lastY = 0, dragging = false;

      const apply = () => {
        img.style.transform = `translate(${originX}px, ${originY}px) scale(${scale})`;
      };
      const clampScale = (s) => Math.min(6, Math.max(1, s));

      img.addEventListener('wheel', (e) => {
        e.preventDefault();
        const delta = e.deltaY < 0 ? 0.1 : -0.1;
        scale = clampScale(scale + delta);
        apply();
      }, { passive: false });

      img.addEventListener('mousedown', (e) => {
        dragging = true;
        img.style.cursor = 'grabbing';
        lastX = e.clientX;
        lastY = e.clientY;
      });

      window.addEventListener('mousemove', (e) => {
        if (!dragging) return;
        originX += (e.clientX - lastX);
        originY += (e.clientY - lastY);
        lastX = e.clientX;
        lastY = e.clientY;
        apply();
      });

      window.addEventListener('mouseup', () => {
        dragging = false;
        img.style.cursor = 'grab';
      });

      // touch (pinch básico + pan)
      let touchStartDist = 0;
      const getDist = (t1, t2) => Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);

      img.addEventListener('touchstart', (e) => {
        if (e.touches.length === 2) {
          touchStartDist = getDist(e.touches[0], e.touches[1]);
        } else if (e.touches.length === 1) {
          lastX = e.touches[0].clientX;
          lastY = e.touches[0].clientY;
        }
      }, { passive: false });

      img.addEventListener('touchmove', (e) => {
        e.preventDefault();
        if (e.touches.length === 2) {
          const d = getDist(e.touches[0], e.touches[1]);
          const factor = (d - touchStartDist) / 200;
          scale = clampScale(scale + factor);
          touchStartDist = d;
          apply();
        } else if (e.touches.length === 1) {
          const tx = e.touches[0].clientX, ty = e.touches[0].clientY;
          originX += (tx - lastX);
          originY += (ty - lastY);
          lastX = tx; 
          lastY = ty;
          apply();
        }
      }, { passive: false });

      img.addEventListener('dblclick', () => {
        if (scale === 1) { 
          scale = 2; 
        } else { 
          scale = 1; 
          originX = 0; 
          originY = 0; 
        }
        apply();
      });

      this._resetZoom = function () {
        scale = 1; 
        originX = 0; 
        originY = 0; 
        apply();
      };
    },

    _resetZoom() {},

    // --------------- modal genérico ---------------
    /**
     * options: { title, message, variant: 'success'|'error'|'warning'|'info', showCancel: bool }
     * return: Promise<boolean>  -> true = aceptar, false = cancelar/cerrar
     */
    showModal(options) {
      const modal = this.els.appModal;
      if (!modal) {
        // fallback muy básico si algo falla
        if (options.showCancel) {
          const result = window.confirm(options.title + '\n\n' + options.message);
          return Promise.resolve(!!result);
        } else {
          window.alert(options.title + '\n\n' + options.message);
          return Promise.resolve(true);
        }
      }

      const icon = this.els.appModalIcon;
      const titleEl = this.els.appModalTitle;
      const msgEl = this.els.appModalMessage;
      const okBtn = this.els.appModalOk;
      const cancelBtn = this.els.appModalCancel;

      const variant = options.variant || 'info';
      icon.classList.remove('success', 'error', 'warning');
      if (variant === 'success') icon.classList.add('success');
      else if (variant === 'error') icon.classList.add('error');
      else if (variant === 'warning') icon.classList.add('warning');
      else icon.classList.add('success'); // por defecto

      titleEl.textContent = options.title || '';
      msgEl.textContent = options.message || '';

      if (options.showCancel) {
        cancelBtn.style.display = 'inline-flex';
      } else {
        cancelBtn.style.display = 'none';
      }

      return new Promise((resolve) => {
        const close = (value) => {
          modal.classList.remove('show');
          modal.setAttribute('aria-hidden', 'true');
          okBtn.removeEventListener('click', onOk);
          cancelBtn.removeEventListener('click', onCancel);
          modal.removeEventListener('click', onBackdrop);
          resolve(value);
        };

        const onOk = () => close(true);
        const onCancel = () => close(false);
        const onBackdrop = (e) => {
          if (e.target === modal && options.showCancel) {
            close(false);
          }
        };

        okBtn.addEventListener('click', onOk);
        cancelBtn.addEventListener('click', onCancel);
        modal.addEventListener('click', onBackdrop);

        modal.classList.add('show');
        modal.setAttribute('aria-hidden', 'false');
      });
    },

    // --------------- util ---------------
    escapeHtml(str) {
      return String(str).replace(/[&<>"']/g, function (m) {
        return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[m];
      });
    },
  };
})();
