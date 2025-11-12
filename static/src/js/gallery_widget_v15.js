// sat/static/src/js/gallery.js
// Galería: cámara continua + lote + pCloud directo + eliminar + visor con zoom
(function () {
  'use strict';

  // --- Se ejecuta SOLO en /gallery/<id> ---
  document.addEventListener('DOMContentLoaded', function () {
    const path = window.location.pathname;
    if (!/^\/gallery\/\d+\/?$/.test(path)) return; // no invadir otras vistas

    galleryApp.init();
  });

  const galleryApp = {
    // ---- estado ----
    capturedPhotos: [],           // [{file, previewUrl, name, size}]
    currentSession: null,         // id de sesión (fallback)
    pcloudUploadUrl: null,        // https://api.pcloud.com/uploadtolink?code=...
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
      this.bootstrapSession(); // valida y obtiene upload link
    },

    qs() {
      this.els.cameraBtn   = document.getElementById('cameraBtn');
      this.els.cameraInput = document.getElementById('cameraCapture');
      this.els.photoGrid   = document.getElementById('photoGrid');
      this.els.loading     = document.getElementById('loadingOverlay');
      // modal visor (si el template ya lo trae)
      this.els.modal       = document.getElementById('slideshowModal');
      this.els.modalImg    = document.getElementById('slideshowImage');
      this.els.modalClose  = document.getElementById('slideshowClose');
      this.els.modalPrev   = document.getElementById('slideshowPrev');
      this.els.modalNext   = document.getElementById('slideshowNext');
    },

    ensureAuxUI() {
      // Barra de lote (pendientes + acciones), se inserta al lado de los botones si existen
      let header = document.querySelector('.header-card .action-buttons') ||
                   document.querySelector('.header-card') ||
                   document.body;

      // contenedor de cola
      let batchBar = document.getElementById('batchBar');
      if (!batchBar) {
        batchBar = document.createElement('div');
        batchBar.id = 'batchBar';
        batchBar.style.display = 'flex';
        batchBar.style.flexWrap = 'wrap';
        batchBar.style.alignItems = 'center';
        batchBar.style.gap = '8px';
        batchBar.style.marginLeft = '8px';
        header.appendChild(batchBar);
      }

      // toggle modo continuo
      let toggle = document.getElementById('toggleContinuous');
      if (!toggle) {
        toggle = document.createElement('button');
        toggle.id = 'toggleContinuous';
        toggle.className = 'btn btn-outline-secondary';
        toggle.title = 'Modo continuo';
        toggle.innerHTML = '<i class="fa-solid fa-repeat"></i> Modo continuo';
        batchBar.appendChild(toggle);
        this.els.toggleContinuous = toggle;
      } else {
        this.els.toggleContinuous = toggle;
      }

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
        sendBtn.className = 'btn btn-success';
        sendBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> Enviar lote';
        sendBtn.disabled = true;
        batchBar.appendChild(sendBtn);
      }
      this.els.sendBatch = sendBtn;

      // descartar lote
      let clearBtn = document.getElementById('clearBatch');
      if (!clearBtn) {
        clearBtn = document.createElement('button');
        clearBtn.id = 'clearBatch';
        clearBtn.className = 'btn btn-outline-danger';
        clearBtn.innerHTML = '<i class="fa-solid fa-trash"></i> Descartar';
        clearBtn.disabled = true;
        batchBar.appendChild(clearBtn);
      }
      this.els.clearBatch = clearBtn;

      // tira de miniaturas pendientes
      let strip = document.getElementById('pendingStrip');
      if (!strip) {
        strip = document.createElement('div');
        strip.id = 'pendingStrip';
        strip.style.display = 'flex';
        strip.style.flexWrap = 'nowrap';
        strip.style.overflowX = 'auto';
        strip.style.gap = '8px';
        strip.style.padding = '8px 0';
        const headerCard = document.querySelector('.header-card');
        (headerCard || document.body).appendChild(strip);
      }
      this.els.pendingStrip = strip;

      // Si el template NO trae modal, creamos uno simple con zoom
      if (!this.els.modal) {
        const m = document.createElement('div');
        m.id = 'slideshowModal';
        m.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.8);display:none;align-items:center;justify-content:center;z-index:1050;';
        m.innerHTML = `
          <button id="slideshowClose" class="btn btn-light" style="position:absolute;top:12px;right:12px;">Cerrar</button>
          <button id="slideshowPrev"  class="btn btn-light" style="position:absolute;left:12px;top:50%;">‹</button>
          <button id="slideshowNext"  class="btn btn-light" style="position:absolute;right:12px;top:50%;">›</button>
          <img id="slideshowImage" alt="Foto" style="max-width:90vw;max-height:85vh;cursor:grab;transform-origin:center center;">
        `;
        document.body.appendChild(m);
        this.els.modal = m;
        this.els.modalImg = m.querySelector('#slideshowImage');
        this.els.modalClose = m.querySelector('#slideshowClose');
        this.els.modalPrev  = m.querySelector('#slideshowPrev');
        this.els.modalNext  = m.querySelector('#slideshowNext');
        this._attachZoomHandlers();
      } else {
        this._attachZoomHandlers();
      }
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
      // Toggle continuo
      if (this.els.toggleContinuous) {
        this.els.toggleContinuous.addEventListener('click', () => {
          this.continuousMode = !this.continuousMode;
          this.els.toggleContinuous.classList.toggle('btn-outline-secondary',  this.continuousMode);
          this.els.toggleContinuous.classList.toggle('btn-secondary',         !this.continuousMode);
          this.els.toggleContinuous.innerHTML = this.continuousMode
            ? '<i class="fa-solid fa-repeat"></i> Modo continuo'
            : '<i class="fa-solid fa-hand"></i> Modo manual';
        });
      }
      // Enviar / Descartar lote
      this.els.sendBatch?.addEventListener('click', () => this.uploadBatch());
      this.els.clearBatch?.addEventListener('click', () => this.clearPending());

      // Visor y eliminar en grid existente
      this.els.photoGrid?.addEventListener('click', (e) => {
        const cont = e.target.closest('[data-open-viewer="1"]');
        if (cont) {
          const fotoCard = cont.closest('.photo-card');
          const fotoId = fotoCard?.getAttribute('data-foto-id');
          const downloadUrl = cont.getAttribute('data-download-url');
          if (downloadUrl) this.openViewer(fotoId, downloadUrl);
          return;
        }
        const delBtn = e.target.closest('.btn-delete-photo');
        if (delBtn) this.handleDeleteClick(e);
      });

      // Controles del modal
      this.els.modalClose?.addEventListener('click', () => this.closeViewer());
      this.els.modalPrev ?.addEventListener('click', () => this.navigateViewer(-1));
      this.els.modalNext ?.addEventListener('click', () => this.navigateViewer(1));
      this.els.modal?.addEventListener('click', (e) => {
        // cerrar si click fuera de la imagen
        if (e.target === this.els.modal) this.closeViewer();
      });
    },

    // --------------- auth ---------------
    async ensureAuthOrRedirect() {
      try {
        const r = await fetch('/web/session/check', { method: 'POST' });
        const data = await r.json();
        if (data?.success && data?.is_authenticated) return true;
      } catch (e) {}
      // redirigir a login SOLO en acciones sensibles
      const redirect = `/web/login?redirect=${encodeURIComponent(location.pathname)}`;
      window.location.href = redirect;
      return false;
    },

    // ---------------- bootstrapping ----------------
    initializeCameraSession() {
      this.capturedPhotos = [];
      this.updateBatchUI();
    },

    async bootstrapSession() {
      // 1) Validación (para fallback)
      try {
        const validateResp = await fetch(`/gallery/upload/validate/${this.reparacionId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ file_count: 0, total_size: 0 })
        });
        const vres = await validateResp.json();
        if (vres?.success) this.currentSession = vres.session_id || null;
      } catch (e) {
        console.warn('validate_upload error', e);
      }

      // 2) Obtener upload link a la carpeta de la reparación
      try {
        const resp = await fetch(`/gallery/pcloud/uploadlink/${this.reparacionId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({})
        });
        const r = await resp.json();
        const data = r.result || r;
        if (data.success && data.endpoint && data.code) {
          this.pcloudUploadUrl = `${data.endpoint}?code=${encodeURIComponent(data.code)}`;
        } else {
          console.warn('No hay upload link (se usará fallback si es necesario):', data.error || data);
        }
      } catch (e) {
        console.warn('get_upload_link error; se usará fallback', e);
      }
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
          canvas.width = width; canvas.height = height;
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
      const compressed = await this.compressImage(inputFile, 5, 0.85);
      this.enqueue(compressed);

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
      wrap.className = 'pending-item';
      wrap.style.position = 'relative';
      wrap.style.width = '72px';
      wrap.style.height = '72px';
      wrap.style.borderRadius = '8px';
      wrap.style.overflow = 'hidden';
      wrap.style.boxShadow = '0 2px 4px rgba(0,0,0,.12)';
      wrap.dataset.idx = String(idx);

      const img = document.createElement('img');
      img.src = item.previewUrl;
      img.alt = item.name || 'foto';
      img.style.width = '100%';
      img.style.height = '100%';
      img.style.objectFit = 'cover';
      img.style.cursor = 'zoom-in';
      img.addEventListener('click', () => this.openTempZoom(img.src));

      const rm = document.createElement('button');
      rm.type = 'button';
      rm.title = 'Quitar de lote';
      rm.className = 'btn btn-sm btn-danger';
      rm.style.position = 'absolute';
      rm.style.right = '4px';
      rm.style.top = '4px';
      rm.style.padding = '2px 6px';
      rm.style.lineHeight = '1';
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

    // --------------- subida ---------------
    async uploadBatch() {
      // Verifica sesión SOLO al intentar subir
      if (!(await this.ensureAuthOrRedirect())) return;

      if (this.uploadingBatch || this.capturedPhotos.length === 0) return;
      this.uploadingBatch = true;
      this.updateBatchUI();
      this.showLoading(true, 'Subiendo lote...');

      try {
        for (let i = 0; i < this.capturedPhotos.length; i++) {
          const item = this.capturedPhotos[i];
          this.showLoading(true, `Subiendo ${i + 1}/${this.capturedPhotos.length}...`);
          await this.uploadOne(item.file);
        }
        this.clearPending();
      } catch (e) {
        console.error('Error en subida por lotes', e);
        alert('Ocurrió un error subiendo el lote: ' + (e.message || e));
      } finally {
        this.uploadingBatch = false;
        this.updateBatchUI();
        this.showLoading(false);
      }
    },

    async uploadOne(file) {
      try {
        const seq = await this.getNextSequence();
        const up = await this.uploadDirectToPcloud(file); // lanza si falla
        const reg = await this.registerUploaded(up.pcloud, file.name, file.size, seq);
        if (reg?.id) {
          // Pintar tarjeta nueva (respuesta de /register devuelve id y thumb_url)
          this.appendPhotoCard({
            id: reg.id,
            sequence: seq,
            nombre_foto: file.name,
            thumb_url: reg.thumb_url || `/gallery/preview/${reg.id}`
          });
        } else if (reg?.foto) {
          this.appendPhotoCard(reg.foto);
        }
      } catch (e) {
        // Fallback si no hay upload link o falló
        if (!this.currentSession) throw e;
        const fd = new FormData();
        fd.append('file', file);
        fd.append('sequence', await this.getNextSequence());
        fd.append('reparacion_id', this.reparacionId);
        const r = await fetch(`/gallery/upload/single/${this.currentSession}`, { method: 'POST', body: fd });
        const j = await r.json();
        if (!j?.success) throw new Error(j?.error || 'Fallback falló');
        window.location.reload();
      }
    },

    async uploadDirectToPcloud(file) {
      if (!(await this.ensureAuthOrRedirect())) throw new Error('AUTH_REQUIRED');
      if (!this.pcloudUploadUrl) throw new Error('NO_PCL_UPLOADLINK');

      const fd = new FormData();
      const safeName = (file.name || `image_${Date.now()}.jpg`).replace(/\s+/g, '_');
      fd.append('file', file, safeName);
      const url = this.pcloudUploadUrl.includes('?') ? `${this.pcloudUploadUrl}&renameifexists=1` : `${this.pcloudUploadUrl}?renameifexists=1`;

      const resp = await fetch(url, { method: 'POST', body: fd });
      if (!resp.ok) throw new Error(`PCLOUD_UPLOAD:${resp.status}`);

      let data = {};
      try { data = await resp.json(); } catch (e) {}
      if (data.result !== 0) throw new Error(data.error || 'pCloud devolvió error');
      const meta = Array.isArray(data.metadata) ? data.metadata[0] : null;
      const fileid = meta?.fileid || (Array.isArray(data.fileids) ? data.fileids[0] : null);
      if (!fileid) throw new Error('No se obtuvo fileid de pCloud');

      return {
        success: true,
        pcloud: {
          fileid: String(fileid),
          size: meta?.size || file.size || 0,
          contenttype: meta?.contenttype || file.type || 'image/jpeg'
        }
      };
    },

    async registerUploaded(pcloudMeta, filename, size, sequence) {
      const payload = {
        reparacion_id: Number(this.reparacionId),
        sequence: Number(sequence || 0),
        filename: filename || 'foto.jpg',
        pcloud: {
          fileid: pcloudMeta.fileid,
          size: Number(pcloudMeta.size || size || 0),
          contenttype: pcloudMeta.contenttype || 'image/jpeg'
        }
      };
      const r = await fetch('/gallery/pcloud/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const j = await r.json();
      if (!j?.success) throw new Error(j?.error || 'Registro falló');
      return j;
    },

    async getNextSequence() {
      const r = await fetch(`/gallery/next-sequence/${this.reparacionId}`);
      const j = await r.json();
      const res = j.result || j;
      return res.next_sequence || 1;
    },

    // --------------- UI: grid existente ---------------
    appendPhotoCard(f) {
      if (!this.els.photoGrid || !f) return;
      const div = document.createElement('div');
      div.className = 'photo-card';
      div.setAttribute('data-foto-id', f.id);
      div.innerHTML = `
        <div class="photo-container" data-open-viewer="1" data-download-url="/gallery/download/${f.id}">
          <span class="photo-badge">Foto</span>
          <img src="${f.thumb_url || ('/gallery/preview/' + f.id)}" alt="Foto"/>
        </div>
        <div class="photo-info">
          <span>#${f.sequence || 0} — ${this.escapeHtml(f.nombre_foto || '')}</span>
          <div class="d-flex gap-2">
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
      // Verifica sesión SOLO al intentar eliminar
      if (!(await this.ensureAuthOrRedirect())) return;

      const btn = e.target.closest('.btn-delete-photo');
      const card = e.target.closest('.photo-card');
      const fotoId = card?.getAttribute('data-foto-id');
      if (!fotoId) return;

      if (!confirm('¿Eliminar esta foto?')) return;

      try {
        const res = await fetch(`/gallery/delete/${fotoId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
        const j = await res.json().catch(() => null);
        if (j?.success) {
          card.remove();
        } else {
          alert(j?.error || 'No se pudo eliminar');
        }
      } catch (err) {
        console.error('Error eliminando la foto', err);
        alert('Error al intentar eliminar');
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
        this.els.modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
      }
    },
    closeViewer() {
      if (this.els.modal) {
        this.els.modal.style.display = 'none';
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
      // zoom rápido al tocar miniatura del lote
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
          const factor = (d - touchStartDist) / 200; // sensibilidad
          scale = clampScale(scale + factor);
          touchStartDist = d;
          apply();
        } else if (e.touches.length === 1) {
          const tx = e.touches[0].clientX, ty = e.touches[0].clientY;
          originX += (tx - lastX);
          originY += (ty - lastY);
          lastX = tx; lastY = ty;
          apply();
        }
      }, { passive: false });

      img.addEventListener('dblclick', () => {
        if (scale === 1) { scale = 2; } else { scale = 1; originX = 0; originY = 0; }
        apply();
      });

      this._resetZoom = function () {
        scale = 1; originX = 0; originY = 0; apply();
      };
    },

    _resetZoom() {},

    // --------------- util ---------------
    escapeHtml(str) {
      return String(str).replace(/[&<>"']/g, function (m) {
        return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[m];
      });
    },
  };
})();
