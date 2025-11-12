// sat/static/src/js/gallery.js
// Versión: solo-cámara + subida directa a pCloud + registro de archivo y visor de imagen completa
document.addEventListener('DOMContentLoaded', function () {
  const gallery = {
    capturedPhotos: [],
    currentSession: null,
    pcloudUploadUrl: null,
    reparacionId: window.location.pathname.split('/').pop(),

    init() {
      this.qs();
      this.bindEvents();
      this.initializeCameraSession();
      this.bootstrapSession(); // valida sesión y obtiene upload link
    },

    qs() {
      this.cameraBtn = document.getElementById('cameraBtn');
      this.cameraInput = document.getElementById('cameraCapture');
      this.photoGrid = document.getElementById('photoGrid');
      this.loadingOverlay = document.getElementById('loadingOverlay');
      // No hay fileInput de galería por política "solo cámara"
    },

    bindEvents() {
      if (this.cameraBtn) {
        this.cameraBtn.addEventListener('click', () => {
          if (this.cameraInput) this.cameraInput.click();
        });
      }
      if (this.cameraInput) {
        this.cameraInput.setAttribute('accept', 'image/*');
        this.cameraInput.setAttribute('capture', 'environment');
        this.cameraInput.addEventListener('change', (e) => this.handleCameraCapture(e));
      }

      // Visor de imagen completa (click en miniatura)
      this.photoGrid?.addEventListener('click', (e) => {
        const card = e.target.closest('[data-open-viewer="1"]');
        if (!card) return;
        const fotoCard = e.target.closest('.photo-card');
        const fotoId = fotoCard?.getAttribute('data-foto-id');
        const downloadUrl = card.getAttribute('data-download-url');
        if (downloadUrl) this.openViewer(fotoId, downloadUrl);
      });

      // Controles del modal
      document.getElementById('slideshowClose')?.addEventListener('click', () => this.closeViewer());
      document.getElementById('slideshowPrev')?.addEventListener('click', () => this.navigateViewer(-1));
      document.getElementById('slideshowNext')?.addEventListener('click', () => this.navigateViewer(1));
    },

    initializeCameraSession() {
      this.capturedPhotos = [];
    },

    async bootstrapSession() {
      // 1) Validar sesión de subida
      const validateResp = await fetch(`/gallery/upload/validate/${this.reparacionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_count: 0, total_size: 0 })
      });
      const vdata = await validateResp.json();
      const vres = vdata.result || vdata;
      if (!vres.success) {
        alert(vres.error || 'No se pudo iniciar sesión de subida');
        return;
      }
      this.currentSession = vres.session_id;

      // 2) Obtener upload link a la carpeta de la reparación
      try {
        const resp = await fetch(`/gallery/pcloud/uploadlink/${this.reparacionId}`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({})
        });
        const j = await resp.json();
        const r = j.result || j;
        if (r.success && r.upload_url) this.pcloudUploadUrl = r.upload_url;
      } catch (e) {
        console.warn('No hay upload link; se usará fallback si hace falta', e);
      }
    },

    // Compresión rápida (mantener percepción de inmediatez)
    async compressImage(file, maxMB = 5, quality = 0.8) {
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
            const f = new File([blob], (file.name || `image_${Date.now()}.jpg`), { type: 'image/jpeg' });
            resolve(f);
          }, 'image/jpeg', quality);
        };
        img.src = URL.createObjectURL(file);
      });
    },

    async handleCameraCapture(e) {
      const files = Array.from(e.target.files || []);
      if (!files.length) return;
      // compresión ligera
      const inputFile = files[0];
      const compressed = await this.compressImage(inputFile, 5, 0.8);
      await this.uploadOne(compressed);
      // reset input para permitir tomar otra foto al instante
      this.cameraInput.value = '';
    },

    async uploadDirectToPcloud(file) {
      if (!this.pcloudUploadUrl) throw new Error('NO_PCL_UPLOADLINK');
      const fd = new FormData();
      const safeName = file.name || `image_${Date.now()}.jpg`;
      fd.append('file', file, safeName);
      fd.append('filename', safeName);
      const url = this.pcloudUploadUrl.includes('?') ? `${this.pcloudUploadUrl}&renameifexists=1` : `${this.pcloudUploadUrl}?renameifexists=1`;
      const resp = await fetch(url, { method: 'POST', body: fd });
      if (!resp.ok) throw new Error(`PCLOUD_UPLOAD:${resp.status}`);
      return { success: true, filename: safeName };
    },

    async registerUploaded(filename, size, sequence) {
      const r = await fetch('/gallery/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reparacion_id: this.reparacionId, filename, size, sequence })
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

    showLoading(show) {
      if (!this.loadingOverlay) return;
      this.loadingOverlay.classList.toggle('hidden', !show);
    },

    async uploadOne(file) {
      try {
        this.showLoading(true);
        const seq = await this.getNextSequence();
        // 1) pCloud
        const up = await this.uploadDirectToPcloud(file);
        // 2) Registrar en BD
        const reg = await this.registerUploaded(up.filename, file.size, seq);
        // 3) Pintar tarjeta nueva
        this.appendPhotoCard(reg.foto);
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
          if (!res.success) throw e;
          // pedir recarga parcial (simple)
          window.location.reload();
        } catch (err) {
          alert('No se pudo subir la foto: ' + (err.message || err));
        }
      } finally {
        this.showLoading(false);
      }
    },

    appendPhotoCard(f) {
      if (!this.photoGrid || !f) return;
      const div = document.createElement('div');
      div.className = 'photo-card';
      div.setAttribute('data-foto-id', f.id);
      div.innerHTML = `
        <div class="photo-container" data-open-viewer="1" data-download-url="/gallery/download/${f.id}">
          <span class="photo-badge">Foto</span>
          <img src="${f.thumb_url || '/gallery/preview/' + f.id}" alt="Foto"/>
        </div>
        <div class="photo-info">
          <span>#${f.sequence || 0} — ${f.nombre_foto || ''}</span>
          <a class="btn btn-sm btn-outline-secondary" href="/gallery/download/${f.id}" target="_blank">
            <i class="fa-solid fa-download"></i>
          </a>
        </div>`;
      this.photoGrid.prepend(div);
    },

    // ===== Visor de imagen completa =====
    openViewer(fotoId, url) {
      this.viewerList = Array.from(document.querySelectorAll('.photo-card'));
      this.viewerIndex = this.viewerList.findIndex(c => c.getAttribute('data-foto-id') === String(fotoId));
      this.modal = document.getElementById('slideshowModal');
      this.img = document.getElementById('slideshowImage');
      this.modal.classList.add('show');
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
  };

  gallery.init();
});
