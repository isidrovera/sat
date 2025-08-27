// sat/static/src/js/gallery.js
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM Cargado. Iniciando script de galería...');
    
    const gallery = {
        // Nueva propiedad para acumular fotos
        capturedPhotos: [],
        currentSession: null,
        pcloudUploadUrl: null,
        
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
        // NUEVA FUNCIÓN: Obtener la siguiente secuencia disponible
        async getNextSequence() {
            console.log(`Obteniendo siguiente secuencia para reparación ${this.reparacionId}`);
            
            try {
                const response = await fetch(`/gallery/next-sequence/${this.reparacionId}`, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });
                
                if (!response.ok) {
                    throw new Error(`Error obteniendo secuencia: ${response.status}`);
                }
                
                const data = await response.json();
                
                // Manejar formato JSON-RPC de Odoo
                const result = data.result || data;
                const nextSequence = result.next_sequence || 1;
                
                console.log(`Siguiente secuencia obtenida: ${nextSequence}`);
                return nextSequence;
                
            } catch (error) {
                console.error('Error obteniendo secuencia:', error);
                // Fallback: usar timestamp como secuencia única
                return Date.now() % 10000;
            }
        },
        // NUEVA FUNCIÓN: Limpiar secuencias duplicadas (función de utilidad)
        async cleanupDuplicateSequences() {
            console.log(`Limpiando secuencias duplicadas para reparación ${this.reparacionId}`);
            
            try {
                const response = await fetch(`/gallery/cleanup-sequences/${this.reparacionId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });
                
                if (!response.ok) {
                    throw new Error(`Error en limpieza: ${response.status}`);
                }
                
                const data = await response.json();
                const result = data.result || data;
                
                console.log('Limpieza de secuencias completada:', result);
                return result;
                
            } catch (error) {
                console.error('Error limpiando secuencias:', error);
                return null;
            }
        },
        // NUEVA FUNCIÓN: Comprimir imagen antes de subir
        async compressImage(file, maxSizeMB = 6, quality = 0.8) {
            console.log(`Comprimiendo ${file.name}: ${(file.size/1024/1024).toFixed(2)}MB -> objetivo: ${maxSizeMB}MB`);
            
            return new Promise((resolve) => {
                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');
                const img = new Image();
                
                img.onload = () => {
                    let { width, height } = img;
                    
                    // Reducir dimensiones más agresivamente para archivos problemáticos
                    const maxDimension = maxSizeMB < 5 ? 1400 : 1600; // Dimensiones menores para compresión agresiva
                    
                    if (width > height) {
                        if (width > maxDimension) {
                            height = (height * maxDimension) / width;
                            width = maxDimension;
                        }
                    } else {
                        if (height > maxDimension) {
                            width = (width * maxDimension) / height;
                            height = maxDimension;
                        }
                    }
                    
                    canvas.width = width;
                    canvas.height = height;
                    ctx.drawImage(img, 0, 0, width, height);
                    
                    canvas.toBlob((blob) => {
                        const compressedSize = blob.size / 1024 / 1024;
                        console.log(`Compresión resultado: ${compressedSize.toFixed(2)}MB (${((file.size - blob.size) / file.size * 100).toFixed(1)}% reducción)`);
                        
                        // Si sigue siendo muy grande, comprimir hasta el límite
                        if (compressedSize > maxSizeMB && quality > 0.3) {
                            console.log(`Aún muy grande, comprimiendo más...`);
                            canvas.toBlob((finalBlob) => {
                                const finalFile = new File([finalBlob], file.name, {
                                    type: 'image/jpeg',
                                    lastModified: file.lastModified
                                });
                                resolve(finalFile);
                            }, 'image/jpeg', Math.max(0.3, quality - 0.2));
                            return;
                        }
                        
                        const compressedFile = new File([blob], file.name, {
                            type: 'image/jpeg',
                            lastModified: file.lastModified
                        });
                        resolve(compressedFile);
                    }, 'image/jpeg', quality);
                };
                
                img.src = URL.createObjectURL(file);
            });
        },
        // === NUEVO: pedir upload link al backend (pCloud) ===
        async getPcloudUploadUrl() {
            try {
                const resp = await fetch(`/gallery/pcloud/uploadlink/${this.reparacionId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                if (!resp.ok) throw new Error(`Server: ${resp.status}`);
                const data = await resp.json();
                const result = data.result || data;
                if (result.success && result.upload_url) {
                    return result.upload_url; // host+path para POST
                }
                return null;
            } catch (e) {
                console.error('[PCLOUD] No se pudo obtener upload link:', e);
                return null;
            }
        },

        // === NUEVO: subida directa a pCloud usando el upload link ===
        async uploadDirectToPcloud(file, uploadUrl) {
            // pCloud (upload link) acepta multipart; usamos campo "file" + filename.
            const fd = new FormData();
            fd.append('file', file, file.name);
            // algunos setups aceptan 'filename' adicional; no hace daño:
            fd.append('filename', file.name);

            // Renombrar si existe (si el servidor lo soporta vía query):
            const url = uploadUrl.includes('?') ? `${uploadUrl}&renameifexists=1` : `${uploadUrl}?renameifexists=1`;

            const resp = await fetch(url, { method: 'POST', body: fd });
            if (!resp.ok) {
                throw new Error(`PCLOUD_UPLOAD:${resp.status}`);
            }

            // pCloud devuelve HTML/JSON variado en upload link; con que sea 200 asumimos OK.
            return { success: true };
        },


        // MODIFICAR: Función uploadSingleFile completa con timeout y validaciones
        async uploadSingleFile(file, sessionId, retryAttempt = 0) {
    const maxRetries = 5;
    console.log(`Subiendo archivo: ${file.name} (${(file.size/1024/1024).toFixed(2)}MB) - Intento ${retryAttempt + 1}/${maxRetries + 1}`);
    
    // === NUEVO: si tenemos pcloudUploadUrl, intentamos primero directo a pCloud
    if (this.pcloudUploadUrl) {
        try {
            // (opcional) renombra para una convención consistente
            const safeName = file.name || `image_${Date.now()}.jpg`;
            const renamed = new File([file], safeName, { type: file.type || 'image/jpeg' });
            await this.uploadDirectToPcloud(renamed, this.pcloudUploadUrl);
            console.log(`✅ Subido a pCloud: ${renamed.name}`);
            return { success: true, filename: renamed.name, via: 'pcloud' };
        } catch (e) {
            console.warn('Fallo subida directa a pCloud; uso fallback Odoo:', e);
            // si falla pCloud, continuamos con el flujo Odoo como fallback
        }
    }

    // === Flujo original (Odoo) como fallback ===
    try {
        let processedFile = file;
        
        // Comprimir más agresivo en reintentos
        if (file.size > 6 * 1024 * 1024) {
            const compressionLevel = retryAttempt > 1 ? 0.5 : 0.8;
            const targetSize = retryAttempt > 2 ? 4 : 6;
            console.log(`Comprimiendo archivo (nivel ${compressionLevel}, objetivo ${targetSize}MB)...`);
            processedFile = await this.compressImage(file, targetSize, compressionLevel);
        }
        
        const nextSequence = await this.getNextSequence();
        console.log(`Secuencia asignada: ${nextSequence}`);
        
        const formData = new FormData();
        formData.append('file', processedFile);
        formData.append('sequence', nextSequence);
        formData.append('reparacion_id', this.reparacionId);
        
        // Timeout progresivo sin AbortController
        const baseTimeout = Math.max(45000, processedFile.size / 1024 / 1024 * 20000);
        const timeoutMs = baseTimeout + (retryAttempt * 15000);
        console.log(`Timeout: ${timeoutMs/1000}s (intento ${retryAttempt + 1})`);
        
        const fetchPromise = fetch(`/gallery/upload/single/${sessionId}`, {
            method: 'POST',
            body: formData
        });
        const timeoutPromise = new Promise((_, reject) => {
            setTimeout(() => reject(new Error(`TIMEOUT_ERROR:${timeoutMs/1000}s`)), timeoutMs);
        });
        
        const response = await Promise.race([fetchPromise, timeoutPromise]);
        if (!response.ok) {
            if ([504, 502, 503].includes(response.status)) {
                throw new Error(`SERVER_RETRY:${response.status}`);
            }
            throw new Error(`Error de servidor: ${response.status}`);
        }
        
        const data = await response.json();
        const result = data.result || data;
        
        if (!result.success) {
            if (result.code === 'SESSION_EXPIRED') {
                this.showAuthError();
                return null;
            }
            throw new Error(`SERVER_RETRY:${result.error}`);
        }
        
        console.log(`✅ ${processedFile.name} subido exitosamente (Odoo)`);
        return result;
        
    } catch (error) {
        console.error(`❌ Error en intento ${retryAttempt + 1}: ${error.message}`);
        
        // Decidir si reintentar
        const shouldRetry = (
            retryAttempt < maxRetries && (
                error.message.includes('TIMEOUT_ERROR') ||
                error.message.includes('SERVER_RETRY') ||
                error.message.includes('timeout') ||
                error.message.includes('network') ||
                error.message.includes('fetch') ||
                error.message.includes('Failed to fetch')
            )
        );
        
        if (shouldRetry) {
            const waitTime = Math.min(3000 + (retryAttempt * 2000), 10000);
            console.log(`🔄 Reintentando ${file.name} en ${waitTime/1000}s...`);
            await new Promise(resolve => setTimeout(resolve, waitTime));
            return this.uploadSingleFile(file, sessionId, retryAttempt + 1);
        }
        
        console.error(`💀 Se agotaron los ${maxRetries + 1} intentos para ${file.name}`);
        return { 
            success: false, 
            error: `Falló después de ${maxRetries + 1} intentos: ${error.message}`, 
            filename: file.name,
            finalAttempt: true
        };
    }
},

        // NUEVA FUNCIÓN: Finalizar sesión de subida
        async completeUploadSession(sessionId) {
            if (!sessionId) {
                console.warn('No hay sessionId para finalizar');
                return null;
            }
            
            console.log(`Finalizando sesión: ${sessionId}`);
            
            try {
                const response = await fetch(`/gallery/upload/complete/${sessionId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });

                if (!response.ok) {
                    // Si es 400, probablemente la sesión ya se finalizó o no existe
                    if (response.status === 400) {
                        console.warn(`Sesión ${sessionId} ya finalizada o no existe`);
                        return { success: true, message: 'Sesión ya finalizada' };
                    }
                    throw new Error(`Error de servidor: ${response.status}`);
                }

                const data = await response.json();
                console.log(`Sesión ${sessionId} finalizada correctamente`);
                return data;

            } catch (error) {
                console.error(`Error finalizando sesión ${sessionId}:`, error);
                // No relanzar el error para evitar interrumpir el flujo principal
                return { success: false, error: error.message };
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

        // Sube TODAS las fotos capturadas DIRECTO a pCloud usando /uploadtolink
async uploadAllCapturedPhotos() {
    const files = this.capturedPhotos || [];
    if (!files.length) {
        this.showError('Sin fotos', 'No hay fotos para subir');
        return;
    }

    // 1) Preparar upload link de pCloud (no expone token)
    const { linkCode } = await this.getPCloudUploadInfo();

    // 2) UI de progreso
    this.showUploadProgress(files.length);

    let uploaded = 0;
    let failed = 0;

    // 3) Subir SECUENCIAL para respetar las secuencias y simplificar
    for (let i = 0; i < files.length; i++) {
        const file = files[i];

        // Obtener la siguiente secuencia desde el backend (como ya tenías)
        const sequence = await this.getNextSequence();

        try {
            // 3.1) POST directo a pCloud /uploadtolink
            const fd = new FormData();
            fd.append('code', linkCode);
            fd.append('file', file, file.name);

            const resp = await fetch('https://api.pcloud.com/uploadtolink', {
                method: 'POST',
                body: fd,
            });

            if (!resp.ok) {
                throw new Error(`pCloud HTTP ${resp.status}`);
            }

            const pdata = await resp.json();
            if (pdata.result !== 0) {
                // Muestra detalle real
                throw new Error(`pCloud uploadtolink: ${pdata.error || JSON.stringify(pdata)}`);
            }

            // pCloud retorna metadata; según doc, puede venir como 'metadata' o 'fileids'
            let meta = null;
            if (Array.isArray(pdata.metadata) && pdata.metadata.length) {
                meta = pdata.metadata[0];
            } else if (pdata.fileids && pdata.fileids.length) {
                meta = { fileid: pdata.fileids[0], size: file.size, contenttype: file.type };
            }

            if (!meta || !meta.fileid) {
                throw new Error(`pCloud no devolvió fileid: ${JSON.stringify(pdata)}`);
            }

            // 3.2) Registrar en Odoo el archivo ya subido
            const regResp = await fetch('/gallery/pcloud/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    reparacion_id: this.reparacionId,
                    sequence: sequence,
                    filename: file.name,
                    pcloud: {
                        fileid: meta.fileid,
                        size: meta.size || file.size,
                        contenttype: meta.contenttype || file.type
                    }
                })
            });
            const regRaw = await regResp.json();
            const reg = regRaw.result || regRaw;
            if (!reg.success) {
                throw new Error(`Registro Odoo: ${reg.error || JSON.stringify(reg)}`);
            }

            uploaded += 1;
        } catch (err) {
            console.error(`Error subiendo ${file.name}:`, err);
            failed += 1;
        }

        const progress = ((i + 1) / files.length) * 100;
        this.updateUploadProgress(progress, uploaded + failed, files.length);

        // Pequeña pausa para evitar picos
        if (i < files.length - 1) {
            await new Promise(r => setTimeout(r, 200));
        }
    }

    // 4) Resultado
    if (uploaded === files.length) {
        this.showSuccess('Subida completada', `Se subieron las ${uploaded} fotos`);
    } else if (uploaded > 0) {
        this.showError('Subida parcial', `Se subieron ${uploaded} de ${files.length} fotos`);
    } else {
        this.showError('Error', 'No se pudo subir ninguna foto');
    }

    // Limpia sesión de cámara y refresca
    this.capturedPhotos = [];
    this.updateCameraButton();
    setTimeout(() => window.location.reload(), 1500);
},


        // MEJORADA: Subida masiva con nuevo sistema
        
        // SUSTITUIR COMPLETA
// Sube selección masiva (desde galería) DIRECTO a pCloud por lotes
async handleMassiveUpload(event) {
    const selected = Array.from(event.target.files || []);
    if (!selected.length) return;

    const files = selected.filter(f => this.validateFile(f));
    if (!files.length) {
        this.showError('Sin archivos válidos', 'Selecciona imágenes válidas');
        return;
    }

    // 1) Preparar upload link (una sola vez para todo el proceso)
    const { linkCode } = await this.getPCloudUploadInfo();

    // 2) Lotes pequeños para estabilidad
    const batchSize = 3;
    const batches = [];
    for (let i = 0; i < files.length; i += batchSize) {
        batches.push(files.slice(i, i + batchSize));
    }

    let uploaded = 0;
    let failed = 0;
    this.showBatchProgress(files.length, uploaded, failed);

    // 3) Procesar lote a lote (secuencial)
    for (let b = 0; b < batches.length; b++) {
        const batch = batches[b];

        // Dentro de cada lote, también SECUENCIAL para respetar secuencias
        for (let i = 0; i < batch.length; i++) {
            const file = batch[i];
            try {
                const sequence = await this.getNextSequence();

                const fd = new FormData();
                fd.append('code', linkCode);
                fd.append('file', file, file.name);

                const resp = await fetch('https://api.pcloud.com/uploadtolink', {
                    method: 'POST',
                    body: fd,
                });
                if (!resp.ok) {
                    throw new Error(`pCloud HTTP ${resp.status}`);
                }

                const pdata = await resp.json();
                if (pdata.result !== 0) {
                    throw new Error(`pCloud uploadtolink: ${pdata.error || JSON.stringify(pdata)}`);
                }

                let meta = null;
                if (Array.isArray(pdata.metadata) && pdata.metadata.length) {
                    meta = pdata.metadata[0];
                } else if (pdata.fileids && pdata.fileids.length) {
                    meta = { fileid: pdata.fileids[0], size: file.size, contenttype: file.type };
                }
                if (!meta || !meta.fileid) {
                    throw new Error(`pCloud no devolvió fileid: ${JSON.stringify(pdata)}`);
                }

                const regResp = await fetch('/gallery/pcloud/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        reparacion_id: this.reparacionId,
                        sequence: sequence,
                        filename: file.name,
                        pcloud: {
                            fileid: meta.fileid,
                            size: meta.size || file.size,
                            contenttype: meta.contenttype || file.type
                        }
                    })
                });
                const regRaw = await regResp.json();
                const reg = regRaw.result || regRaw;
                if (!reg.success) {
                    throw new Error(`Registro Odoo: ${reg.error || JSON.stringify(reg)}`);
                }

                uploaded += 1;
            } catch (err) {
                console.error(`Error subiendo ${file.name}:`, err);
                failed += 1;
            }

            this.updateBatchProgress(files.length, uploaded, failed);
            await new Promise(r => setTimeout(r, 300));
        }

        // Pausa entre lotes
        if (b < batches.length - 1) {
            await new Promise(r => setTimeout(r, 1200));
        }
    }

    // 4) Resultado final
    this.showFinalResult(files.length, uploaded, failed);
    if (uploaded > 0) {
        setTimeout(() => window.location.reload(), 1500);
    }

    // limpiar input
    event.target.value = '';
},

// === FUNCIÓN CORREGIDA: getPCloudUploadInfo ===
// REEMPLAZA la función existente en tu JS
async getPCloudUploadInfo() {
    console.log('[PCLOUD_UPLOADINFO] === INICIANDO SOLICITUD DE UPLOAD LINK ===');
    console.log('[PCLOUD_UPLOADINFO] Reparación ID:', this.reparacionId);
    
    try {
        const requestUrl = `/gallery/pcloud/uploadinfo/${this.reparacionId}`;
        console.log('[PCLOUD_UPLOADINFO] URL de solicitud:', requestUrl);
        
        // Mostrar loading mientras obtenemos el upload link
        Swal.fire({
            title: 'Preparando subida',
            text: 'Validando conexión con pCloud...',
            allowOutsideClick: false,
            showConfirmButton: false,
            didOpen: () => {
                Swal.showLoading();
            }
        });
        
        const response = await fetch(requestUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({}),
            credentials: 'same-origin' // Importante para mantener la sesión
        });
        
        console.log('[PCLOUD_UPLOADINFO] Response status:', response.status);
        console.log('[PCLOUD_UPLOADINFO] Response headers:', Object.fromEntries(response.headers.entries()));
        
        if (!response.ok) {
            console.error('[PCLOUD_UPLOADINFO] Error HTTP:', response.status, response.statusText);
            
            // Manejar errores específicos de HTTP
            switch (response.status) {
                case 401:
                    console.log('[PCLOUD_UPLOADINFO] Error 401 - Sesión expirada');
                    Swal.close();
                    this.showAuthError();
                    return null;
                case 403:
                    throw new Error('Sin permisos para realizar esta operación');
                case 500:
                    throw new Error('Error interno del servidor. Inténtalo más tarde.');
                default:
                    throw new Error(`Error de servidor: ${response.status} ${response.statusText}`);
            }
        }
        
        const rawData = await response.json();
        console.log('[PCLOUD_UPLOADINFO] Respuesta cruda del servidor:', rawData);
        
        // Manejar respuestas JSON-RPC de Odoo y respuestas directas
        let data;
        if (rawData.error) {
            console.error('[PCLOUD_UPLOADINFO] Error JSON-RPC:', rawData.error);
            
            // Manejar errores específicos de Odoo
            if (rawData.error.message && rawData.error.message.includes('Session')) {
                console.log('[PCLOUD_UPLOADINFO] Sesión de Odoo expirada');
                Swal.close();
                this.showAuthError();
                return null;
            }
            
            throw new Error(`Error del servidor: ${rawData.error.message || rawData.error}`);
        }
        
        // Los datos pueden estar en 'result' (JSON-RPC) o directamente en la respuesta
        data = rawData.result || rawData;
        console.log('[PCLOUD_UPLOADINFO] Datos procesados:', data);
        
        // Verificar el éxito de la operación
        if (data.success === false) {
            console.error('[PCLOUD_UPLOADINFO] Operación falló según respuesta:', data);
            
            // Manejar códigos de error específicos del backend
            switch (data.code) {
                case 'PCLOUD_TOKEN_INVALID':
                case 'PCLOUD_TOKEN_MISSING':
                    Swal.close();
                    Swal.fire({
                        icon: 'error',
                        title: 'Token de pCloud Inválido',
                        text: 'El token de acceso a pCloud ha expirado o es inválido. Contacta al administrador para renovarlo.',
                        confirmButtonText: 'Entendido',
                        allowOutsideClick: false
                    });
                    return null;
                    
                case 'PCLOUD_CONNECTION_ERROR':
                case 'PCLOUD_VALIDATION_TIMEOUT':
                    Swal.close();
                    Swal.fire({
                        icon: 'warning',
                        title: 'Problema de Conexión',
                        text: 'No se pudo conectar con pCloud. Verifica tu conexión e inténtalo nuevamente.',
                        confirmButtonText: 'Reintentar',
                        showCancelButton: true,
                        cancelButtonText: 'Cancelar'
                    }).then((result) => {
                        if (result.isConfirmed) {
                            // Reintentar automáticamente
                            setTimeout(() => this.getPCloudUploadInfo(), 2000);
                        }
                    });
                    return null;
                    
                case 'PCLOUD_CONFIG_MISSING':
                case 'PCLOUD_HOSTNAME_MISSING':
                    Swal.close();
                    Swal.fire({
                        icon: 'error',
                        title: 'Configuración Faltante',
                        text: 'La configuración de pCloud no está completa. Contacta al administrador.',
                        confirmButtonText: 'Entendido'
                    });
                    return null;
                    
                case 'REPARACION_NOT_FOUND':
                    Swal.close();
                    Swal.fire({
                        icon: 'error',
                        title: 'Reparación No Encontrada',
                        text: 'La reparación especificada no existe.',
                        confirmButtonText: 'Entendido'
                    }).then(() => {
                        window.history.back();
                    });
                    return null;
                    
                case 'PCLOUD_FOLDER_ERROR':
                case 'PCLOUD_FOLDER_CREATE_ERROR':
                    throw new Error(`Error creando carpeta en pCloud: ${data.error}`);
                    
                case 'PCLOUD_CREATELINK_ERROR':
                    throw new Error(`Error creando upload link: ${data.error}`);
                    
                default:
                    throw new Error(data.error || 'Error desconocido obteniendo upload link');
            }
        }
        
        // Verificar que tenemos todos los datos necesarios
        if (!data.link_code) {
            console.error('[PCLOUD_UPLOADINFO] Falta link_code en la respuesta:', data);
            throw new Error('Respuesta inválida del servidor: falta código de upload link');
        }
        
        if (!data.folder_id) {
            console.warn('[PCLOUD_UPLOADINFO] Falta folder_id en la respuesta (continuando)');
        }
        
        // Cerrar loading
        Swal.close();
        
        console.log('[PCLOUD_UPLOADINFO] === UPLOAD LINK OBTENIDO EXITOSAMENTE ===');
        console.log('[PCLOUD_UPLOADINFO] Link code:', data.link_code);
        console.log('[PCLOUD_UPLOADINFO] Folder ID:', data.folder_id);
        console.log('[PCLOUD_UPLOADINFO] Upload endpoint:', data.upload_endpoint);
        
        return {
            linkCode: data.link_code,
            folderId: data.folder_id,
            uploadEndpoint: data.upload_endpoint || 'https://api.pcloud.com/uploadtolink'
        };
        
    } catch (error) {
        console.error('[PCLOUD_UPLOADINFO] === ERROR CAPTURADO ===');
        console.error('[PCLOUD_UPLOADINFO] Tipo de error:', error.constructor.name);
        console.error('[PCLOUD_UPLOADINFO] Mensaje:', error.message);
        console.error('[PCLOUD_UPLOADINFO] Stack:', error.stack);
        
        // Cerrar cualquier loading dialog
        Swal.close();
        
        // Mostrar error apropiado al usuario
        let userMessage = 'Error preparando la subida a pCloud';
        let shouldRetry = false;
        
        if (error.message.includes('network') || 
            error.message.includes('fetch') || 
            error.message.includes('Failed to fetch') ||
            error.message.includes('conexión')) {
            userMessage = 'Error de conexión. Verifica tu internet e inténtalo nuevamente.';
            shouldRetry = true;
        } else if (error.message.includes('timeout')) {
            userMessage = 'La operación tardó demasiado. Inténtalo nuevamente.';
            shouldRetry = true;
        } else if (error.message.includes('500')) {
            userMessage = 'Error interno del servidor. Inténtalo más tarde.';
            shouldRetry = true;
        } else {
            userMessage = error.message || 'Error desconocido preparando la subida';
        }
        
        if (shouldRetry) {
            Swal.fire({
                icon: 'error',
                title: 'Error de Conexión',
                text: userMessage,
                confirmButtonText: 'Reintentar',
                showCancelButton: true,
                cancelButtonText: 'Cancelar'
            }).then((result) => {
                if (result.isConfirmed) {
                    // Esperar un momento antes de reintentar
                    setTimeout(() => this.getPCloudUploadInfo(), 3000);
                }
            });
        } else {
            Swal.fire({
                icon: 'error',
                title: 'Error',
                text: userMessage,
                confirmButtonText: 'Entendido'
            });
        }
        
        return null;
    }
},


// === NUEVO: subida directa a pCloud (uploadtolink) ===
async uploadSingleFileToPCloud(file, code, retryAttempt = 0) {
    const maxRetries = 4;
    try {
        const formData = new FormData();
        formData.append('code', code);
        formData.append('file', file); // pCloud acepta 'file' como campo

        // Nota: si CORS falla en tu navegador, usa el proxy:
        // const res = await fetch('/gallery/pcloud/proxy-upload', { method: 'POST', body: formData });

        const res = await fetch('https://api.pcloud.com/uploadtolink', { method: 'POST', body: formData });
        const data = await res.json();
        if (res.ok && data && data.result === 0) {
            return { success: true };
        }
        throw new Error(`pCloud: ${data && data.error ? data.error : 'error'}`);
    } catch (err) {
        const transient = /fetch|network|timeout|Failed|502|503|504/i.test(err.message);
        if (retryAttempt < maxRetries && transient) {
            await new Promise(r => setTimeout(r, 1000 + retryAttempt * 1500));
            return this.uploadSingleFileToPCloud(file, code, retryAttempt + 1);
        }
        return { success: false, error: err.message };
    }
},

// === NUEVO: sync sin UI ruidosa post-subida ===
async syncSilently() {
    try {
        const res = await fetch(`/gallery/sync/${this.reparacionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        const data = await res.json();
        return !!(res.ok && data && data.success);
    } catch { return false; }
},

        // NUEVA FUNCIÓN: Crear lotes
        createBatches(files, batchSize) {
            const batches = [];
            for (let i = 0; i < files.length; i += batchSize) {
                batches.push(files.slice(i, i + batchSize));
            }
            return batches;
        },

        // NUEVA FUNCIÓN: Subida con reintentos
        async uploadWithRetry(file, sessionId, maxRetries = 1) {
            // Simplificado - los reintentos están dentro de uploadSingleFile
            console.log(`Procesando ${file.name}`);
            return await this.uploadSingleFile(file, sessionId, 0);
        },

        // NUEVA FUNCIÓN: Progreso por lotes
        showBatchProgress(total, uploaded, failed) {
            Swal.fire({
                title: 'Subiendo por lotes',
                html: `
                    <div class="progress mb-3">
                        <div class="progress-bar bg-success" style="width: ${(uploaded/total*100)}%"></div>
                        <div class="progress-bar bg-danger" style="width: ${(failed/total*100)}%"></div>
                    </div>
                    <div>Procesadas: ${uploaded + failed}/${total}</div>
                    <div class="text-success">Exitosas: ${uploaded}</div>
                    <div class="text-danger">Fallidas: ${failed}</div>
                    <div class="mt-2"><small>Procesando en lotes pequeños para mayor confiabilidad...</small></div>
                `,
                allowOutsideClick: false,
                showConfirmButton: false
            });
        },

        // NUEVA FUNCIÓN: Actualizar progreso
        updateBatchProgress(total, uploaded, failed) {
            const uploadedPercent = (uploaded / total) * 100;
            const failedPercent = (failed / total) * 100;
            
            const progressHtml = `
                <div class="progress mb-3">
                    <div class="progress-bar bg-success" style="width: ${uploadedPercent}%"></div>
                    <div class="progress-bar bg-danger" style="width: ${failedPercent}%"></div>
                </div>
                <div>Procesadas: ${uploaded + failed}/${total}</div>
                <div class="text-success">Exitosas: ${uploaded}</div>
                <div class="text-danger">Fallidas: ${failed}</div>
                <div class="mt-2"><small>Procesando en lotes pequeños para mayor confiabilidad...</small></div>
            `;
            
            Swal.update({ html: progressHtml });
        },

        // NUEVA FUNCIÓN: Resultado final
        showFinalResult(total, uploaded, failed) {
            const successRate = ((uploaded / total) * 100).toFixed(1);
            
            if (uploaded === total) {
                Swal.fire({
                    icon: 'success',
                    title: 'Subida Completada',
                    text: `Se subieron las ${uploaded} fotos correctamente`,
                    timer: 2000
                });
            } else if (uploaded > 0) {
                Swal.fire({
                    icon: 'warning',
                    title: 'Subida Parcial',
                    html: `
                        <p>Se subieron <strong>${uploaded} de ${total}</strong> fotos</p>
                        <p>Tasa de éxito: <strong>${successRate}%</strong></p>
                        <p><small>Las fotos fallidas pueden deberse a problemas de conectividad</small></p>
                    `,
                    confirmButtonText: 'OK'
                });
            } else {
                Swal.fire({
                    icon: 'error',
                    title: 'Error en Subida',
                    text: 'No se pudieron subir las fotos. Verifica tu conexión e inténtalo de nuevo.',
                    confirmButtonText: 'OK'
                });
            }
        },

        validateFile(file) {
            console.log(`Validando archivo: ${file.name}, tipo: ${file.type}, tamaño: ${file.size} bytes`);
            
            if (!file.type.startsWith('image/')) {
                console.warn(`Archivo rechazado (no es una imagen): ${file.name}`);
                return false;
            }

            // Límite más generoso - la compresión se encargará del tamaño
            const maxSize = 25 * 1024 * 1024; // 25MB original
            if (file.size > maxSize) {
                console.warn(`Archivo rechazado (demasiado grande): ${file.name}`);
                this.showError('Archivo muy grande', `${file.name} excede el límite de 25MB`);
                return false;
            }

            if (file.size === 0) {
                console.warn(`Archivo rechazado (vacío): ${file.name}`);
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
                // Usar nuestro endpoint personalizado
                fetch('/web/session/check', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    credentials: 'same-origin'
                })
                .then(response => response.json())
                .then(data => {
                    if (!data.success || !data.is_authenticated || data.uid === false) {
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