// sat/static/src/js/gallery.js
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM Cargado. Iniciando script de galería...');
    
    const gallery = {
        // Nueva propiedad para acumular fotos
        capturedPhotos: [],
        currentSession: null,
        
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

        // NUEVA FUNCIÓN: Validar sesión antes de subir
        async validateUploadSession(files) {
        console.log(`[DEBUG] Iniciando validación para ${files.length} archivos`);
        
        const totalSize = files.reduce((sum, file) => sum + file.size, 0);
        console.log(`[DEBUG] Tamaño total calculado: ${totalSize} bytes`);
        
        try {
            console.log(`[DEBUG] Enviando request a: /gallery/upload/validate/${this.reparacionId}`);
            console.log(`[DEBUG] Body enviado:`, {
                file_count: files.length,
                total_size: totalSize
            });
            
            const response = await fetch(`/gallery/upload/validate/${this.reparacionId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    file_count: files.length,
                    total_size: totalSize
                })
            });

            console.log(`[DEBUG] Response status: ${response.status}`);
            console.log(`[DEBUG] Response ok: ${response.ok}`);
            
            if (!response.ok) {
                console.error(`[DEBUG] Response no ok, status: ${response.status}`);
                throw new Error(`Error de servidor: ${response.status}`);
            }

            const data = await response.json();
            console.log('[DEBUG] Respuesta RAW del servidor:', data);
            console.log('[DEBUG] Tipo de respuesta:', typeof data);
            console.log('[DEBUG] Tiene error?', !!data.error);
            console.log('[DEBUG] Tiene result?', !!data.result);
            
            // Manejar formato JSON-RPC de Odoo
            if (data.error) {
                console.log('[DEBUG] Detectado error en respuesta JSON-RPC:', data.error);
                if (data.error.message === 'Odoo Session Expired') {
                    console.log('[DEBUG] Sesión de Odoo expirada');
                    this.showAuthError();
                    return null;
                }
                console.error('[DEBUG] Error del servidor:', data.error.message);
                throw new Error(data.error.message || 'Error en validación');
            }

            // Si es respuesta JSON-RPC exitosa, los datos están en 'result'
            const result = data.result || data;
            console.log('[DEBUG] Datos procesados (result):', result);
            console.log('[DEBUG] result.success:', result.success);
            console.log('[DEBUG] result.session_id:', result.session_id);
            console.log('[DEBUG] result.error:', result.error);
            console.log('[DEBUG] result.code:', result.code);
            
            if (result.success === false) {
                console.log('[DEBUG] Validación falló, success === false');
                if (result.code === 'AUTH_REQUIRED') {
                    console.log('[DEBUG] Código AUTH_REQUIRED detectado');
                    this.showAuthError();
                    return null;
                }
                console.error('[DEBUG] Error de validación:', result.error);
                throw new Error(result.error || 'Error en validación');
            }

            // Verificar que tenemos session_id
            if (!result.session_id) {
                console.error('[DEBUG] No se recibió session_id');
                throw new Error('No se recibió session_id del servidor');
            }

            this.currentSession = result.session_id;
            console.log(`[DEBUG] Sesión validada exitosamente: ${this.currentSession}`);
            console.log('[DEBUG] Retornando result:', result);
            return result;

        } catch (error) {
            console.error('[DEBUG] Error capturado en catch:', error);
            console.error('[DEBUG] Tipo de error:', typeof error);
            console.error('[DEBUG] Error.message:', error.message);
            console.error('[DEBUG] Error completo:', error);
            this.showError('Error de Validación', error.message);
            return null;
        }
        },
        // NUEVA FUNCIÓN: Mostrar error de autenticación específico
        showAuthError() {
            console.log('Mostrando error de autenticación');
            Swal.fire({
                icon: 'warning',
                title: 'Sesión Expirada',
                text: 'Tu sesión ha expirado. Por favor, inicia sesión nuevamente.',
                confirmButtonText: 'Recargar Página',
                showCancelButton: true,
                cancelButtonText: 'Cancelar'
            }).then((result) => {
                if (result.isConfirmed) {
                    // Redirigir a login o recargar página
                    window.location.reload();
                }
            });
        },

        // NUEVA FUNCIÓN: Subir archivo individual con progreso
        async uploadSingleFile(file, sessionId) {
            console.log(`Subiendo archivo individual: ${file.name}`);
            
            const formData = new FormData();
            formData.append('file', file);
            
            try {
                const response = await fetch(`/gallery/upload/single/${sessionId}`, {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    throw new Error(`Error de servidor: ${response.status}`);
                }

                const data = await response.json();
                console.log('Respuesta de subida individual:', data);

                if (!data.success) {
                    // Manejar error de sesión expirada durante subida
                    if (data.code === 'SESSION_EXPIRED') {
                        this.showAuthError();
                        return null;
                    }
                    throw new Error(data.error || 'Error en subida');
                }

                return data;

            } catch (error) {
                console.error(`Error subiendo ${file.name}:`, error);
                return { success: false, error: error.message, filename: file.name };
            }
        },

        // NUEVA FUNCIÓN: Finalizar sesión de subida
        async completeUploadSession(sessionId) {
            console.log(`Finalizando sesión: ${sessionId}`);
            
            try {
                const response = await fetch(`/gallery/upload/complete/${sessionId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });

                if (!response.ok) {
                    throw new Error(`Error de servidor: ${response.status}`);
                }

                const data = await response.json();
                console.log('Sesión finalizada:', data);
                return data;

            } catch (error) {
                console.error('Error finalizando sesión:', error);
                return null;
            }
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

        // MEJORADA: Subida de fotos de cámara con nuevo sistema
        async uploadAllCapturedPhotos() {
            console.log(`Subiendo ${this.capturedPhotos.length} fotos capturadas`);
            
            if (this.capturedPhotos.length === 0) {
                this.showError('Sin fotos', 'No hay fotos para subir');
                return;
            }

            // Validar sesión primero
            const validation = await this.validateUploadSession(this.capturedPhotos);
            if (!validation) {
                console.log('Validación fallida, cancelando subida');
                return;
            }

            this.showUploadProgress(this.capturedPhotos.length);
            
            let uploadedCount = 0;
            let failedCount = 0;
            const results = [];

            // Subir archivos individualmente
            for (let i = 0; i < this.capturedPhotos.length; i++) {
                const file = this.capturedPhotos[i];
                console.log(`Subiendo foto ${i + 1}/${this.capturedPhotos.length}: ${file.name}`);
                
                const result = await this.uploadSingleFile(file, this.currentSession);
                
                if (result && result.success) {
                    uploadedCount++;
                    console.log(`Foto ${i + 1} subida exitosamente`);
                } else {
                    failedCount++;
                    console.log(`Foto ${i + 1} falló: ${result ? result.error : 'Error desconocido'}`);
                }
                
                results.push(result);
                
                // Actualizar progreso
                const progress = ((i + 1) / this.capturedPhotos.length) * 100;
                this.updateUploadProgress(progress, uploadedCount + failedCount, this.capturedPhotos.length);
                
                // Si hay error de autenticación, salir del bucle
                if (result && result.code === 'SESSION_EXPIRED') {
                    break;
                }
            }

            // Finalizar sesión
            await this.completeUploadSession(this.currentSession);

            // Mostrar resultado final
            if (uploadedCount > 0) {
                console.log(`Subida completada: ${uploadedCount} exitosos, ${failedCount} fallidos`);
                this.showSuccess(
                    'Fotos Subidas', 
                    failedCount === 0 
                        ? `Se subieron las ${uploadedCount} fotos correctamente`
                        : `Se subieron ${uploadedCount} de ${this.capturedPhotos.length} fotos`
                );
                
                // Limpiar sesión de cámara
                this.capturedPhotos = [];
                this.currentSession = null;
                this.updateCameraButton();
                setTimeout(() => window.location.reload(), 1500);
            } else {
                this.showError('Error', 'No se pudieron subir las fotos');
            }
        },

        // MEJORADA: Subida masiva con nuevo sistema
        async handleMassiveUpload(event) {
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

            // Validar sesión primero
            const validation = await this.validateUploadSession(validFiles);
            if (!validation) {
                console.log('Validación fallida, cancelando subida');
                return;
            }

            this.showUploadProgress(validFiles.length);

            let uploadedCount = 0;
            let failedCount = 0;
            const results = [];

            // Subir archivos individualmente con límite de concurrencia
            const batchSize = 3; // Subir máximo 3 archivos simultáneamente
            for (let i = 0; i < validFiles.length; i += batchSize) {
                const batch = validFiles.slice(i, i + batchSize);
                console.log(`Procesando lote ${Math.floor(i/batchSize) + 1}: ${batch.length} archivos`);
                
                const batchPromises = batch.map(file => this.uploadSingleFile(file, this.currentSession));
                const batchResults = await Promise.all(batchPromises);
                
                batchResults.forEach((result, index) => {
                    if (result && result.success) {
                        uploadedCount++;
                        console.log(`Archivo ${batch[index].name} subido exitosamente`);
                    } else {
                        failedCount++;
                        console.log(`Archivo ${batch[index].name} falló: ${result ? result.error : 'Error desconocido'}`);
                    }
                    results.push(result);
                });
                
                // Actualizar progreso
                const progress = ((i + batch.length) / validFiles.length) * 100;
                this.updateUploadProgress(Math.min(progress, 100), uploadedCount + failedCount, validFiles.length);
                
                // Verificar si hay errores de autenticación
                if (batchResults.some(result => result && result.code === 'SESSION_EXPIRED')) {
                    break;
                }
            }

            // Finalizar sesión
            await this.completeUploadSession(this.currentSession);

            // Mostrar resultado final
            if (uploadedCount > 0) {
                console.log(`Subida masiva completada: ${uploadedCount} exitosos, ${failedCount} fallidos`);
                this.showSuccess(
                    'Subida Completada', 
                    failedCount === 0 
                        ? `Se subieron los ${uploadedCount} archivos correctamente`
                        : `Se subieron ${uploadedCount} de ${validFiles.length} archivos`
                );
                setTimeout(() => window.location.reload(), 1500);
            } else {
                this.showError('Error', 'No se pudieron subir los archivos');
            }

            // Limpiar session
            this.currentSession = null;
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
                    // Manejar error de autenticación en eliminación
                    if (data.code === 'AUTH_REQUIRED') {
                        this.showAuthError();
                        return;
                    }
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
                                
                                // NUEVO: Manejar errores de carga de imagen con endpoint de preview
                                img.addEventListener('error', () => {
                                    console.log('Error cargando imagen, intentando con placeholder');
                                    const photoId = img.closest('.photo-card')?.dataset.photoId;
                                    if (photoId) {
                                        img.src = `/gallery/preview/${photoId}`;
                                    }
                                });
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
                        
                        // NUEVO: Manejar errores de carga de imagen
                        img.addEventListener('error', () => {
                            console.log('Error cargando imagen, intentando con placeholder');
                            const photoId = img.closest('.photo-card')?.dataset.photoId;
                            if (photoId) {
                                img.src = `/gallery/preview/${photoId}`;
                            }
                        });
                    }
                });
            }
            
            console.log('Inicialización de vistas previas completada');
        },

        // NUEVA FUNCIÓN: Verificar estado de autenticación periódicamente
        startAuthCheck() {
            console.log('Iniciando verificación periódica de autenticación');
            
            setInterval(() => {
                // Verificar cada 5 minutos si el usuario sigue autenticado
                fetch('/web/session/get_session_info')
                    .then(response => response.json())
                    .then(data => {
                        if (!data || !data.uid || data.uid === false) {
                            console.log('Sesión expirada detectada');
                            this.showAuthError();
                        }
                    })
                    .catch(error => {
                        console.warn('Error verificando autenticación:', error);
                    });
            }, 5 * 60 * 1000); // 5 minutos
        },

        // NUEVA FUNCIÓN: Reintentar operación fallida
        retryOperation(operationType, ...args) {
            console.log(`Reintentando operación: ${operationType}`);
            
            switch (operationType) {
                case 'upload_camera':
                    this.uploadAllCapturedPhotos();
                    break;
                case 'upload_files':
                    this.handleMassiveUpload(args[0]);
                    break;
                case 'delete_photo':
                    this.deletePhoto(args[0]);
                    break;
                case 'sync':
                    this.handleSync();
                    break;
                default:
                    console.warn(`Tipo de operación desconocido: ${operationType}`);
            }
        }
    };

    // Inicializar galería
    gallery.init();
    
    // NUEVO: Iniciar verificación de autenticación
    gallery.startAuthCheck();
});