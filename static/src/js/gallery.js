// sat/static/src/js/gallery.js
// gallery.js
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
            this.loadingOverlay = document.getElementById('loadingOverlay');
            this.reparacionId = window.location.pathname.split('/').pop();
        },

        bindEvents() {
            if (this.fileInput) {
                this.fileInput.addEventListener('change', (e) => this.handleFileUpload(e));
                console.log('Evento de subida de archivos vinculado');
            }

            if (this.syncButton) {
                this.syncButton.addEventListener('click', () => this.handleSync());
                console.log('Evento de sincronización vinculado');
            }

            document.querySelectorAll('.delete-photo').forEach(btn => {
                btn.addEventListener('click', (e) => this.handleDelete(e));
            });

            // Eventos para las imágenes
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

                // Timeout para la carga
                loadTimeout = setTimeout(() => {
                    if (!img.complete && retryCount < maxRetries) {
                        console.log(`Reintentando carga de imagen ${retryCount + 1}/${maxRetries}`);
                        retryCount++;
                        img.src = img.src + `?retry=${Date.now()}`;
                        loadImage(); // Recursivo para siguiente intento
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

        handleFileUpload(event) {
            console.log('Iniciando subida de archivos...');
            const files = event.target.files;
            if (!files || !files.length) {
                console.log('No se seleccionaron archivos');
                return;
            }

            const formData = new FormData();
            Array.from(files).forEach(file => {
                if (this.validateFile(file)) {
                    formData.append('files[]', file);
                    console.log('Archivo agregado:', file.name);
                }
            });

            if (!formData.has('files[]')) {
                this.showError('No hay archivos válidos', 'Por favor seleccione imágenes válidas');
                return;
            }

            this.showLoading('Subiendo fotos...');

            fetch(`/gallery/upload/${this.reparacionId}`, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.showSuccess('Éxito', 'Fotos subidas correctamente');
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    throw new Error(data.error || 'Error al subir las fotos');
                }
            })
            .catch(error => {
                console.error('Error en subida:', error);
                this.showError('Error', error.message);
            })
            .finally(() => {
                this.fileInput.value = '';
                this.hideLoading();
            });
        },

        validateFile(file) {
            if (!file.type.startsWith('image/')) {
                this.showError('Archivo no válido', `${file.name} no es una imagen`);
                return false;
            }

            const maxSize = 10 * 1024 * 1024; // 10MB
            if (file.size > maxSize) {
                this.showError('Archivo muy grande', `${file.name} excede el tamaño máximo de 10MB`);
                return false;
            }

            return true;
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
