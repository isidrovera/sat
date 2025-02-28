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
            console.log('Elementos inicializados:', {
                fileInput: this.fileInput,
                photoGrid: this.photoGrid,
                syncButton: this.syncButton,
                shareGalleryBtn: this.shareGalleryBtn,
                loadingOverlay: this.loadingOverlay,
                reparacionId: this.reparacionId,
            });
            this.setupFileInput();
        },

        setupFileInput() {
            if (this.fileInput) {
                this.fileInput.setAttribute('multiple', 'multiple');
                this.fileInput.setAttribute('accept', 'image/*');
                console.log('Configurando input para múltiples fotos en dispositivos móviles.');

                if (this.isMobile()) {
                    this.fileInput.addEventListener('click', function() {
                        this.setAttribute('multiple', 'multiple');
                    });
                    this.fileInput.addEventListener('change', (e) => this.handleMassiveUpload(e));
                    console.log('Configuración de subida múltiple activada para dispositivos móviles');
                }
            }
        },

        isMobile() {
            const isMobileDevice = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
            console.log('Detección de dispositivo móvil:', isMobileDevice);
            return isMobileDevice;
        },

        bindEvents() {
            console.log('Iniciando bindEvents...');
            
            // Inicializar eventos de slideshow
            this.slideshowEventsInitialized = false;
            
            if (this.fileInput && !this.isMobile()) {
                this.fileInput.addEventListener('change', (e) => this.handleMassiveUpload(e));
                console.log('Evento de subida masiva vinculado');
            } else {
                console.log('No se pudo vincular el evento de subida masiva');
            }
        
            if (this.syncButton) {
                this.syncButton.addEventListener('click', () => this.handleSync());
                console.log('Evento de sincronización vinculado');
            } else {
                console.log('No se encontró syncButton');
            }
        
            if (this.shareGalleryBtn) {
                this.shareGalleryBtn.addEventListener('click', () => this.handleShareGallery());
                console.log('Evento de compartir vinculado');
            } else {
                console.log('No se encontró shareGalleryBtn');
            }
            
            document.querySelectorAll('.download-photo').forEach(btn => {
                btn.addEventListener('click', (e) => this.handleDownload(e));
                console.log('Evento de descarga vinculado para foto:', btn);
            });
        
            document.querySelectorAll('.delete-photo').forEach(btn => {
                btn.addEventListener('click', (e) => this.handleDelete(e));
                console.log('Evento de eliminación vinculado para foto:', btn);
            });
        },
        
        handleDownload(event) {
            event.preventDefault();
            const button = event.currentTarget;
            const photoId = button.dataset.photoId;
            console.log(`Solicitando descarga para la foto con ID: ${photoId}`);
        
            // Hacer una solicitud para obtener el contenido binario desde el servidor
            fetch(`/gallery/download/${photoId}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error('No se pudo obtener el archivo');
                    }
                    return response.blob();
                })
                .then(blob => {
                    const url = window.URL.createObjectURL(blob);
                    const link = document.createElement('a');
                    link.href = url;
                    link.setAttribute('download', button.getAttribute('data-filename') || 'foto');
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                    window.URL.revokeObjectURL(url);
                    console.log('Archivo descargado exitosamente');
                })
                .catch(error => {
                    console.error('Error al descargar la foto:', error);
                    this.showError('Error', 'No se pudo descargar la foto. Inténtalo de nuevo.');
                });
        },

        handleShareGallery() {
            console.log('handleShareGallery fue llamado');  // Verifica que la función se está ejecutando
        
            const currentUrl = window.location.href;
            console.log(`URL actual para compartir: ${currentUrl}`);  // Verifica si obtiene la URL
        
            if (!currentUrl) {
                console.error('No se pudo obtener la URL actual');
                return;
            }
        
            // Intento de copiar URL al portapapeles
            if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
                console.log('Intentando copiar al portapapeles usando Clipboard API');
                navigator.clipboard.writeText(currentUrl)
                    .then(() => {
                        console.log('URL copiada al portapapeles exitosamente');
                        Swal.fire({
                            icon: 'success',
                            title: 'URL Copiada',
                            text: 'El enlace ha sido copiado al portapapeles',
                            timer: 1500,
                            showConfirmButton: false
                        });
                    })
                    .catch(err => {
                        console.error('Error al intentar copiar con Clipboard API:', err);
                    });
            } else {
                console.warn('Clipboard API no disponible. Usando método alternativo.');
            }
        },
        tryClipboardAPI(currentUrl) {
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(currentUrl)
                    .then(() => {
                        console.log('URL copiada exitosamente usando Clipboard API');
                        this.showSuccess('URL Copiada', 'El enlace ha sido copiado al portapapeles');
                    })
                    .catch(error => {
                        console.error('Error al copiar con Clipboard API:', error);
                        this.fallbackCopyText(currentUrl);
                    });
            } else {
                console.warn('Clipboard API no disponible, usando método alternativo.');
                this.fallbackCopyText(currentUrl);
            }
        },
        
        getCurrentPageUrl() {
            // Obtener la URL canónica si existe, si no, usar la URL actual
            const canonicalElement = document.querySelector("link[rel='canonical']");
            if (canonicalElement) {
                return canonicalElement.href;
            }
            
            // Si no hay URL canónica, usar la URL actual limpia
            const url = new URL(window.location.href);
            // Eliminar parámetros UTM y otros parámetros de tracking si existen
            ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content'].forEach(param => 
                url.searchParams.delete(param)
            );
            return url.toString();
        },
        
        fallbackCopyText(text) {
            const tempInput = document.createElement('textarea');
            tempInput.style.position = 'fixed';
            tempInput.style.opacity = '0';
            tempInput.value = text;
            document.body.appendChild(tempInput);
        
            try {
                // Para dispositivos móviles
                tempInput.contentEditable = true;
                tempInput.readOnly = false;
                
                // Seleccionar y copiar
                const range = document.createRange();
                range.selectNodeContents(tempInput);
                const selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
                tempInput.setSelectionRange(0, text.length); // Para dispositivos móviles
                
                const successful = document.execCommand('copy');
                if (successful) {
                    console.log('Texto copiado exitosamente usando método fallback');
                    this.showSuccess('URL Copiada', 'El enlace ha sido copiado al portapapeles');
                } else {
                    throw new Error('No se pudo copiar el texto');
                }
            } catch (err) {
                console.error('Error en fallbackCopyText:', err);
                this.showError('Error', 'No se pudo copiar la URL');
            } finally {
                document.body.removeChild(tempInput);
            }
        },

        // Nuevas funciones para el visor de imágenes
        setupImageHandling(img) {
            // Configura el evento de click para abrir la imagen en el visor
            const photoCard = img.closest('.photo-card');
            if (photoCard) {
                photoCard.addEventListener('click', (e) => {
                    // Solo abrir si no se hizo clic en los botones de acción
                    if (!e.target.closest('.actions-bar')) {
                        const photoId = photoCard.dataset.photoId;
                        this.openPhotoViewer(photoId);
                    }
                });
            }
        },

        openPhotoViewer(photoId) {
            console.log(`Abriendo visor para la foto con ID: ${photoId}`);
            // Obtener todas las fotos en la cuadrícula
            const photoElements = document.querySelectorAll('.photo-card');
            const photos = Array.from(photoElements).map(el => {
                const img = el.querySelector('img');
                const nameEl = el.querySelector('.photo-name');
                return {
                    id: el.dataset.photoId,
                    // Cambia la ruta de la miniatura a la imagen completa
                    url: img.src.replace('/thumb/', '/'),
                    name: nameEl ? nameEl.textContent : 'Foto'
                };
            });
            
            // Encontrar el índice de la foto actual
            const currentIndex = photos.findIndex(photo => photo.id === photoId);
            
            if (currentIndex === -1) {
                console.error('No se encontró la foto en la galería');
                return;
            }
            
            // Configurar el modal
            const modal = document.getElementById('slideshowModal');
            const modalImg = document.getElementById('slideshowImage');
            const captionText = document.getElementById('slideshowCaption');
            const currentCounter = document.getElementById('slideshowCurrent');
            const totalCounter = document.getElementById('slideshowTotal');
            
            // Establecer los datos iniciales
            this.currentPhotoIndex = currentIndex;
            this.galleryPhotos = photos;
            
            // Actualizar la imagen y la información
            modalImg.src = photos[currentIndex].url;
            captionText.textContent = photos[currentIndex].name;
            currentCounter.textContent = currentIndex + 1;
            totalCounter.textContent = photos.length;
            
            // Mostrar el modal
            modal.style.display = 'block';
            document.body.style.overflow = 'hidden'; // Prevenir scroll
            
            // Configurar los eventos de navegación si aún no están configurados
            if (!this.slideshowEventsInitialized) {
                this.initSlideshowEvents();
            }
        },

        initSlideshowEvents() {
            // Configurar cerrar modal
            const modal = document.getElementById('slideshowModal');
            const closeBtn = modal.querySelector('.slideshow-close');
            
            closeBtn.addEventListener('click', () => {
                modal.style.display = 'none';
                document.body.style.overflow = ''; // Restaurar scroll
            });
            
            // Configurar botones de navegación
            const prevBtn = modal.querySelector('.slideshow-prev');
            const nextBtn = modal.querySelector('.slideshow-next');
            
            prevBtn.addEventListener('click', () => this.navigateSlideshow(-1));
            nextBtn.addEventListener('click', () => this.navigateSlideshow(1));
            
            // Configurar navegación con teclado
            document.addEventListener('keydown', (e) => {
                if (modal.style.display === 'block') {
                    if (e.key === 'ArrowLeft') {
                        this.navigateSlideshow(-1);
                    } else if (e.key === 'ArrowRight') {
                        this.navigateSlideshow(1);
                    } else if (e.key === 'Escape') {
                        modal.style.display = 'none';
                        document.body.style.overflow = '';
                    }
                }
            });
            
            // Cerrar al hacer clic fuera de la imagen
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    modal.style.display = 'none';
                    document.body.style.overflow = '';
                }
            });
            
            this.slideshowEventsInitialized = true;
        },

        navigateSlideshow(step) {
            if (!this.galleryPhotos || this.galleryPhotos.length === 0) return;
            
            // Calcular nuevo índice
            const newIndex = (this.currentPhotoIndex + step + this.galleryPhotos.length) % this.galleryPhotos.length;
            this.currentPhotoIndex = newIndex;
            
            // Actualizar la imagen y la información
            const photo = this.galleryPhotos[newIndex];
            const modalImg = document.getElementById('slideshowImage');
            const captionText = document.getElementById('slideshowCaption');
            const currentCounter = document.getElementById('slideshowCurrent');
            
            // Añadir clase para efecto de transición
            modalImg.classList.add('changing');
            
            // Actualizar imagen con efecto de carga
            modalImg.src = photo.url;
            captionText.textContent = photo.name;
            currentCounter.textContent = newIndex + 1;
            
            // Quitar clase después de la transición
            setTimeout(() => {
                modalImg.classList.remove('changing');
            }, 300);
        },

        handleMassiveUpload(event) {
            console.log('Subida masiva de archivos iniciada.');
            const files = Array.from(event.target.files);
            if (!files.length) {
                console.log('No se seleccionaron archivos para subir.');
                return;
            }

            const validFiles = files.filter(file => this.validateFile(file));
            console.log(`Archivos válidos para subir: ${validFiles.length}`);
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
            console.log(`Lotes de archivos para subir: ${batches.length}`);

            this.processBatches(batches, 0, validFiles.length);
        },
        processBatches(batches, uploadedCount, totalFiles) {
            console.log(`Iniciando proceso de lotes de subida. Total archivos: ${totalFiles}`);
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
                    console.log(`Subida en progreso: ${newUploadedCount}/${totalFiles} (${progress}%)`);
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
            console.log(`Validando archivo: ${file.name}`);
            if (!file.type.startsWith('image/')) {
                console.warn(`Archivo no válido (no es una imagen): ${file.name}`);
                return false;
            }

            const maxSize = 10 * 1024 * 1024;
            if (file.size > maxSize) {
                console.warn(`Archivo demasiado grande: ${file.name}`);
                return false;
            }

            return true;
        },

        showUploadProgress(totalFiles) {
            console.log(`Mostrando progreso de subida para ${totalFiles} archivos.`);
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
            console.log(`Actualizando progreso de subida: ${uploadedCount}/${totalFiles} (${progress}%)`);
            const progressBar = document.querySelector('.progress-bar');
            const statusText = document.getElementById('uploadStatus');
            
            if (progressBar && statusText) {
                progressBar.style.width = `${progress}%`;
                progressBar.setAttribute('aria-valuenow', progress);
                statusText.textContent = `Subiendo: ${uploadedCount} de ${totalFiles} fotos`;
            }
        },

        handleSync() {
            console.log('Iniciando sincronización con pCloud...');
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
                    console.log('Sincronización completada:', data.message || 'Fotos sincronizadas');
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
            console.log(`Intentando eliminar la foto con ID: ${photoId}`);
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
                    console.log(`Confirmación de eliminación recibida para la foto ID: ${photoId}`);
                    this.deletePhoto(photoId);
                }
            });
        },

        deletePhoto(photoId) {
            console.log(`Eliminando foto con ID: ${photoId}`);
            this.showLoading('Eliminando foto...');
        
            fetch(`/gallery/delete/${photoId}`, {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const element = document.querySelector(`.photo-card[data-photo-id="${photoId}"]`);
                    if (element) {
                        element.remove();  // Elimina la tarjeta de la galería sin recargar
                        console.log('Foto eliminada correctamente:', photoId);
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
            console.log(`Mostrando carga: ${message}`);
            Swal.fire({
                title: message,
                allowOutsideClick: false,
                didOpen: () => {
                    Swal.showLoading();
                }
            });
        },

        hideLoading() {
            console.log('Ocultando indicador de carga.');
            Swal.close();
        },

        showError(title, message) {
            console.log(`Mostrando error: ${title} - ${message}`);
            Swal.fire({
                icon: 'error',
                title: title,
                text: message,
                confirmButtonText: 'Aceptar'
            });
        },

        showSuccess(title, message) {
            console.log(`Mostrando mensaje de éxito: ${title} - ${message}`);
            Swal.fire({
                icon: 'success',
                title: title,
                text: message,
                confirmButtonText: 'Aceptar'
            });
        },

        initializeImagePreviews() {
            console.log('Inicializando vistas previas de imágenes.');
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