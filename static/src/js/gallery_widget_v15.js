// sat/static/src/js/gallery.js
// Modo: solo cámara + multi-captura tipo WhatsApp + subida directa a pCloud por lotes
// + registro en Odoo y visor de imagen completa + eliminar fotos
(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    const gallery = {
      // ---- estado ----
      capturedPhotos: [],           // [{file, previewUrl, name, size}...]
      currentSession: null,         // id de sesión para fallback
      pcloudUploadUrl: null,        // URL de POST devuelta por /gallery/pcloud/uploadlink/<id> (uploadtolink completo con ?code=...)
      reparacionId: (function () {
        // intenta extraer el id desde /gallery/<id>
        const parts = window.location.pathname.split('/').filter(Boolean);
        const idx = parts.indexOf('gallery');
        if (idx >= 0 && parts[idx + 1]) return parts[idx + 1];
        // fallback: último segmento numérico
        for (let i = parts.length - 1; i >= 0; i--) {
          if (/^\d+$/.test(parts[i])) return parts[i];
        }
        return null;
      })(),
      continuousMode: true,         // reabrir cámara tras cada captura
      uploadingBatch: false,
      viewerList: null,
      viewerIndex: 0,
      // ---- elementos ----
      els: {},

      // ---------------- init ----------------
      init() {
        this.qs();
        this.ensureAuxUI();
        this.bindEvents();
        this.initializeCameraSession();
        this.bootstrapSession(); // valida sesión y obtiene upload link
      },

      qs() {
        this.els.cameraBtn   = document.getElementById('cameraBtn');
        this.els.cameraInput = document.getElementById('cameraCapture');
        this.els.photoGrid   = document.getElementById('photoGrid');
        this.els.loading     = document.getElementById('loadingOverlay');
        // contenedores auxiliares creados en ensureAuxUI()
      },

      ensureAuxUI() {
        // Barra de lote (pendientes + acciones), se inserta al lado de los botones
        let header = document.querySelector('.header-card .action-buttons');
        if (!header) header = document.querySelector('.header-card') || document.body;

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
        }
        // indicador cola
        let badge = document.getElementById('batchCount');
        if (!badge) {
          badge = document.createElement('span');
          badge.id = 'batchCount';
          badge.className = 'badge bg-secondary';
          badge.textContent = 'Lote: 0';
          batchBar.appendChild(badge);
          this.els.batchCount = badge;
        }
        // enviar lote
        let sendBtn = document.getElementById('sendBatch');
        if (!sendBtn) {
          sendBtn = document.createElement('button');
          sendBtn.id = 'sendBatch';
          sendBtn.className = 'btn btn-success';
          sendBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> Enviar lote';
          sendBtn.disabled = true;
          batchBar.appendChild(sendBtn);
          this.els.sendBatch = sendBtn;
        }
        // descartar lote
        let clearBtn = document.getElementById('clearBatch');
        if (!clearBtn) {
          clearBtn = document.createElement('button');
          clearBtn.id = 'clearBatch';
          clearBtn.className = 'btn btn-outline-danger';
          clearBtn.innerHTML = '<i class="fa-solid fa-trash"></i> Descartar';
          clearBtn.disabled = true;
          batchBar.appendChild(clearBtn);
          this.els.clearBatch = clearBtn;
        }
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
          // insertamos debajo del header-card
          const headerCard = document.querySelector('.header-card');
          if (headerCard) headerCard.appendChild(strip);
          else document.body.appendChild(strip);
          this.els.pendingStrip = strip;
        }
      },

      bindEvents() {
        if (this.els.cameraBtn) {
          this.els.cameraBtn.addEventListener('click', () => {
            if (this.els.cameraInput) this.els.cameraInput.click();
          });
        }
        if (this.els.cameraInput) {
          this.els.cameraInput.setAttribute('accept', 'image/*');
          this.els.cameraInput.setAttribute('capture', 'environment');
          // múltiples capturas consecutivas: cada selección agrega 1; re-disparamos si continuousMode
          this.els.cameraInput.addEventListener('change', (e) => this.handleCameraCapture(e));
        }
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
        if (this.els.sendBatch) {
          this.els.sendBatch.addEventListener('click', () => this.uploadBatch());
        }
        if (this.els.clearBatch) {
          this.els.clearBatch.addEventListener('click', () => this.clearPending());
        }

        // Visor de imagen completa (click en miniatura existente)
        this.els.photoGrid?.addEventListener('click', (e) => {
          const card = e.target.closest('[data-open-viewer="1"]');
          if (!card) return;
          const fotoCard = e.target.closest('.photo-card');
          const fotoId = fotoCard?.getAttribute('data-foto-id');
          const downloadUrl = card.getAttribute('data-download-url');
          if (downloadUrl) this.openViewer(fotoId, downloadUrl);
        });

        // Eliminar foto existente
        this.els.photoGrid?.addEventListener('click', async (e) => {
          const btn = e.target.closest('.btn-delete-photo');
          if (!btn) return;
          const card = e.target.closest('.photo-card');
          const fotoId = card?.getAttribute('data-foto-id');
          if (!fotoId) return;
          if (!confirm('¿Eliminar esta foto?')) return;
          try {
            const res = await fetch(`/gallery/delete/${fotoId}`, { method: 'POST' });
            const j = await res.json().catch(() => null);
            const ok = j?.success === true;
            if (ok) card.remove();
            else alert(j?.error || 'No se pudo eliminar');
          } catch (err) {
            alert('Error eliminando la foto');
          }
        });

        // Controles del modal
        document.getElementById('slideshowClose')?.addEventListener('click', () => this.closeViewer());
        document.getElementById('slideshowPrev')?.addEventListener('click', () => this.navigateViewer(-1));
        document.getElementById('slideshowNext')?.addEventListener('click', () => this.navigateViewer(1));
      },

      initializeCameraSession() {
        this.capturedPhotos = [];
        this.updateBatchUI();
      },

      async bootstrapSession() {
        // 1) Validar sesión de subida
        try {
          const validateResp = await fetch(`/gallery/upload/validate/${this.reparacionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_count: 0, total_size: 0 })
          });
          const vres = await validateResp.json();
          const ok = (vres && (vres.success || vres?.result?.success));
          if (!ok) {
            const err = vres?.error || vres?.result?.error || 'No se pudo iniciar sesión de subida';
            console.warn(err);
          } else {
            this.currentSession = (vres.session_id || vres?.result?.session_id) || null;
          }
        } catch (e) {
          console.warn('validate_upload error', e);
        }

        // 2) Obtener upload link a la carpeta de la reparación
        try {
          const resp = await fetch(`/gallery/pcloud/uploadlink/${this.reparacionId}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({})
          });
          const r = await resp.json();
          const data = r.result || r;
          // La ruta devuelve { success, endpoint, code } si OK
          if (data.success && data.endpoint && data.code) {
            // pCloud uploadtolink usa POST a endpoint con campo 'code' o query ?code=
            this.pcloudUploadUrl = `${data.endpoint}?code=${encodeURIComponent(data.code)}`;
          } else {
            console.warn('No hay upload link (se usará fallback si es necesario):', data.error || data);
          }
        } catch (e) {
          console.warn('get_upload_link error; se usará fallback', e);
        }
      },

      // --------------- captura & cola ---------------
      async compressImage(file, maxMB = 5, quality = 0.8) {
        // reescala a ~1600px max y exporta JPEG de calidad razonable
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
        // Tomamos UN archivo por captura (flujo móvil)
        const inputFile = files[0];
        const compressed = await this.compressImage(inputFile, 5, 0.8);
        this.enqueue(compressed);

        // reabrir cámara si está activo el modo continuo
        this.els.cameraInput.value = '';
        if (this.continuousMode) {
          setTimeout(() => this.els.cameraInput.click(), 200);
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
          // liberar URL y quitar del array
          try { URL.revokeObjectURL(this.capturedPhotos[idx].previewUrl); } catch (e) {}
        }
        // reconstruimos array y DOM de la tira
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
        // revocar objectURLs
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
          // limpiar cola
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
        // intenta directo a pCloud → registrar; si falla, cae en fallback legacy (upload/single)
        try {
          this.showLoading(true, 'Subiendo a pCloud...');
          const seq = await this.getNextSequence();
          const up = await this.uploadDirectToPcloud(file);
          if (!up?.success || !up?.pcloud) throw new Error('Respuesta pCloud inesperada');
          this.showLoading(true, 'Registrando en Odoo...');
          const reg = await this.registerUploaded(up.pcloud, file.name, file.size, seq);
          // Pintar tarjeta nueva
          if (reg?.foto) this.appendPhotoCard(reg.foto);
        } catch (e) {
          // Fallback: usa endpoint legacy si existe sesión
          try {
            if (!this.currentSession) throw e;
            const fd = new FormData();
            fd.append('file', file);
            fd.append('sequence', await this.getNextSequence());
            fd.append('reparacion_id', this.reparacionId);
            const r = await fetch(`/gallery/upload/single/${this.currentSession}`, { method: 'POST', body: fd });
            const j = await r.json();
            const res = j.result || j;
            if (!res.success) throw new Error(res.error || 'Fallback falló');
            // refresco simple del grid
            window.location.reload();
          } catch (err) {
            throw err;
          }
        }
      },

      async uploadDirectToPcloud(file) {
        if (!this.pcloudUploadUrl) throw new Error('NO_PCL_UPLOADLINK');
        const fd = new FormData();
        const safeName = (file.name || `image_${Date.now()}.jpg`).replace(/\s+/g, '_');
        fd.append('file', file, safeName);
        // Nota: uploadtolink NO requiere token; usa code
        const url = this.pcloudUploadUrl.includes('?') ? `${this.pcloudUploadUrl}&renameifexists=1` : `${this.pcloudUploadUrl}?renameifexists=1`;
        const resp = await fetch(url, { method: 'POST', body: fd });
        if (!resp.ok) throw new Error(`PCLOUD_UPLOAD:${resp.status}`);
        // Respuesta típica: { result:0, fileids:[...], metadata:[{fileid, size, contenttype, name,...}] } (según versión)
        let data = {};
        try { data = await resp.json(); } catch (e) { /* puede no retornar JSON; manejar */ }
        if (data.result !== 0) {
          throw new Error(data.error || 'pCloud devolvió error');
        }
        // normalizar metadatos
        const meta = (Array.isArray(data.metadata) && data.metadata[0]) ? data.metadata[0] : null;
        const fileid = meta?.fileid || (Array.isArray(data.fileids) ? data.fileids[0] : null);
        if (!fileid) throw new Error('No se obtuvo fileid de pCloud');
        return {
          success: true,
          filename: safeName,
          pcloud: {
            fileid: String(fileid),
            size: meta?.size || file.size || 0,
            contenttype: meta?.contenttype || file.type || 'image/jpeg'
          }
        };
      },

      async registerUploaded(pcloudMeta, filename, size, sequence) {
        // Usa el endpoint del controlador: /gallery/pcloud/register (JSON)
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
        const res = j.result || j;
        if (!res.success) throw new Error(res.error || 'Registro falló');
        return res;
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

      // --------------- Visor ---------------
      openViewer(fotoId, url) {
        this.viewerList = Array.from(document.querySelectorAll('.photo-card'));
        this.viewerIndex = this.viewerList.findIndex(c => c.getAttribute('data-foto-id') === String(fotoId));
        this.modal = document.getElementById('slideshowModal');
        this.img = document.getElementById('slideshowImage');
        if (this.modal) this.modal.classList.add('show');
        this.loadViewerImage(this.viewerIndex);
      },
      closeViewer() {
        this.modal?.classList.remove('show');
      },
      navigateViewer(delta) {
        if (!this.viewerList) return;
        this.viewerIndex = (this.viewerIndex + delta + this.viewerList.length) % this.viewerList.length;
        this.loadViewerImage(this.viewerIndex);
      },
      loadViewerImage(index) {
        const card = this.viewerList[index];
        const cont = card.querySelector('[data-open-viewer="1"]');
        const full = cont?.getAttribute('data-download-url');
        if (full && this.img) this.img.src = full;
      },

      // --------------- util ---------------
      escapeHtml(str) {
        return String(str).replace(/[&<>"']/g, function (m) {
          return ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
          })[m];
        });
      },
    };

    gallery.init();
  });
})();