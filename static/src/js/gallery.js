// sat/static/src/js/gallery.js
document.addEventListener('DOMContentLoaded', function() {
    const gallery = {
        init() {
            console.log('Iniciando galería...');
            this.initializeElements();
            this.bindEvents();
            this.initializeImagePreviews();
        },

        initializeElements() {
            this.fileInput = document.getElementById('fileUpload');
            this.photoGrid = document.querySelector('#photoGrid');
            this.syncButton = document.getElementById('syncButton');
            this.shareGalleryBtn = document.getElementById('shareGalleryBtn');
            this.loadingOverlay = document.getElementById('loadingOverlay');
            this.reparacionId = window.location.pathname.split('/').pop();
            this.setupFileInput();
        },

        setupFileInput() {
            if (this.fileInput) {
                this.fileInput.setAttribute('multiple', 'multiple');
                this.fileInput.setAttribute('accept', 'image/*');

                // Mejorar soporte móvil para múltiples fotos
                if (this.isMobile()) {
                    this.fileInput.addEventListener('click', function() {
                        this.setAttribute('multiple', 'multiple');
                    });
                    this.fileInput.addEventListener('change', (e) => this.handleMassiveUpload(e));
                }
            }
        },

        isMobile() {
            return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
        },

        bindEvents() {
            if (this.fileInput && !this.isMobile()) {
                this.fileInput.addEventListener('change', (e) => this.handleMassiveUpload(e));
                console.log('Evento de subida masiva vinculado');
            }

            if (this.syncButton) {
                this.syncButton.addEventListener('click', () => this.handleSync());
                console.log('Evento de sincronización vinculado');
            }

            if (this.shareGalleryBtn) {
                this.shareGalleryBtn.addEventListener('click', () => this.handleShareGallery());
                console.log('Evento de compartir vinculado');
            }

            document.querySelectorAll('.download-photo').forEach(btn => {
                btn.addEventListener('click', (e) => this.handleDownload(e));
            });

            document.querySelectorAll('.delete-photo').forEach(btn => {
                btn.addEventListener('click', (e) => this.handleDelete(e));
            });

            document.querySelectorAll('.preview-image').forEach(img => {
                this.setupImageHandling(img);
            });
        },

        handleDownload(event) {
            event.preventDefault();
            const button = event.currentTarget;
            const url = button.dataset.url;
            console.log(`Intentando descargar la imagen desde: ${url}`);

            const fileName = button.closest('.photo-card').querySelector('.photo-name')?.textContent.trim() || 'foto';

            fetch(url)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`Error al descargar la imagen: ${response.statusText}`);
                    }
                    console.log('Respuesta de descarga recibida');
                    return response.blob();
                })
                .then(blob => {
                    const link = document.createElement('a');
                    link.href = URL.createObjectURL(blob);
                    link.download = fileName;
                    console.log(`Iniciando descarga de archivo: ${fileName}`);
                    link.click();
                    URL.revokeObjectURL(link.href);
                })
                .catch(error => {
                    console.error('Error en descarga:', error);
                    this.showError('Error', 'No se pudo descargar la foto');
                });
        },

        handleShareGallery() {
            const currentUrl = window.location.href;
            console.log(`Intentando compartir la URL: ${currentUrl}`);

            if (navigator.clipboard) {
                navigator.clipboard.writeText(currentUrl).then(() => {
                    console.log('URL copiada al portapapeles');
                    Swal.fire({
                        icon: 'success',
                        title: 'URL Copiada',
                        text: 'El enlace ha sido copiado al portapapeles',
                        timer: 1500,
                        showConfirmButton: false
                    });
                }).catch(err => {
                    console.error('Error al copiar URL:', err);
                    this.showError('Error', 'No se pudo copiar el enlace al portapapeles');
                });
            } else {
                console.warn('La API Clipboard no está disponible en este navegador');
                this.showError('No compatible', 'Tu navegador no permite copiar enlaces directamente');
            }
        },

        handleMassiveUpload(event) {
            const files = Array.from(event.target.files);
            if (!files.length) return;

            const validFiles = files.filter(file => this.validateFile(file));
            if (!validFiles.length) {
                this.showError('No hay archivos válidos', 'Por favor seleccione imágenes válidas');
                return;
            }

            this.showUploadProgress(validFiles.length);

            const batchSize = 5;
            const batches = [];
            for (let i = 0; i < validFiles.length; i += batchSize) {
                batches.push(validFiles.slice(i, i + batchSize));
            }

            this.processBatches(batches, 0, validFiles.length);
        },

        processBatches(batches, uploadedCount, totalFiles) {
            if (batches.length === 0) {
                this.showSuccess('Subida Completada', `Se subieron ${uploadedCount} fotos correctamente`);
                setTimeout(() => window.location.reload(), 1500);
                return;
            }

            const currentBatch = batches.shift();
            const formData = new FormData();
            currentBatch.forEach(file => formData.append('files[]', file));

            fetch(`/gallery/upload/${this.reparacionId}`, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const newUploadedCount = uploadedCount + currentBatch.length;
                    const progress = (newUploadedCount / totalFiles) * 100;
                    this.updateUploadProgress(progress, newUploadedCount, totalFiles);
                    this.processBatches(batches, newUploadedCount, totalFiles);
                } else {
                    throw new Error(data.error || 'Error en la subida');
                }
            })
            .catch(error => {
                console.error('Error en subida:', error);
                this.showError('Error', error.message);
            });
        },

        validateFile(file) {
            if (!file.type.startsWith('image/')) {
                console.warn(`Archivo no válido: ${file.name} (no es una imagen)`);
                return false;
            }

            const maxSize = 10 * 1024 * 1024;
            if (file.size > maxSize) {
                console.warn(`Archivo muy grande: ${file.name}`);
                return false;
            }

            return true;
        },

        showUploadProgress(totalFiles) {
            Swal.fire({
                title: 'Subiendo Fotos',
                html: `
                    <div class="progress mb-3">
                        <div class="progress-bar" role="progressbar" style="width: 0%" 
                             aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>
                    </div>
                    <div id="uploadStatus">Iniciando subida de ${totalFiles} fotos...</div>
                `,
                allowOutsideClick: false,
                showConfirmButton: false
            });
        },

        updateUploadProgress(progress, uploadedCount, totalFiles) {
            const progressBar = document.querySelector('.progress-bar');
            const statusText = document.getElementById('uploadStatus');
            
            if (progressBar && statusText) {
                progressBar.style.width = `${progress}%`;
                progressBar.setAttribute('aria-valuenow', progress);
                statusText.textContent = `Subiendo: ${uploadedCount} de ${totalFiles} fotos`;
            }
        },

        handleSync() {
            console.log('Iniciando sincronización...');
            this.showLoading('Sincronizando con pCloud...');

            fetch(`/gallery/sync/${this.reparacionId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.showSuccess('Sincronización completada', data.message || 'Fotos sincronizadas');
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    throw new Error(data.error || 'Error al sincronizar');
                }
            })
            .catch(error => {
                console.error('Error en sincronización:', error);
                this.showError('Error', error.message);
            })
            .finally(() => {
                this.hideLoading();
            });
        },

        handleDelete(event) {
            const photoId = event.currentTarget.dataset.photoId;
            if (!photoId) {
                console.error('No se encontró ID de foto');
                return;
            }

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

        deletePhoto(photoId) {
            this.showLoading('Eliminando foto...');

            fetch(`/gallery/delete/${photoId}`, {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const element = document.querySelector(`[data-photo-id="${photoId}"]`);
                    if (element) {
                        element.remove();
                        this.showSuccess('Éxito', 'Foto eliminada correctamente');
                    }
                } else {
                    throw new Error(data.error || 'Error al eliminar la foto');
                }
            })
            .catch(error => {
                console.error('Error en eliminación:', error);
                this.showError('Error', error.message);
            })
            .finally(() => {
                this.hideLoading();
            });
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
        },

        initializeImagePreviews() {
            if ('IntersectionObserver' in window) {
                const imageObserver = new IntersectionObserver((entries, observer) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            const img = entry.target;
                            if (!img.classList.contains('loaded')) {
                                this.setupImageHandling(img);
                                img.classList.add('loaded');
                            }
                        }
                    });
                });

                document.querySelectorAll('.preview-image:not(.loaded)').forEach(img => {
                    imageObserver.observe(img);
                });
            } else {
                document.querySelectorAll('.preview-image:not(.loaded)').forEach(img => {
                    this.setupImageHandling(img);
                    img.classList.add('loaded');
                });
            }
        }
    };

    gallery.init();
});
