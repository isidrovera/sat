// sat/static/src/js/gallery.js
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM Cargado. Iniciando script de galería...');
    
    const gallery = {
        // Nueva propiedad para acumular fotos
        capturedPhotos: [],
        
        init() {
            console.log('Iniciando galería...');
            this.initializeElements();
            this.bindEvents();
            this.initializeImagePreviews();
            this.initializeCameraSession();
            
            console.log('Inicialización completa de galería');
        },

        initializeElements() {
            console.log('Inicializando elementos DOM...');
            this.fileInput = document.getElementById('fileUpload');
            this.cameraInput = document.getElementById('cameraCapture');
            this.photoGrid = document.querySelector('#photoGrid');
            this.syncButton = document.getElementById('syncButton');
            this.shareGalleryBtn = document.getElementById('shareGalleryBtn');
            this.cameraBtn = document.getElementById('cameraBtn');
            this.loadingOverlay = document.getElementById('loadingOverlay');
            this.reparacionId = window.location.pathname.split('/').pop();
            
            console.log('Elementos inicializados:', {
                fileInput: this.fileInput ? 'Encontrado' : 'No encontrado',
                cameraInput: this.cameraInput ? 'Encontrado' : 'No encontrado',
                photoGrid: this.photoGrid ? 'Encontrado' : 'No encontrado',
                syncButton: this.syncButton ? 'Encontrado' : 'No encontrado',
                shareGalleryBtn: this.shareGalleryBtn ? 'Encontrado' : 'No encontrado',
                cameraBtn: this.cameraBtn ? 'Encontrado' : 'No encontrado',
                loadingOverlay: this.loadingOverlay ? 'Encontrado' : 'No encontrado',
                reparacionId: this.reparacionId,
            });
            
            // Si no existe el input de cámara, crearlo dinámicamente
            if (!this.cameraInput) {
                console.log('Input de cámara no encontrado, creándolo dinámicamente...');
                this.cameraInput = document.createElement('input');
                this.cameraInput.type = 'file';
                this.cameraInput.id = 'cameraCapture';
                this.cameraInput.style.display = 'none';
                this.cameraInput.accept = 'image/*';
                this.cameraInput.setAttribute('capture', 'camera');
                document.body.appendChild(this.cameraInput);
                console.log('Input de cámara creado dinámicamente');
            }
            
            this.setupFileInputs();
        },

        initializeCameraSession() {
            console.log('Inicializando sesión de cámara...');
            this.capturedPhotos = [];
            this.updateCameraButton();
        },

        setupFileInputs() {
            console.log('Configurando inputs para fotos y cámara...');
            
            // Configurar input para seleccionar fotos de galería
            if (this.fileInput) {
                console.log('Configurando input para múltiples fotos de galería...');
                this.fileInput.setAttribute('multiple', 'multiple');
                this.fileInput.setAttribute('accept', 'image/*');

                if (this.isMobile()) {
                    console.log('Configuración específica para dispositivos móviles - galería');
                    this.fileInput.addEventListener('click', function() {
                        this.setAttribute('multiple', 'multiple');
                    });
                    this.fileInput.addEventListener('change', (e) => {
                        console.log('Evento change en input de archivos de galería (móvil)');
                        this.handleMassiveUpload(e);
                    });
                }
            } else {
                console.warn('No se encontró el elemento fileInput');
            }

            // Configurar input para captura de cámara
            if (this.cameraInput) {
                console.log('Configurando input para captura de cámara...');
                this.cameraInput.setAttribute('accept', 'image/*');
                this.cameraInput.setAttribute('capture', 'camera');
                
                if (this.isMobile()) {
                    console.log('Configuración específica para dispositivos móviles - cámara');
                    this.cameraInput.addEventListener('change', (e) => {
                        console.log('Evento change en input de cámara (móvil)');
                        this.handleCameraCapture(e);
                    });
                }
            } else {
                console.warn('No se encontró el elemento cameraInput');
            }
        },

        isMobile() {
            const isMobileDevice = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
            console.log('Detección de dispositivo móvil:', isMobileDevice);
            return isMobileDevice;
        },

        bindEvents() {
            console.log('Iniciando bindEvents...');
            
            // Eventos para input de galería (escritorio)
            if (this.fileInput && !this.isMobile()) {
                console.log('Vinculando evento change para subida de archivos de galería (escritorio)');
                this.fileInput.addEventListener('change', (e) => this.handleMassiveUpload(e));
            }

            // Eventos para input de cámara (escritorio)
            if (this.cameraInput && !this.isMobile()) {
                console.log('Vinculando evento change para captura de cámara (escritorio)');
                this.cameraInput.addEventListener('change', (e) => this.handleCameraCapture(e));
            }

            // Evento para botón de cámara
            if (this.cameraBtn) {
                console.log('Vinculando evento para botón de cámara');
                this.cameraBtn.addEventListener('click', () => this.handleCameraButtonClick());
            } else {
                console.log('No se encontró cameraBtn - buscando alternativas...');
                const alternativeCameraBtn = document.querySelector('button[id*="camera"], .btn-camera, button:has(i.fa-camera)');
                if (alternativeCameraBtn) {
                    console.log('Botón de cámara encontrado por selector alternativo');
                    this.cameraBtn = alternativeCameraBtn;
                    this.cameraBtn.addEventListener('click', () => this.handleCameraButtonClick());
                } else {
                    console.warn('No se pudo encontrar botón de cámara por ningún método');
                }
            }
        
            if (this.syncButton) {
                console.log('Vinculando evento para botón de sincronización');
                this.syncButton.addEventListener('click', () => this.handleSync());
            } else {
                console.log('No se encontró syncButton');
            }
        
            if (this.shareGalleryBtn) {
                console.log('Vinculando evento para botón de compartir');
                this.shareGalleryBtn.addEventListener('click', () => this.handleShareGallery());
            } else {
                console.log('No se encontró shareGalleryBtn');
            }
            
            console.log('Vinculando eventos para botones de descarga');
            document.querySelectorAll('.download-photo').forEach(btn => {
                btn.addEventListener('click', (e) => this.handleDownload(e));
                console.log('Evento de descarga vinculado para foto ID:', btn.dataset.photoId || 'sin ID');
            });
        
            console.log('Vinculando eventos para botones de eliminación');
            document.querySelectorAll('.delete-photo').forEach(btn => {
                btn.addEventListener('click', (e) => this.handleDelete(e));
                console.log('Evento de eliminación vinculado para foto ID:', btn.dataset.photoId || 'sin ID');
            });
            
            console.log('Eventos vinculados correctamente');
        },

        handleCameraButtonClick() {
            console.log(`Estado actual: ${this.capturedPhotos.length} fotos capturadas`);
            
            if (this.capturedPhotos.length === 0) {
                // Primera vez: iniciar sesión de cámara
                console.log('Iniciando nueva sesión de cámara');
                this.triggerCamera();
            } else {
                // Ya hay fotos: mostrar opciones
                console.log('Mostrando opciones de cámara');
                this.showCameraOptions();
            }
        },

        showCameraOptions() {
            console.log(`Mostrando opciones con ${this.capturedPhotos.length} fotos`);
            
            Swal.fire({
                title: `${this.capturedPhotos.length} Fotos Capturadas`,
                text: '¿Qué deseas hacer?',
                icon: 'question',
                showCancelButton: true,
                showDenyButton: true,
                confirmButtonText: `📸 Tomar Otra (${this.capturedPhotos.length + 1})`,
                denyButtonText: `💾 Subir Todas (${this.capturedPhotos.length})`,
                cancelButtonText: '❌ Cancelar',
                confirmButtonColor: '#3085d6',
                denyButtonColor: '#28a745',
                cancelButtonColor: '#6c757d'
            }).then((result) => {
                if (result.isConfirmed) {
                    console.log('Usuario eligió tomar otra foto');
                    this.triggerCamera();
                } else if (result.isDenied) {
                    console.log('Usuario eligió subir todas las fotos');
                    this.uploadAllCapturedPhotos();
                } else {
                    console.log('Usuario canceló la operación');
                }
            });
        },

        triggerCamera() {
            console.log('Activando captura de cámara...');
            
            // Verificar que el input de cámara existe
            if (!this.cameraInput) {
                console.error('Input de cámara no disponible, intentando crear uno temporal...');
                this.createTemporaryCameraInput();
                return;
            }
            
            console.log('Disparando click en input de cámara');
            this.cameraInput.click();
        },

        createTemporaryCameraInput() {
            console.log('Creando input temporal de cámara');
            const tempInput = document.createElement('input');
            tempInput.type = 'file';
            tempInput.accept = 'image/*';
            tempInput.setAttribute('capture', 'camera');
            tempInput.style.display = 'none';
            tempInput.addEventListener('change', (e) => {
                console.log('Evento change en input temporal de cámara');
                this.handleCameraCapture(e);
                document.body.removeChild(tempInput);
            });
            document.body.appendChild(tempInput);
            console.log('Disparando click en input temporal de cámara');
            tempInput.click();
        },

        handleCameraCapture(event) {
            console.log('Iniciando proceso de captura de cámara');
            const files = Array.from(event.target.files);
            console.log(`Total de fotos capturadas: ${files.length}`);
            
            if (!files.length) {
                console.log('No se capturaron fotos');
                return;
            }

            const validFiles = files.filter(file => this.validateFile(file));
            console.log(`Fotos válidas capturadas: ${validFiles.length} de ${files.length}`);
            
            if (!validFiles.length) {
                this.showError('Foto no válida', 'La foto capturada no es válida');
                return;
            }

            // Agregar fotos a la colección en lugar de subirlas inmediatamente
            validFiles.forEach(file => {
                const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
                const newName = `camera_${timestamp}_${this.capturedPhotos.length + 1}.jpg`;
                console.log(`Agregando foto a la sesión: ${newName}`);
                
                const renamedFile = new File([file], newName, { type: file.type });
                this.capturedPhotos.push(renamedFile);
            });

            console.log(`Total de fotos en sesión: ${this.capturedPhotos.length}`);
            this.updateCameraButton();
            
            // Preguntar inmediatamente qué hacer
            setTimeout(() => {
                this.showCameraOptions();
            }, 500);

            // Limpiar el input para permitir capturar la misma foto nuevamente
            event.target.value = '';
        },

        updateCameraButton() {
            if (!this.cameraBtn) return;
            
            const count = this.capturedPhotos.length;
            console.log(`Actualizando botón de cámara: ${count} fotos`);
            
            if (count === 0) {
                this.cameraBtn.innerHTML = '<i class="fa fa-camera"></i> Tomar Foto';
                this.cameraBtn.className = 'btn btn-primary';
            } else {
                this.cameraBtn.innerHTML = `<i class="fa fa-camera"></i> Cámara (${count})`;
                this.cameraBtn.className = 'btn btn-warning';
            }
        },

        uploadAllCapturedPhotos() {
            console.log(`Subiendo ${this.capturedPhotos.length} fotos capturadas`);
            
            if (this.capturedPhotos.length === 0) {
                this.showError('Sin fotos', 'No hay fotos para subir');
                return;
            }

            this.showUploadProgress(this.capturedPhotos.length);
            
            const formData = new FormData();
            this.capturedPhotos.forEach((file, index) => {
                console.log(`Agregando foto ${index + 1} al FormData: ${file.name}, tamaño: ${file.size} bytes`);
                formData.append('files[]', file);
            });

            console.log(`Enviando ${this.capturedPhotos.length} fotos al servidor: /gallery/upload/${this.reparacionId}`);
            fetch(`/gallery/upload/${this.reparacionId}`, {
                method: 'POST',
                body: formData
            })
            .then(response => {
                console.log(`Respuesta recibida del servidor: ${response.status} ${response.statusText}`);
                if (!response.ok) {
                    throw new Error(`Error de servidor: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('Respuesta procesada:', data);
                if (data.success) {
                    console.log('Fotos de cámara subidas exitosamente');
                    this.showSuccess('Fotos Subidas', `Se subieron ${this.capturedPhotos.length} fotos correctamente`);
                    // Limpiar sesión de cámara
                    this.capturedPhotos = [];
                    this.updateCameraButton();
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    console.error(`Error reportado por el servidor: ${data.error || 'Error desconocido'}`);
                    throw new Error(data.error || 'Error en la subida de fotos de cámara');
                }
            })
            .catch(error => {
                console.error('Error en subida de fotos de cámara:', error);
                this.showError('Error', error.message || 'Ocurrió un error durante la subida de fotos de cámara');
            });
        },

        handleMassiveUpload(event) {
            console.log('Iniciando proceso de subida masiva de archivos de galería');
            const files = Array.from(event.target.files);
            console.log(`Total de archivos seleccionados de galería: ${files.length}`);
            
            if (!files.length) {
                console.log('No se seleccionaron archivos para subir');
                return;
            }

            const validFiles = files.filter(file => this.validateFile(file));
            console.log(`Archivos válidos para subir: ${validFiles.length} de ${files.length}`);
            
            if (!validFiles.length) {
                this.showError('No hay archivos válidos', 'Por favor seleccione imágenes válidas');
                return;
            }

            this.showUploadProgress(validFiles.length);

            // Dividir archivos en lotes para evitar problemas de tamaño
            const batchSize = 5;
            const batches = [];
            for (let i = 0; i < validFiles.length; i += batchSize) {
                batches.push(validFiles.slice(i, i + batchSize));
            }
            console.log(`Lotes de archivos para subir: ${batches.length}`);

            this.processBatches(batches, 0, validFiles.length);
        },

        processBatches(batches, uploadedCount, totalFiles) {
            console.log(`Procesando lotes: ${batches.length} lotes pendientes, ${uploadedCount}/${totalFiles} archivos subidos`);
            
            if (batches.length === 0) {
                console.log('Todos los lotes procesados. Subida completa.');
                this.showSuccess('Subida Completada', `Se subieron ${uploadedCount} fotos correctamente`);
                setTimeout(() => window.location.reload(), 1500);
                return;
            }

            const currentBatch = batches.shift();
            console.log(`Procesando lote con ${currentBatch.length} archivos`);
            
            const formData = new FormData();
            currentBatch.forEach(file => {
                console.log(`Agregando archivo al FormData: ${file.name}, tamaño: ${file.size} bytes`);
                formData.append('files[]', file);
            });

            console.log(`Enviando lote al servidor: /gallery/upload/${this.reparacionId}`);
            fetch(`/gallery/upload/${this.reparacionId}`, {
                method: 'POST',
                body: formData
            })
            .then(response => {
                console.log(`Respuesta recibida del servidor: ${response.status} ${response.statusText}`);
                if (!response.ok) {
                    throw new Error(`Error de servidor: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('Respuesta procesada:', data);
                if (data.success) {
                    const newUploadedCount = uploadedCount + currentBatch.length;
                    const progress = (newUploadedCount / totalFiles) * 100;
                    console.log(`Subida en progreso: ${newUploadedCount}/${totalFiles} (${progress.toFixed(1)}%)`);
                    this.updateUploadProgress(progress, newUploadedCount, totalFiles);
                    this.processBatches(batches, newUploadedCount, totalFiles);
                } else {
                    console.error(`Error reportado por el servidor: ${data.error || 'Error desconocido'}`);
                    throw new Error(data.error || 'Error en la subida');
                }
            })
            .catch(error => {
                console.error('Error en proceso de subida:', error);
                this.showError('Error', error.message || 'Ocurrió un error durante la subida');
            });
        },

        validateFile(file) {
            console.log(`Validando archivo: ${file.name}, tipo: ${file.type}, tamaño: ${file.size} bytes`);
            
            if (!file.type.startsWith('image/')) {
                console.warn(`Archivo rechazado (no es una imagen): ${file.name}`);
                return false;
            }

            const maxSize = 10 * 1024 * 1024; // 10MB
            if (file.size > maxSize) {
                console.warn(`Archivo rechazado (excede tamaño máximo): ${file.name} (${file.size} bytes, máximo: ${maxSize} bytes)`);
                return false;
            }

            console.log(`Archivo validado correctamente: ${file.name}`);
            return true;
        },

        showUploadProgress(totalFiles) {
            console.log(`Mostrando UI de progreso para ${totalFiles} archivos`);
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
            console.log(`Actualizando UI de progreso: ${uploadedCount}/${totalFiles} (${progress.toFixed(1)}%)`);
            const progressBar = document.querySelector('.progress-bar');
            const statusText = document.getElementById('uploadStatus');
            
            if (progressBar && statusText) {
                progressBar.style.width = `${progress}%`;
                progressBar.setAttribute('aria-valuenow', progress);
                statusText.textContent = `Subiendo: ${uploadedCount} de ${totalFiles} fotos`;
            } else {
                console.warn('No se encontraron elementos de UI para actualizar el progreso');
            }
        },
              
        handleDownload(event) {
            event.preventDefault();
            const button = event.currentTarget;
            const photoId = button.dataset.photoId;
            console.log(`Solicitando descarga para la foto con ID: ${photoId}`);
        
            fetch(`/gallery/download/${photoId}`)
                .then(response => {
                    if (!response.ok) {
                        console.error(`Error en respuesta del servidor: ${response.status} ${response.statusText}`);
                        throw new Error('No se pudo obtener el archivo');
                    }
                    console.log('Respuesta del servidor correcta, obteniendo blob');
                    return response.blob();
                })
                .then(blob => {
                    console.log(`Blob recibido: tipo=${blob.type}, tamaño=${blob.size} bytes`);
                    const url = window.URL.createObjectURL(blob);
                    const link = document.createElement('a');
                    link.href = url;
                    
                    const filename = button.getAttribute('data-filename') || 'foto.jpg';
                    console.log(`Descargando como: ${filename}`);
                    link.setAttribute('download', filename);
                    
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
            console.log('Función handleShareGallery iniciada');
        
            const currentUrl = window.location.href;
            console.log(`URL para compartir: ${currentUrl}`);
        
            if (!currentUrl) {
                console.error('No se pudo obtener la URL actual');
                return;
            }
        
            if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
                console.log('Usando Clipboard API para copiar URL');
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
                        this.tryClipboardAPI(currentUrl);
                    });
            } else {
                console.warn('Clipboard API no disponible. Usando método alternativo.');
                this.tryClipboardAPI(currentUrl);
            }
        },
        
        tryClipboardAPI(currentUrl) {
            console.log('Intentando método alternativo con tryClipboardAPI');
            
            if (navigator.clipboard && window.isSecureContext) {
                console.log('Contexto seguro detectado, usando navigator.clipboard');
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
                console.warn('Clipboard API no disponible o contexto no seguro, usando método fallback');
                this.fallbackCopyText(currentUrl);
            }
        },
        
        fallbackCopyText(text) {
            console.log('Usando método fallback para copiar texto');
            const tempInput = document.createElement('textarea');
            tempInput.style.position = 'fixed';
            tempInput.style.opacity = '0';
            tempInput.value = text;
            document.body.appendChild(tempInput);
        
            try {
                console.log('Configurando textarea para selección');
                tempInput.contentEditable = true;
                tempInput.readOnly = false;
                
                const range = document.createRange();
                range.selectNodeContents(tempInput);
                const selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
                tempInput.setSelectionRange(0, text.length);
                
                console.log('Ejecutando comando de copia');
                const successful = document.execCommand('copy');
                if (successful) {
                    console.log('Texto copiado exitosamente usando método fallback');
                    this.showSuccess('URL Copiada', 'El enlace ha sido copiado al portapapeles');
                } else {
                    console.error('Comando execCommand retornó false');
                    throw new Error('No se pudo copiar el texto');
                }
            } catch (err) {
                console.error('Error en fallbackCopyText:', err);
                this.showError('Error', 'No se pudo copiar la URL');
            } finally {
                console.log('Limpiando elementos temporales');
                document.body.removeChild(tempInput);
            }
        },

        handleSync() {
            console.log('Iniciando sincronización con pCloud');
            this.showLoading('Sincronizando con pCloud...');

            fetch(`/gallery/sync/${this.reparacionId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({})
            })
            .then(response => {
                console.log(`Respuesta del servidor: ${response.status} ${response.statusText}`);
                if (!response.ok) {
                    throw new Error(`Error de servidor: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('Respuesta procesada:', data);
                if (data.success) {
                    console.log('Sincronización completada');
                    this.showSuccess('Sincronización completada', data.message || 'Fotos sincronizadas');
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    console.error(`Error reportado por el servidor: ${data.error || 'Error desconocido'}`);
                    throw new Error(data.error || 'Error al sincronizar');
                }
            })
            .catch(error => {
                console.error('Error en sincronización:', error);
                this.showError('Error', error.message || 'Ocurrió un error durante la sincronización');
            })
            .finally(() => {
                console.log('Finalizando operación de sincronización');
                this.hideLoading();
            });
        },

        handleDelete(event) {
            const button = event.currentTarget;
            const photoId = button.dataset.photoId;
            console.log(`Solicitando eliminar foto con ID: ${photoId}`);
            
            if (!photoId) {
                console.error('No se encontró ID de foto en el botón');
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
                    console.log(`Confirmación recibida para eliminar foto ID: ${photoId}`);
                    this.deletePhoto(photoId);
                } else {
                    console.log('Eliminación cancelada por el usuario');
                }
            });
        },

        deletePhoto(photoId) {
            console.log(`Ejecutando eliminación de foto ID: ${photoId}`);
            this.showLoading('Eliminando foto...');
        
            fetch(`/gallery/delete/${photoId}`, {
                method: 'POST'
            })
            .then(response => {
                console.log(`Respuesta del servidor: ${response.status} ${response.statusText}`);
                if (!response.ok) {
                    throw new Error(`Error de servidor: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('Respuesta procesada:', data);
                if (data.success) {
                    const element = document.querySelector(`.photo-card[data-photo-id="${photoId}"]`);
                    if (element) {
                        console.log('Eliminando tarjeta de foto del DOM');
                        element.remove();
                        console.log('Foto eliminada correctamente:', photoId);
                        this.showSuccess('Éxito', 'Foto eliminada correctamente');
                    } else {
                        console.warn(`No se encontró elemento DOM para foto ID: ${photoId}`);
                        setTimeout(() => window.location.reload(), 1500);
                    }
                } else {
                    console.error(`Error reportado por el servidor: ${data.error || 'Error desconocido'}`);
                    throw new Error(data.error || 'Error al eliminar la foto');
                }
            })
            .catch(error => {
                console.error('Error en eliminación:', error);
                this.showError('Error', error.message || 'No se pudo eliminar la foto');
            })
            .finally(() => {
                console.log('Finalizando operación de eliminación');
                this.hideLoading();
            });
        },
        
        showLoading(message = 'Cargando...') {
            console.log(`Mostrando indicador de carga: "${message}"`);
            Swal.fire({
                title: message,
                allowOutsideClick: false,
                didOpen: () => {
                    Swal.showLoading();
                }
            });
        },

        hideLoading() {
            console.log('Ocultando indicador de carga');
            Swal.close();
        },

        showError(title, message) {
            console.log(`Mostrando mensaje de error: ${title} - ${message}`);
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
            console.log('Inicializando vistas previas de imágenes');
            
            const photoCards = document.querySelectorAll('.photo-card');
            console.log(`Se encontraron ${photoCards.length} tarjetas de fotos`);
            
            if ('IntersectionObserver' in window) {
                console.log('Usando IntersectionObserver para carga eficiente');
                
                const imageObserver = new IntersectionObserver((entries, observer) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            console.log('Imagen entrando en viewport, configurando');
                            const img = entry.target;
                            if (!img.classList.contains('loaded')) {
                                img.classList.add('loaded');
                            }
                        }
                    });
                });

                photoCards.forEach(card => {
                    const img = card.querySelector('img');
                    if (img && !img.classList.contains('loaded')) {
                        imageObserver.observe(img);
                    }
                });
            } else {
                console.log('IntersectionObserver no disponible, cargando todas las imágenes directamente');
                photoCards.forEach(card => {
                    const img = card.querySelector('img');
                    if (img && !img.classList.contains('loaded')) {
                        img.classList.add('loaded');
                    }
                });
            }
            
            console.log('Inicialización de vistas previas completada');
        }
    };

    // Inicializar galería
    gallery.init();
});