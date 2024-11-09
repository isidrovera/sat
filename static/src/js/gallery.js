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
            this.shareGalleryBtn = document.getElementById('shareGalleryBtn'); // Asegurarnos que coincida con el ID en el HTML
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
                }
            }
        },

        isMobile() {
            return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
        },

        bindEvents() {
            if (this.fileInput) {
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

            // Eventos para descargas
            document.querySelectorAll('.download-photo').forEach(btn => {
                btn.addEventListener('click', (e) => this.handleDownload(e));
            });

            // Eventos para eliminación
            document.querySelectorAll('.delete-photo').forEach(btn => {
                btn.addEventListener('click', (e) => this.handleDelete(e));
            });

            // Eventos para imágenes
            document.querySelectorAll('.preview-image').forEach(img => {
                this.setupImageHandling(img);
            });
        },

        setupImageHandling(img) {
            let loadTimeout;
            let retryCount = 0;
            const maxRetries = 3;

            const loadImage = () => {
                img.classList.add('loading');
                clearTimeout(loadTimeout);

                loadTimeout = setTimeout(() => {
                    if (!img.complete && retryCount < maxRetries) {
                        console.log(`Reintentando carga de imagen ${retryCount + 1}/${maxRetries}`);
                        retryCount++;
                        img.src = img.src + `?retry=${Date.now()}`;
                        loadImage();
                    } else if (retryCount >= maxRetries) {
                        this.handleImageError(img);
                    }
                }, 5000);

                img.onerror = () => {
                    clearTimeout(loadTimeout);
                    if (retryCount < maxRetries) {
                        retryCount++;
                        setTimeout(() => {
                            img.src = img.src + `?retry=${Date.now()}`;
                            loadImage();
                        }, 1000 * retryCount);
                    } else {
                        this.handleImageError(img);
                    }
                };

                img.onload = () => {
                    clearTimeout(loadTimeout);
                    this.handleImageSuccess(img);
                };
            };

            loadImage();
        },

        handleImageError(img) {
            console.error(`Error definitivo cargando imagen: ${img.src}`);
            img.src = '/sat/static/src/img/placeholder.png';
            img.classList.remove('loading');
            const retryBadge = img.closest('.photo-container').querySelector('.retry-badge');
            if (retryBadge) {
                retryBadge.classList.add('d-none');
            }
        },

        handleImageSuccess(img) {
            console.log(`Imagen cargada exitosamente: ${img.src}`);
            img.classList.remove('loading');
            const retryBadge = img.closest('.photo-container').querySelector('.retry-badge');
            if (retryBadge) {
                retryBadge.classList.add('d-none');
            }
        },

        handleDownload(event) {
            event.preventDefault();
            const button = event.currentTarget;
            const url = button.dataset.url;
            const fileName = button.closest('.photo-card').querySelector('.photo-name').textContent;

            this.showLoading('Descargando foto...');

            fetch(url)
                .then(response => response.blob())
                .then(blob => {
                    const link = document.createElement('a');
                    link.href = window.URL.createObjectURL(blob);
                    link.download = fileName;
                    link.click();
                    window.URL.revokeObjectURL(link.href);
                    this.hideLoading();
                })
                .catch(error => {
                    console.error('Error en descarga:', error);
                    this.showError('Error', 'No se pudo descargar la foto');
                    this.hideLoading();
                });
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

        validateFile(file) {
            if (!file.type.startsWith('image/')) {
                console.warn(`Archivo no válido: ${file.name} (no es una imagen)`);
                return false;
            }

            const maxSize = 10 * 1024 * 1024; // 10MB
            if (file.size > maxSize) {
                console.warn(`Archivo muy grande: ${file.name}`);
                return false;
            }

            return true;
        },

        handleShareGallery() {
            const currentUrl = window.location.href;
            
            if (navigator.share) {
                navigator.share({
                    title: 'Galería de Fotos',
                    text: 'Accede a la galería de fotos completa:',
                    url: currentUrl
                }).catch(() => {
                    this.showShareDialog(currentUrl);
                });
            } else {
                this.showShareDialog(currentUrl);
            }
        },

        showShareDialog(url) {
            Swal.fire({
                title: 'Compartir Galería',
                html: `
                    <div class="input-group mb-3">
                        <input type="text" class="form-control" value="${url}" readonly id="shareUrl">
                        <button class="btn btn-outline-primary" type="button" id="copyButton">
                            <i class="fas fa-copy"></i> Copiar
                        </button>
                    </div>
                    <p class="text-muted">Comparte este enlace para que otros puedan ver la galería</p>
                `,
                showCancelButton: true,
                cancelButtonText: 'Cerrar',
                showConfirmButton: false,
                didRender: () => {
                    const copyButton = document.getElementById('copyButton');
                    const shareUrl = document.getElementById('shareUrl');
                    
                    copyButton.addEventListener('click', () => {
                        shareUrl.select();
                        document.execCommand('copy');
                        Swal.fire({
                            icon: 'success',
                            title: 'URL Copiada',
                            text: 'El enlace ha sido copiado al portapapeles',
                            timer: 1500,
                            showConfirmButton: false
                        });
                    });
                }
            });
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

    // Inicializar galería
    gallery.init();
});