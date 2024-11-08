// sat/static/src/js/gallery.js
document.addEventListener('DOMContentLoaded', function() {
    const gallery = {
        init() {
            this.fileInput = document.getElementById('fileUpload');
            this.progressBar = document.querySelector('.upload-progress');
            this.photoGrid = document.getElementById('photoGrid');
            this.reparacionId = this.getReparacionId();
            this.bindEvents();
            this.loadGallery();
        },

        getReparacionId() {
            return window.location.pathname.split('/').pop();
        },

        bindEvents() {
            // Bind upload event
            this.fileInput?.addEventListener('change', (e) => this.handleFileUpload(e));
            
            // Bind delete events
            document.querySelectorAll('.delete-photo').forEach(btn => {
                btn.addEventListener('click', (e) => this.handleDelete(e));
            });

            // Bind download all button
            const downloadAllBtn = document.querySelector('.download-all');
            if (downloadAllBtn) {
                downloadAllBtn.addEventListener('click', (e) => this.handleDownloadAll(e));
            }
        },

        loadGallery() {
            fetch(`/gallery/refresh_gallery/${this.reparacionId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success && data.fotos) {
                    this.renderPhotos(data.fotos);
                } else if (data.error) {
                    this.showError('Error al cargar la galería', data.error);
                }
            })
            .catch(error => {
                this.showError('Error de conexión', 'No se pudo cargar la galería.');
            });
        },

        renderPhotos(fotos) {
            if (!this.photoGrid) return;

            if (fotos.length === 0) {
                this.photoGrid.innerHTML = `
                    <div class="col-12 text-center p-5">
                        <h4 class="text-muted">No hay fotos disponibles</h4>
                        <p>Haga clic en "Subir Fotos" para agregar imágenes.</p>
                    </div>
                `;
                return;
            }

            this.photoGrid.innerHTML = fotos.map(foto => `
                <div class="photo-card" data-photo-id="${foto.id}">
                    <div class="photo-container">
                        <img src="${foto.thumb_url}" 
                             alt="${foto.nombre_foto}"
                             onerror="this.src='/sat/static/src/img/image-error.png'"/>
                        <div class="actions-bar">
                            <button class="btn btn-sm btn-danger delete-photo" 
                                    data-photo-id="${foto.id}"
                                    title="Eliminar foto">
                                <i class="fas fa-trash"></i>
                            </button>
                            <a href="${foto.download_url}" 
                               class="btn btn-sm btn-primary"
                               title="Descargar foto"
                               download>
                                <i class="fas fa-download"></i>
                            </a>
                        </div>
                    </div>
                    <div class="p-2">
                        <small class="text-muted text-truncate d-block" title="${foto.nombre_foto}">
                            ${foto.nombre_foto}
                        </small>
                    </div>
                </div>
            `).join('');
            
            this.bindEvents();
        },

        handleFileUpload(event) {
            const files = event.target.files;
            if (!files.length) return;

            // Validar archivos
            const validFiles = Array.from(files).filter(file => {
                const isValid = this.validateFile(file);
                if (!isValid) {
                    this.showError('Archivo no válido', 
                        `El archivo "${file.name}" no es una imagen válida o excede el tamaño permitido.`);
                }
                return isValid;
            });

            if (!validFiles.length) {
                this.fileInput.value = '';
                return;
            }

            // Mostrar loading
            this.showLoading('Subiendo fotos...');

            const formData = new FormData();
            validFiles.forEach(file => {
                formData.append('files[]', file);
            });

            fetch(`/gallery/upload/${this.reparacionId}`, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.showSuccess('Éxito', 'Fotos subidas correctamente');
                    this.loadGallery();
                } else {
                    throw new Error(data.error || 'Error al subir las fotos');
                }
            })
            .catch(error => {
                this.showError('Error', error.message);
            })
            .finally(() => {
                this.hideLoading();
                this.fileInput.value = '';
            });
        },

        handleDelete(event) {
            const button = event.currentTarget;
            const photoId = button.dataset.photoId;
            
            if (!photoId) return;

            Swal.fire({
                title: '¿Está seguro?',
                text: 'Esta acción no se puede deshacer',
                icon: 'warning',
                showCancelButton: true,
                confirmButtonColor: '#d33',
                cancelButtonColor: '#3085d6',
                confirmButtonText: 'Sí, eliminar',
                cancelButtonText: 'Cancelar'
            }).then((result) => {
                if (result.isConfirmed) {
                    this.deletePhoto(photoId);
                }
            });
        },

        handleDownloadAll(event) {
            event.preventDefault();
            
            this.showLoading('Preparando descarga...');
            
            fetch(`/gallery/api/download_all/${this.reparacionId}`)
                .then(response => {
                    if (!response.ok) throw new Error('Error al preparar la descarga');
                    return response.blob();
                })
                .then(blob => {
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `fotos_reparacion_${this.reparacionId}.zip`;
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    document.body.removeChild(a);
                })
                .catch(error => {
                    this.showError('Error', 'No se pudo descargar el archivo ZIP');
                })
                .finally(() => {
                    this.hideLoading();
                });
        },

        deletePhoto(photoId) {
            this.showLoading('Eliminando foto...');

            fetch(`/gallery/delete/${photoId}`, {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const photoCard = document.querySelector(`[data-photo-id="${photoId}"]`);
                    if (photoCard) {
                        photoCard.remove();
                        this.showSuccess('Éxito', 'Foto eliminada correctamente');
                    }
                    // Recargar galería para actualizar la numeración
                    this.loadGallery();
                } else {
                    throw new Error(data.error || 'Error al eliminar la foto');
                }
            })
            .catch(error => {
                this.showError('Error', error.message);
            })
            .finally(() => {
                this.hideLoading();
            });
        },

        validateFile(file) {
            // Validar tipo de archivo
            const validTypes = ['image/jpeg', 'image/png', 'image/gif'];
            if (!validTypes.includes(file.type)) return false;

            // Validar tamaño (máximo 10MB)
            const maxSize = 10 * 1024 * 1024; // 10MB en bytes
            if (file.size > maxSize) return false;

            return true;
        },

        showLoading(message = 'Cargando...') {
            Swal.fire({
                title: message,
                allowOutsideClick: false,
                didOpen: () => {
                    Swal.showLoading();
                }
            });
        },

        hideLoading() {
            Swal.close();
        },

        showError(title, message) {
            Swal.fire({
                icon: 'error',
                title: title,
                text: message,
                confirmButtonText: 'Aceptar'
            });
        },

        showSuccess(title, message) {
            Swal.fire({
                icon: 'success',
                title: title,
                text: message,
                confirmButtonText: 'Aceptar'
            });
        }
    };

    // Inicializar galería
    gallery.init();
});