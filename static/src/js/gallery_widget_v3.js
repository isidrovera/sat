// sat/static/src/js/gallery.js - Parte 1 de 4: Inicialización y Configuración
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM Cargado. Iniciando script de galería...');
    
    const gallery = {
        // ========== PROPIEDADES BASE ==========
        capturedPhotos: [],
        progressInterval: null,
        
        // Propiedades para subida paralela
        uploadState: {
            isUploading: false,
            sessionId: null,
            currentFiles: [],
            uploadedCount: 0,
            failedCount: 0,
            totalCount: 0,
            failedFiles: [],
            startTime: null
        },
        
        // Configuración de subida paralela
        uploadConfig: {
            maxParallelUploads: 3,
            retryAttempts: 3,
            retryDelay: 1000,
            chunkSize: 2
        },

        // Estado de cámara
        cameraState: {
            isCapturing: false,
            sessionActive: false,
            compressionEnabled: true,
            compressionQuality: 0.8
        },

        // ========== MÉTODOS DE INICIALIZACIÓN ==========
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
            this.cameraState = {
                isCapturing: false,
                sessionActive: false,
                compressionEnabled: true,
                compressionQuality: 0.8
            };
            this.updateCameraButton();
        },

        setupFileInputs() {
            console.log('Configurando inputs para fotos y cámara...');
            
            // Configurar input para seleccionar fotos de galería
            if (this.fileInput) {
                console.log('Configurando input para múltiples fotos de galería...');
                this.fileInput.setAttribute('multiple', 'multiple');
                this.fileInput.setAttribute('accept', 'image/*');
                this.fileInput.addEventListener('change', (e) => {
                    console.log('Evento change en input de archivos de galería');
                    this.handleMassiveUpload(e);
                });
            } else {
                console.warn('No se encontró el elemento fileInput');
            }

            // Configurar input para captura de cámara
            if (this.cameraInput) {
                console.log('Configurando input para captura de cámara...');
                this.cameraInput.setAttribute('accept', 'image/*');
                this.cameraInput.setAttribute('capture', 'camera');
                this.cameraInput.addEventListener('change', (e) => {
                    console.log('Evento change en input de cámara');
                    this.handleCameraCapture(e);
                });
            } else {
                console.warn('No se encontró el elemento cameraInput');
            }
        },

        // ========== UTILIDADES Y HELPERS ==========
        delay(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        },

        resetUploadState() {
            this.uploadState = {
                isUploading: false,
                sessionId: null,
                currentFiles: [],
                uploadedCount: 0,
                failedCount: 0,
                totalCount: 0,
                failedFiles: [],
                startTime: null
            };
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

            if (file.size === 0) {
                console.warn(`Archivo rechazado (vacío): ${file.name}`);
                return false;
            }

            console.log(`Archivo validado correctamente: ${file.name}`);
            return true;
        },

        updateElement(id, value) {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value;
            }
        },

        truncateFileName(fileName, maxLength) {
            if (fileName.length <= maxLength) return fileName;
            
            const extension = fileName.split('.').pop();
            const nameWithoutExt = fileName.substring(0, fileName.lastIndexOf('.'));
            const truncatedName = nameWithoutExt.substring(0, maxLength - extension.length - 4) + '...';
            
            return `${truncatedName}.${extension}`;
        },

        formatFileSize(bytes) {
            if (bytes === 0) return '0 B';
            
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        },

        formatTime(seconds) {
            if (seconds < 60) {
                return `${Math.round(seconds)}s`;
            } else if (seconds < 3600) {
                const minutes = Math.floor(seconds / 60);
                const remainingSeconds = Math.round(seconds % 60);
                return `${minutes}m ${remainingSeconds}s`;
            } else {
                const hours = Math.floor(seconds / 3600);
                const minutes = Math.floor((seconds % 3600) / 60);
                return `${hours}h ${minutes}m`;
            }
        },

        isMobile() {
            return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
        },

        // ========== UI UTILITIES ==========
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

        showAuthError(title, message) {
            Swal.fire({
                icon: 'warning',
                title: title,
                text: message,
                confirmButtonText: 'Iniciar Sesión',
                allowOutsideClick: false
            }).then(() => {
                window.location.href = '/login';
            });
        },

        showErrorWithRetry(title, message, retryCallback = null) {
            const options = {
                icon: 'error',
                title: title,
                text: message,
                confirmButtonText: 'Aceptar'
            };

            if (retryCallback) {
                options.showCancelButton = true;
                options.cancelButtonText = 'Reintentar';
                options.confirmButtonColor = '#d33';
                options.cancelButtonColor = '#3085d6';
            }

            Swal.fire(options).then((result) => {
                if (result.dismiss === Swal.DismissReason.cancel && retryCallback) {
                    retryCallback();
                }
            });
        },

        // ========== INICIALIZACIÓN DE IMÁGENES ==========
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
                                
                                img.style.opacity = '0';
                                img.style.transition = 'opacity 0.3s ease';
                                
                                img.onload = () => {
                                    img.style.opacity = '1';
                                };
                            }
                            observer.unobserve(img);
                        }
                    });
                }, {
                    rootMargin: '50px'
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
        },

        // ========== LIMPIEZA Y RECURSOS ==========
        cleanup() {
            console.log('Ejecutando limpieza de recursos...');
            
            if (this.progressInterval) {
                clearInterval(this.progressInterval);
                this.progressInterval = null;
            }
            
            this.capturedPhotos.forEach(file => {
                if (file.url) {
                    URL.revokeObjectURL(file.url);
                }
            });
            
            this.uploadState.isUploading = false;
            this.cameraState.isCapturing = false;
            
            console.log('Limpieza completada');
        }
    };

    // Hacer la galería disponible globalmente
    window.gallery = gallery;
    
    console.log('🎉 Gallery.js Parte 1 cargada correctamente');
});
// sat/static/src/js/gallery.js - Parte 2 de 4: Sistema de Subida Paralela
// Este archivo debe cargarse después de la Parte 1

// Extender el objeto gallery con métodos de subida paralela
Object.assign(window.gallery, {

    // ========== SISTEMA DE SUBIDA PARALELA PRINCIPAL ==========
    async handleMassiveUpload(event) {
        console.log('Iniciando proceso de subida masiva inteligente');
        
        if (this.uploadState.isUploading) {
            this.showError('Subida en progreso', 'Espera a que termine la subida actual');
            return;
        }

        const files = Array.from(event.target.files);
        console.log(`Total de archivos seleccionados: ${files.length}`);
        
        if (!files.length) {
            console.log('No se seleccionaron archivos para subir');
            return;
        }

        // Validar archivos localmente primero
        const validationResult = this.validateFilesLocally(files);
        if (!validationResult.valid) {
            this.showValidationErrors(validationResult);
            return;
        }

        const validFiles = validationResult.validFiles;
        console.log(`Archivos válidos para subir: ${validFiles.length} de ${files.length}`);

        // Inicializar estado de subida
        this.resetUploadState();
        this.uploadState.isUploading = true;
        this.uploadState.currentFiles = validFiles;
        this.uploadState.totalCount = validFiles.length;
        this.uploadState.startTime = Date.now();

        try {
            // Paso 1: Validar en el servidor
            console.log('Validando subida en el servidor...');
            const validationResponse = await this.validateUploadOnServer(validFiles);
            
            if (!validationResponse.success) {
                this.handleValidationError(validationResponse);
                return;
            }

            this.uploadState.sessionId = validationResponse.session_id;
            console.log(`Sesión de subida iniciada: ${this.uploadState.sessionId}`);

            // Paso 2: Mostrar UI de progreso avanzado
            this.showAdvancedUploadProgress();

            // Paso 3: Subir archivos en paralelo controlado
            await this.uploadFilesInParallel(validFiles);

            // Paso 4: Completar sesión
            await this.completeUploadSession();

        } catch (error) {
            console.error('Error en subida masiva:', error);
            this.handleUploadError(error);
        } finally {
            this.uploadState.isUploading = false;
            event.target.value = '';
        }
    },

    // ========== VALIDACIÓN DE ARCHIVOS ==========
    validateFilesLocally(files) {
        const validFiles = [];
        const invalidFiles = [];
        const maxSize = 10 * 1024 * 1024; // 10MB
        const allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp'];

        files.forEach(file => {
            const errors = [];

            if (!file.type.startsWith('image/') || !allowedTypes.includes(file.type)) {
                errors.push('Tipo de archivo no permitido');
            }

            if (file.size > maxSize) {
                errors.push(`Excede ${maxSize / 1024 / 1024}MB`);
            }

            if (file.size === 0) {
                errors.push('Archivo vacío');
            }

            if (!file.name || file.name.trim() === '') {
                errors.push('Nombre de archivo inválido');
            }

            if (errors.length === 0) {
                validFiles.push(file);
            } else {
                invalidFiles.push({
                    file: file,
                    errors: errors
                });
            }
        });

        return {
            valid: invalidFiles.length === 0,
            validFiles: validFiles,
            invalidFiles: invalidFiles,
            totalSize: validFiles.reduce((sum, file) => sum + file.size, 0)
        };
    },

    showValidationErrors(validationResult) {
        const { invalidFiles, validFiles } = validationResult;
        
        let message = `Se encontraron ${invalidFiles.length} archivos con problemas:\n\n`;
        
        invalidFiles.slice(0, 5).forEach(item => {
            message += `• ${item.file.name}: ${item.errors.join(', ')}\n`;
        });
        
        if (invalidFiles.length > 5) {
            message += `... y ${invalidFiles.length - 5} más\n`;
        }
        
        if (validFiles.length > 0) {
            message += `\n${validFiles.length} archivos son válidos y pueden subirse.`;
        }

        Swal.fire({
            icon: 'warning',
            title: 'Archivos con problemas',
            text: message,
            confirmButtonText: 'Aceptar',
            width: '500px'
        });
    },

    async validateUploadOnServer(files) {
        const totalSize = files.reduce((sum, file) => sum + file.size, 0);
        
        try {
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

            if (!response.ok) {
                if (response.status === 401 || response.status === 403) {
                    throw new Error('Sesión expirada. Por favor, inicia sesión nuevamente.');
                }
                throw new Error(`Error del servidor: ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error('Error en validación del servidor:', error);
            throw error;
        }
    },

    handleValidationError(validationResponse) {
        const message = validationResponse.error || 'Error de validación desconocido';
        
        if (validationResponse.details) {
            console.error('Detalles de validación:', validationResponse.details);
        }
        
        this.showError('Error de Validación', message);
    },

    // ========== SUBIDA PARALELA CONTROLADA ==========
    async uploadFilesInParallel(files) {
        console.log(`Iniciando subida paralela de ${files.length} archivos`);
        
        const chunks = this.createFileChunks(files, this.uploadConfig.maxParallelUploads);
        
        for (let chunkIndex = 0; chunkIndex < chunks.length; chunkIndex++) {
            const chunk = chunks[chunkIndex];
            console.log(`Procesando chunk ${chunkIndex + 1}/${chunks.length} con ${chunk.length} archivos`);
            
            const uploadPromises = chunk.map(file => this.uploadSingleFileWithRetry(file));
            
            try {
                const results = await Promise.allSettled(uploadPromises);
                this.processChunkResults(results, chunk);
            } catch (error) {
                console.error(`Error en chunk ${chunkIndex + 1}:`, error);
            }
            
            this.updateAdvancedProgress();
            
            if (chunkIndex < chunks.length - 1) {
                await this.delay(200);
            }
        }
    },

    async uploadSingleFileWithRetry(file, attemptNumber = 1) {
        console.log(`Subiendo archivo: ${file.name} (intento ${attemptNumber})`);
        
        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch(`/gallery/upload/single/${this.uploadState.sessionId}`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                if (response.status === 401 || response.status === 403) {
                    throw new Error('Sesión expirada');
                }
                throw new Error(`Error HTTP: ${response.status}`);
            }

            const result = await response.json();
            
            if (result.success) {
                console.log(`Archivo subido exitosamente: ${file.name}`);
                this.uploadState.uploadedCount++;
                return { success: true, file: file, result: result };
            } else {
                throw new Error(result.error || 'Error desconocido');
            }

        } catch (error) {
            console.error(`Error subiendo ${file.name} (intento ${attemptNumber}):`, error);
            
            if (attemptNumber < this.uploadConfig.retryAttempts) {
                console.log(`Reintentando ${file.name} en ${this.uploadConfig.retryDelay}ms...`);
                await this.delay(this.uploadConfig.retryDelay * attemptNumber);
                return this.uploadSingleFileWithRetry(file, attemptNumber + 1);
            } else {
                console.error(`Archivo ${file.name} falló después de ${this.uploadConfig.retryAttempts} intentos`);
                this.uploadState.failedCount++;
                this.uploadState.failedFiles.push({
                    file: file,
                    error: error.message
                });
                return { success: false, file: file, error: error.message };
            }
        }
    },

    createFileChunks(files, chunkSize) {
        const chunks = [];
        for (let i = 0; i < files.length; i += chunkSize) {
            chunks.push(files.slice(i, i + chunkSize));
        }
        return chunks;
    },

    processChunkResults(results, files) {
        results.forEach((result, index) => {
            const file = files[index];
            if (result.status === 'fulfilled') {
                console.log(`Resultado para ${file.name}:`, result.value);
            } else {
                console.error(`Error procesando ${file.name}:`, result.reason);
                this.uploadState.failedCount++;
                this.uploadState.failedFiles.push({
                    file: file,
                    error: result.reason.message || 'Error desconocido'
                });
            }
        });
    },

    // ========== COMPLETAR SESIÓN Y MOSTRAR RESULTADOS ==========
    async completeUploadSession() {
        if (!this.uploadState.sessionId) return;

        try {
            const response = await fetch(`/gallery/upload/complete/${this.uploadState.sessionId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });

            if (response.ok) {
                const result = await response.json();
                console.log('Sesión completada:', result);
                this.showUploadSummary(result.summary);
            } else {
                console.warn('Error completando sesión, pero archivos pueden haberse subido');
                this.showUploadSummary();
            }
        } catch (error) {
            console.error('Error completando sesión:', error);
            this.showUploadSummary();
        }
    },

    showUploadSummary(summary = null) {
        const uploaded = summary?.uploaded || this.uploadState.uploadedCount;
        const failed = summary?.failed || this.uploadState.failedCount;
        const total = summary?.total_files || this.uploadState.totalCount;
        const duration = summary?.duration || (Date.now() - this.uploadState.startTime) / 1000;

        let message = `Subida completada en ${duration.toFixed(1)}s\n\n`;
        message += `✅ Exitosos: ${uploaded}/${total}\n`;
        
        if (failed > 0) {
            message += `❌ Fallidos: ${failed}\n\n`;
            message += 'Archivos fallidos:\n';
            this.uploadState.failedFiles.forEach(item => {
                message += `• ${item.file.name}: ${item.error}\n`;
            });
        }

        Swal.fire({
            icon: uploaded > 0 ? 'success' : 'error',
            title: uploaded === total ? 'Subida Exitosa' : 'Subida Parcial',
            text: message,
            confirmButtonText: 'Aceptar',
            footer: failed > 0 ? '<button id="retryFailedBtn" class="btn btn-warning btn-sm">Reintentar Fallidos</button>' : null
        }).then(() => {
            if (uploaded > 0) {
                setTimeout(() => window.location.reload(), 1000);
            }
        });

        if (failed > 0) {
            setTimeout(() => {
                const retryBtn = document.getElementById('retryFailedBtn');
                if (retryBtn) {
                    retryBtn.addEventListener('click', () => this.retryFailedFiles());
                }
            }, 100);
        }
    },

    async retryFailedFiles() {
        if (!this.uploadState.failedFiles.length) return;

        const failedFiles = this.uploadState.failedFiles.map(item => item.file);
        console.log(`Reintentando subida de ${failedFiles.length} archivos fallidos`);

        // Resetear contadores solo para archivos fallidos
        this.uploadState.failedFiles = [];
        this.uploadState.failedCount = 0;
        this.uploadState.currentFiles = failedFiles;
        this.uploadState.totalCount = failedFiles.length;

        try {
            this.showAdvancedUploadProgress();
            await this.uploadFilesInParallel(failedFiles);
            await this.completeUploadSession();
        } catch (error) {
            console.error('Error en reintento:', error);
            this.handleUploadError(error);
        }
    },

    handleUploadError(error) {
        console.error('Error en subida:', error);
        
        let title = 'Error en Subida';
        let message = error.message || 'Ocurrió un error durante la subida';
        
        if (error.message.includes('Sesión expirada') || error.message.includes('AUTH_REQUIRED')) {
            this.showAuthError('Sesión Expirada', message);
        } else if (error.message.includes('Network')) {
            this.showErrorWithRetry('Error de Conexión', 'Verifica tu conexión a internet', () => {
                // Reintentar toda la subida
                if (this.uploadState.currentFiles.length > 0) {
                    this.retryFailedFiles();
                }
            });
        } else {
            this.showError(title, message);
        }
    },

    // ========== SISTEMA DE SUBIDA ORIGINAL (FALLBACK) ==========
    async handleMassiveUploadOriginal(event) {
        console.log('Usando sistema de subida original (fallback)');
        const files = Array.from(event.target.files);
        console.log(`Total de archivos seleccionados: ${files.length}`);
        
        if (!files.length) return;

        const validFiles = files.filter(file => this.validateFile(file));
        console.log(`Archivos válidos: ${validFiles.length} de ${files.length}`);
        
        if (!validFiles.length) {
            this.showError('No hay archivos válidos', 'Por favor seleccione imágenes válidas');
            return;
        }

        this.showUploadProgress(validFiles.length);

        const batchSize = 3;
        const batches = [];
        for (let i = 0; i < validFiles.length; i += batchSize) {
            batches.push(validFiles.slice(i, i + batchSize));
        }

        await this.processBatches(batches, 0, validFiles.length);
    },

    async processBatches(batches, uploadedCount, totalFiles) {
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

        try {
            console.log(`Enviando lote al servidor: /gallery/upload/${this.reparacionId}`);
            const response = await fetch(`/gallery/upload/${this.reparacionId}`, {
                method: 'POST',
                body: formData
            });

            console.log(`Respuesta recibida del servidor: ${response.status} ${response.statusText}`);
            
            if (!response.ok) {
                if (response.status === 401 || response.status === 403) {
                    throw new Error('Sesión expirada. Por favor, inicia sesión nuevamente.');
                }
                throw new Error(`Error de servidor: ${response.status}`);
            }

            const data = await response.json();
            console.log('Respuesta procesada:', data);
            
            if (data.success) {
                const newUploadedCount = uploadedCount + (data.uploaded_count || currentBatch.length);
                const progress = (newUploadedCount / totalFiles) * 100;
                console.log(`Subida en progreso: ${newUploadedCount}/${totalFiles} (${progress.toFixed(1)}%)`);
                
                this.updateUploadProgress(progress, newUploadedCount, totalFiles);
                
                if (data.failed_count > 0 && data.failed_files) {
                    console.warn(`Archivos fallidos en este lote: ${data.failed_count}`, data.failed_files);
                }
                
                await this.processBatches(batches, newUploadedCount, totalFiles);
            } else {
                throw new Error(data.error || 'Error en la subida');
            }
        } catch (error) {
            console.error('Error en proceso de subida:', error);
            
            if (error.message.includes('Sesión expirada') || error.message.includes('AUTH_REQUIRED')) {
                this.showAuthError('Sesión Expirada', error.message);
            } else {
                this.showErrorWithRetry('Error en Subida', error.message || 'Ocurrió un error durante la subida');
            }
        }
    }
});

console.log('🎉 Gallery.js Parte 2 (Sistema de Subida Paralela) cargada correctamente');
// sat/static/src/js/gallery.js - Parte 3 de 4: Funcionalidad de Cámara y UI de Progreso
// Este archivo debe cargarse después de la Parte 2

// Extender el objeto gallery con funcionalidades de cámara y UI avanzado
Object.assign(window.gallery, {

    // ========== FUNCIONALIDAD DE CÁMARA ==========
    handleCameraButtonClick() {
        console.log('Botón de cámara presionado');
        
        if (this.capturedPhotos.length > 0) {
            this.showCameraOptions();
        } else {
            this.triggerCameraCapture();
        }
    },

    triggerCameraCapture() {
        console.log('Activando captura de cámara');
        
        if (this.cameraInput) {
            this.cameraState.isCapturing = true;
            this.cameraInput.click();
        } else {
            console.error('Input de cámara no disponible');
            this.showError('Error', 'Cámara no disponible en este dispositivo');
        }
    },

    async handleCameraCapture(event) {
        console.log('Procesando captura de cámara');
        
        const files = Array.from(event.target.files);
        if (!files.length) {
            console.log('No se capturaron archivos');
            this.cameraState.isCapturing = false;
            return;
        }

        for (const file of files) {
            if (this.validateFile(file)) {
                console.log(`Agregando foto capturada: ${file.name}`);
                
                // Comprimir imagen si está habilitado
                const processedFile = this.cameraState.compressionEnabled 
                    ? await this.compressImage(file) 
                    : file;
                
                this.capturedPhotos.push(processedFile);
            } else {
                console.warn(`Foto capturada no válida: ${file.name}`);
            }
        }

        this.cameraState.sessionActive = this.capturedPhotos.length > 0;
        this.updateCameraButton();
        
        // Limpiar input
        event.target.value = '';
        
        if (this.capturedPhotos.length > 0) {
            this.showCameraOptions();
        }

        this.cameraState.isCapturing = false;
    },

    async compressImage(file) {
        return new Promise((resolve) => {
            if (!this.cameraState.compressionEnabled) {
                resolve(file);
                return;
            }

            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            const img = new Image();

            img.onload = () => {
                // Calcular nuevas dimensiones manteniendo aspect ratio
                const maxWidth = 1920;
                const maxHeight = 1080;
                let { width, height } = img;

                if (width > maxWidth || height > maxHeight) {
                    const ratio = Math.min(maxWidth / width, maxHeight / height);
                    width *= ratio;
                    height *= ratio;
                }

                canvas.width = width;
                canvas.height = height;

                // Dibujar imagen redimensionada
                ctx.drawImage(img, 0, 0, width, height);

                // Convertir a blob con compresión
                canvas.toBlob((blob) => {
                    if (blob) {
                        const compressedFile = new File([blob], file.name, {
                            type: 'image/jpeg',
                            lastModified: Date.now()
                        });
                        console.log(`Imagen comprimida: ${file.size} -> ${compressedFile.size} bytes`);
                        resolve(compressedFile);
                    } else {
                        resolve(file);
                    }
                }, 'image/jpeg', this.cameraState.compressionQuality);
            };

            img.onerror = () => resolve(file);
            img.src = URL.createObjectURL(file);
        });
    },

    showCameraOptions() {
        const count = this.capturedPhotos.length;
        const totalSize = this.capturedPhotos.reduce((sum, file) => sum + file.size, 0);
        
        Swal.fire({
            title: `${count} Foto${count > 1 ? 's' : ''} Capturada${count > 1 ? 's' : ''}`,
            html: `
                <div class="camera-options">
                    <p>Tienes <strong>${count}</strong> foto${count > 1 ? 's' : ''} capturada${count > 1 ? 's' : ''} 
                    (${this.formatFileSize(totalSize)})</p>
                    <div class="btn-group-vertical w-100 mt-3">
                        <button class="btn btn-primary mb-2" id="takeMoreBtn">
                            <i class="fa fa-camera"></i> Tomar Más Fotos
                        </button>
                        <button class="btn btn-info mb-2" id="previewBtn">
                            <i class="fa fa-eye"></i> Ver Fotos
                        </button>
                        <button class="btn btn-success mb-2" id="uploadAllBtn">
                            <i class="fa fa-upload"></i> Subir Todas (${count})
                        </button>
                        <button class="btn btn-warning mb-2" id="clearSessionBtn">
                            <i class="fa fa-trash"></i> Eliminar Todas
                        </button>
                    </div>
                </div>
            `,
            showConfirmButton: false,
            showCancelButton: true,
            cancelButtonText: 'Cerrar',
            width: '400px',
            didOpen: () => {
                this.bindCameraOptionEvents();
            }
        });
    },

    bindCameraOptionEvents() {
        const takeMoreBtn = document.getElementById('takeMoreBtn');
        const previewBtn = document.getElementById('previewBtn');
        const uploadAllBtn = document.getElementById('uploadAllBtn');
        const clearSessionBtn = document.getElementById('clearSessionBtn');

        if (takeMoreBtn) {
            takeMoreBtn.addEventListener('click', () => {
                Swal.close();
                this.triggerCameraCapture();
            });
        }

        if (previewBtn) {
            previewBtn.addEventListener('click', () => {
                Swal.close();
                this.showPhotosPreview();
            });
        }

        if (uploadAllBtn) {
            uploadAllBtn.addEventListener('click', () => {
                Swal.close();
                this.uploadAllCapturedPhotos();
            });
        }

        if (clearSessionBtn) {
            clearSessionBtn.addEventListener('click', () => {
                this.clearCameraSession();
            });
        }
    },

    async showPhotosPreview() {
        console.log('Mostrando preview de fotos capturadas');
        
        Swal.fire({
            title: 'Vista Previa de Fotos',
            html: '<div id="photosCarousel">Cargando preview...</div>',
            width: '90%',
            showConfirmButton: false,
            showCancelButton: true,
            cancelButtonText: 'Cerrar',
            didOpen: async () => {
                await this.createPhotosCarousel();
            }
        });
    },

    async createPhotosCarousel() {
        const container = document.getElementById('photosCarousel');
        if (!container) return;

        let carouselHTML = `
            <div class="photos-carousel">
                <div class="carousel-controls mb-3">
                    <button class="btn btn-sm btn-outline-primary" id="prevPhoto">❮ Anterior</button>
                    <span class="photo-counter mx-3">1 / ${this.capturedPhotos.length}</span>
                    <button class="btn btn-sm btn-outline-primary" id="nextPhoto">Siguiente ❯</button>
                </div>
                <div class="carousel-container">
        `;

        for (let i = 0; i < this.capturedPhotos.length; i++) {
            const file = this.capturedPhotos[i];
            const imageUrl = URL.createObjectURL(file);
            
            carouselHTML += `
                <div class="carousel-slide ${i === 0 ? 'active' : ''}" data-slide="${i}">
                    <img src="${imageUrl}" alt="${file.name}" style="max-width: 100%; max-height: 400px; object-fit: contain;">
                    <div class="slide-info mt-2">
                        <strong>${file.name}</strong><br>
                        <small class="text-muted">${this.formatFileSize(file.size)}</small>
                        <br>
                        <button class="btn btn-sm btn-danger mt-2" onclick="gallery.removePhotoFromSession(${i})">
                            <i class="fa fa-trash"></i> Eliminar
                        </button>
                    </div>
                </div>
            `;
        }

        carouselHTML += `
                </div>
            </div>
        `;

        container.innerHTML = carouselHTML;
        this.initializeCarouselControls();
    },

    initializeCarouselControls() {
        let currentSlide = 0;
        const totalSlides = this.capturedPhotos.length;
        
        const updateSlide = () => {
            document.querySelectorAll('.carousel-slide').forEach((slide, index) => {
                slide.classList.toggle('active', index === currentSlide);
                slide.style.display = index === currentSlide ? 'block' : 'none';
            });
            
            const counter = document.querySelector('.photo-counter');
            if (counter) {
                counter.textContent = `${currentSlide + 1} / ${totalSlides}`;
            }
        };

        const prevBtn = document.getElementById('prevPhoto');
        const nextBtn = document.getElementById('nextPhoto');

        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                currentSlide = (currentSlide - 1 + totalSlides) % totalSlides;
                updateSlide();
            });
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                currentSlide = (currentSlide + 1) % totalSlides;
                updateSlide();
            });
        }

        updateSlide();
    },

    removePhotoFromSession(index) {
        if (index >= 0 && index < this.capturedPhotos.length) {
            const removedPhoto = this.capturedPhotos.splice(index, 1)[0];
            console.log(`Foto eliminada de la sesión: ${removedPhoto.name}`);
            
            // Limpiar URL object
            if (removedPhoto.url) {
                URL.revokeObjectURL(removedPhoto.url);
            }
            
            this.updateCameraButton();
            
            if (this.capturedPhotos.length === 0) {
                this.cameraState.sessionActive = false;
                Swal.close();
                this.showSuccess('Sesión Limpiada', 'Todas las fotos han sido eliminadas');
            } else {
                this.showCameraOptions();
            }
        }
    },

    clearCameraSession() {
        Swal.fire({
            title: '¿Eliminar todas las fotos?',
            text: 'Se perderán todas las fotos capturadas en esta sesión',
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#d33',
            cancelButtonColor: '#3085d6',
            confirmButtonText: 'Sí, eliminar todas',
            cancelButtonText: 'Cancelar'
        }).then((result) => {
            if (result.isConfirmed) {
                console.log('Limpiando sesión de cámara');
                
                // Limpiar URLs de objetos
                this.capturedPhotos.forEach(file => {
                    if (file.url) {
                        URL.revokeObjectURL(file.url);
                    }
                });
                
                this.capturedPhotos = [];
                this.cameraState.sessionActive = false;
                this.updateCameraButton();
                Swal.close();
                
                Swal.fire({
                    icon: 'success',
                    title: 'Sesión Limpiada',
                    text: 'Todas las fotos han sido eliminadas',
                    timer: 1500,
                    showConfirmButton: false
                });
            }
        });
    },

    async uploadAllCapturedPhotos() {
        console.log(`Subiendo ${this.capturedPhotos.length} fotos capturadas`);
        
        if (this.capturedPhotos.length === 0) {
            this.showError('Sin fotos', 'No hay fotos para subir');
            return;
        }

        const syntheticEvent = {
            target: {
                files: this.capturedPhotos,
                value: ''
            }
        };

        try {
            await this.handleMassiveUpload(syntheticEvent);
            
            // Limpiar sesión después de subida exitosa
            this.capturedPhotos.forEach(file => {
                if (file.url) {
                    URL.revokeObjectURL(file.url);
                }
            });
            
            this.capturedPhotos = [];
            this.cameraState.sessionActive = false;
            this.updateCameraButton();
            
        } catch (error) {
            console.error('Error en subida de fotos de cámara:', error);
        }
    },

    updateCameraButton() {
        if (!this.cameraBtn) return;
        
        const count = this.capturedPhotos.length;
        console.log(`Actualizando botón de cámara: ${count} fotos`);
        
        if (count === 0) {
            this.cameraBtn.innerHTML = '<i class="fa fa-camera"></i> Tomar Foto';
            this.cameraBtn.className = 'btn btn-primary';
            this.cameraBtn.title = 'Capturar nueva foto';
        } else {
            const totalSize = this.capturedPhotos.reduce((sum, file) => sum + file.size, 0);
            const formattedSize = this.formatFileSize(totalSize);
            
            this.cameraBtn.innerHTML = `<i class="fa fa-camera"></i> Cámara (${count})`;
            this.cameraBtn.className = 'btn btn-warning';
            this.cameraBtn.title = `${count} fotos capturadas (${formattedSize})`;
        }
    },

    // ========== UI DE PROGRESO AVANZADO ==========
    showAdvancedUploadProgress() {
        console.log('Mostrando UI de progreso avanzado');
        
        const totalFiles = this.uploadState.totalCount;
        
        Swal.fire({
            title: 'Subiendo Fotos',
            html: this.createAdvancedProgressHTML(totalFiles),
            allowOutsideClick: false,
            showConfirmButton: false,
            showCancelButton: true,
            cancelButtonText: 'Cancelar Subida',
            customClass: {
                popup: 'upload-progress-popup',
                htmlContainer: 'upload-progress-container'
            },
            didOpen: () => {
                this.injectProgressStyles();
                this.startProgressPolling();
                
                const cancelBtn = Swal.getCancelButton();
                if (cancelBtn) {
                    cancelBtn.addEventListener('click', () => this.cancelUpload());
                }
            }
        });
    },

    createAdvancedProgressHTML(totalFiles) {
        return `
            <div class="upload-progress-wrapper">
                <div class="general-progress mb-4">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <span class="progress-label">Progreso General</span>
                        <span class="progress-percentage">0%</span>
                    </div>
                    <div class="progress progress-main">
                        <div class="progress-bar progress-bar-striped progress-bar-animated" 
                             role="progressbar" style="width: 0%" 
                             aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                        </div>
                    </div>
                    <div class="progress-stats mt-2">
                        <small class="text-muted">
                            <span id="uploadedCount">0</span> exitosos • 
                            <span id="failedCount">0</span> fallidos • 
                            <span id="remainingCount">${totalFiles}</span> restantes
                        </small>
                    </div>
                </div>

                <div class="upload-metrics mb-3">
                    <div class="row text-center">
                        <div class="col-4">
                            <div class="metric-value" id="uploadSpeed">--</div>
                            <div class="metric-label">archivos/min</div>
                        </div>
                        <div class="col-4">
                            <div class="metric-value" id="timeRemaining">--</div>
                            <div class="metric-label">tiempo restante</div>
                        </div>
                        <div class="col-4">
                            <div class="metric-value" id="totalTime">0s</div>
                            <div class="metric-label">tiempo total</div>
                        </div>
                    </div>
                </div>

                <div class="files-progress">
                    <div class="files-header mb-2">
                        <strong>Estado de Archivos</strong>
                        <button class="btn btn-sm btn-outline-secondary float-right" id="toggleFileList">
                            <i class="fa fa-chevron-down"></i>
                        </button>
                    </div>
                    <div class="files-list" id="filesList" style="max-height: 200px; overflow-y: auto;">
                        ${this.createFileListHTML()}
                    </div>
                </div>

                <div class="current-status mt-3">
                    <div class="alert alert-info mb-0" id="currentStatus">
                        <i class="fa fa-info-circle"></i>
                        <span id="statusText">Preparando subida...</span>
                    </div>
                </div>
            </div>
        `;
    },

    createFileListHTML() {
        return this.uploadState.currentFiles.map((file, index) => `
            <div class="file-item" data-file-index="${index}">
                <div class="file-info">
                    <div class="file-name">${this.truncateFileName(file.name, 30)}</div>
                    <div class="file-size">${this.formatFileSize(file.size)}</div>
                </div>
                <div class="file-status">
                    <span class="status-badge status-pending">
                        <i class="fa fa-clock"></i> Pendiente
                    </span>
                </div>
            </div>
        `).join('');
    },

    updateAdvancedProgress() {
        const uploaded = this.uploadState.uploadedCount;
        const failed = this.uploadState.failedCount;
        const total = this.uploadState.totalCount;
        const completed = uploaded + failed;
        const remaining = total - completed;
        const percentage = total > 0 ? (completed / total) * 100 : 0;

        const progressBar = document.querySelector('.progress-main .progress-bar');
        const progressPercentage = document.querySelector('.progress-percentage');
        
        if (progressBar && progressPercentage) {
            progressBar.style.width = `${percentage}%`;
            progressBar.setAttribute('aria-valuenow', percentage);
            progressPercentage.textContent = `${Math.round(percentage)}%`;
        }

        this.updateElement('uploadedCount', uploaded);
        this.updateElement('failedCount', failed);
        this.updateElement('remainingCount', remaining);
        this.updateUploadMetrics();
        this.updateCurrentStatus(uploaded, failed, remaining);

        console.log(`Progreso actualizado: ${completed}/${total} (${percentage.toFixed(1)}%)`);
    },

    updateUploadMetrics() {
        if (!this.uploadState.startTime) return;

        const elapsedSeconds = (Date.now() - this.uploadState.startTime) / 1000;
        const completed = this.uploadState.uploadedCount + this.uploadState.failedCount;
        const remaining = this.uploadState.totalCount - completed;

        const speed = completed > 0 ? (completed / elapsedSeconds) * 60 : 0;
        this.updateElement('uploadSpeed', speed > 0 ? speed.toFixed(1) : '--');

        const timeRemaining = speed > 0 && remaining > 0 ? (remaining / speed) * 60 : 0;
        this.updateElement('timeRemaining', timeRemaining > 0 ? this.formatTime(timeRemaining) : '--');

        this.updateElement('totalTime', this.formatTime(elapsedSeconds));
    },

    updateCurrentStatus(uploaded, failed, remaining) {
        const statusEl = document.getElementById('currentStatus');
        const statusTextEl = document.getElementById('statusText');
        
        if (!statusEl || !statusTextEl) return;

        let message, alertClass, icon;

        if (remaining > 0) {
            message = `Subiendo archivos... ${uploaded} completados`;
            alertClass = 'alert-info';
            icon = 'fa-upload';
        } else if (failed === 0) {
            message = `¡Subida completada! Todos los ${uploaded} archivos subidos exitosamente`;
            alertClass = 'alert-success';
            icon = 'fa-check-circle';
        } else if (uploaded === 0) {
            message = `Error: No se pudo subir ningún archivo (${failed} fallidos)`;
            alertClass = 'alert-danger';
            icon = 'fa-exclamation-circle';
        } else {
            message = `Subida parcial: ${uploaded} exitosos, ${failed} fallidos`;
            alertClass = 'alert-warning';
            icon = 'fa-exclamation-triangle';
        }

        statusEl.className = `alert mb-0 ${alertClass}`;
        statusTextEl.innerHTML = `<i class="fa ${icon}"></i> ${message}`;
    },

    startProgressPolling() {
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
        }
        
        this.progressInterval = setInterval(() => {
            this.updateAdvancedProgress();
        }, 500);
    },

    cancelUpload() {
        Swal.fire({
            title: '¿Cancelar subida?',
            text: 'Los archivos ya subidos se mantendrán',
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#d33',
            cancelButtonColor: '#3085d6',
            confirmButtonText: 'Sí, cancelar',
            cancelButtonText: 'Continuar subida'
        }).then((result) => {
            if (result.isConfirmed) {
                this.uploadState.isUploading = false;
                if (this.progressInterval) {
                    clearInterval(this.progressInterval);
                }
                Swal.close();
                this.showSuccess('Subida Cancelada', 'La subida ha sido cancelada');
            }
        });
    },

    // ========== PROGRESO SIMPLE (FALLBACK) ==========
    showUploadProgress(totalFiles) {
        console.log(`Mostrando UI de progreso para ${totalFiles} archivos`);
        
        if (typeof this.showAdvancedUploadProgress === 'function') {
            this.uploadState.totalCount = totalFiles;
            this.showAdvancedUploadProgress();
            return;
        }
        
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
        
        if (typeof this.updateAdvancedProgress === 'function') {
            this.uploadState.uploadedCount = uploadedCount;
            this.uploadState.totalCount = totalFiles;
            this.updateAdvancedProgress();
            return;
        }
        
        const progressBar = document.querySelector('.progress-bar');
        const statusText = document.getElementById('uploadStatus');
        
        if (progressBar && statusText) {
            progressBar.style.width = `${progress}%`;
            progressBar.setAttribute('aria-valuenow', progress);
            statusText.textContent = `Subiendo: ${uploadedCount} de ${totalFiles} fotos`;
        } else {
            console.warn('No se encontraron elementos de UI para actualizar el progreso');
        }
    }
});

console.log('🎉 Gallery.js Parte 3 (Cámara y UI de Progreso) cargada correctamente');
// sat/static/src/js/gallery.js - Parte 4 de 4: Estilos CSS, Eventos y Finalización
// Este archivo debe cargarse después de la Parte 3

// Extender el objeto gallery con estilos, eventos y funciones finales
Object.assign(window.gallery, {

    // ========== INYECCIÓN DE ESTILOS CSS ==========
    injectProgressStyles() {
        if (document.getElementById('uploadProgressStyles')) return;

        const styles = document.createElement('style');
        styles.id = 'uploadProgressStyles';
        styles.textContent = `
            /* Estilos para popup de progreso */
            .upload-progress-popup {
                width: 90% !important;
                max-width: 600px !important;
            }
            
            .upload-progress-container {
                text-align: left !important;
            }
            
            .upload-progress-wrapper {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }
            
            /* Barra de progreso principal */
            .progress-main {
                height: 12px;
                background-color: #e9ecef;
                border-radius: 6px;
                overflow: hidden;
                box-shadow: inset 0 1px 3px rgba(0,0,0,0.1);
            }
            
            .progress-main .progress-bar {
                background: linear-gradient(45deg, #28a745, #20c997);
                transition: width 0.4s ease;
                position: relative;
            }
            
            .progress-main .progress-bar::after {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                bottom: 0;
                right: 0;
                background-image: linear-gradient(
                    45deg,
                    rgba(255,255,255,.15) 25%,
                    transparent 25%,
                    transparent 50%,
                    rgba(255,255,255,.15) 50%,
                    rgba(255,255,255,.15) 75%,
                    transparent 75%,
                    transparent
                );
                background-size: 1rem 1rem;
                animation: progress-bar-stripes 1s linear infinite;
            }
            
            @keyframes progress-bar-stripes {
                0% { background-position: 1rem 0; }
                100% { background-position: 0 0; }
            }
            
            /* Labels y texto */
            .progress-label {
                font-weight: 600;
                color: #495057;
                font-size: 0.95em;
            }
            
            .progress-percentage {
                font-weight: 700;
                color: #28a745;
                font-size: 1.1em;
            }
            
            .progress-stats {
                font-size: 0.85em;
                color: #6c757d;
            }
            
            /* Métricas de subida */
            .upload-metrics {
                background: #f8f9fa;
                border-radius: 8px;
                padding: 15px;
                border: 1px solid #dee2e6;
            }
            
            .upload-metrics .metric-value {
                font-size: 1.4em;
                font-weight: 700;
                color: #007bff;
                line-height: 1.2;
            }
            
            .upload-metrics .metric-label {
                font-size: 0.75em;
                color: #6c757d;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-top: 2px;
            }
            
            /* Lista de archivos */
            .files-progress {
                background: white;
                border-radius: 8px;
                border: 1px solid #dee2e6;
            }
            
            .files-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 12px 15px;
                background: #f8f9fa;
                border-bottom: 1px solid #dee2e6;
                border-radius: 8px 8px 0 0;
                font-weight: 600;
                color: #495057;
            }
            
            #toggleFileList {
                border: none;
                background: none;
                padding: 4px 8px;
                color: #6c757d;
                border-radius: 4px;
                transition: all 0.2s;
            }
            
            #toggleFileList:hover {
                background: #dee2e6;
                color: #495057;
            }
            
            .files-list {
                max-height: 200px;
                overflow-y: auto;
                border-radius: 0 0 8px 8px;
            }
            
            .files-list::-webkit-scrollbar {
                width: 6px;
            }
            
            .files-list::-webkit-scrollbar-track {
                background: #f1f1f1;
            }
            
            .files-list::-webkit-scrollbar-thumb {
                background: #c1c1c1;
                border-radius: 3px;
            }
            
            .files-list::-webkit-scrollbar-thumb:hover {
                background: #a8a8a8;
            }
            
            /* Items de archivo */
            .file-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 12px 15px;
                border-bottom: 1px solid #f1f3f4;
                transition: background-color 0.2s;
            }
            
            .file-item:last-child {
                border-bottom: none;
            }
            
            .file-item:hover {
                background-color: #f8f9fa;
            }
            
            .file-info {
                flex: 1;
                min-width: 0;
                margin-right: 15px;
            }
            
            .file-name {
                font-weight: 500;
                color: #333;
                font-size: 0.9em;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                margin-bottom: 2px;
            }
            
            .file-size {
                font-size: 0.75em;
                color: #6c757d;
            }
            
            /* Badges de estado */
            .status-badge {
                padding: 4px 10px;
                border-radius: 12px;
                font-size: 0.7em;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.3px;
                white-space: nowrap;
                display: inline-flex;
                align-items: center;
                gap: 4px;
            }
            
            .status-pending {
                background-color: #fff3cd;
                color: #856404;
                border: 1px solid #ffeaa7;
            }
            
            .status-uploading {
                background-color: #cce5ff;
                color: #004085;
                border: 1px solid #99d6ff;
                animation: pulse 1.5s infinite;
            }
            
            .status-success {
                background-color: #d4edda;
                color: #155724;
                border: 1px solid #a3d9a5;
            }
            
            .status-error {
                background-color: #f8d7da;
                color: #721c24;
                border: 1px solid #f1a5a8;
            }
            
            .status-retrying {
                background-color: #fff3cd;
                color: #856404;
                border: 1px solid #ffeaa7;
                animation: pulse 1s infinite;
            }
            
            @keyframes pulse {
                0% { opacity: 1; }
                50% { opacity: 0.7; }
                100% { opacity: 1; }
            }
            
            /* Estado actual */
            .current-status .alert {
                border-radius: 8px;
                border: none;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                padding: 12px 15px;
                margin: 0;
                font-size: 0.9em;
            }
            
            .current-status .alert i {
                margin-right: 8px;
                font-size: 1.1em;
            }
            
            /* Estilos para carrusel de fotos */
            .photos-carousel {
                text-align: center;
            }
            
            .carousel-controls {
                display: flex;
                justify-content: center;
                align-items: center;
                gap: 15px;
                margin-bottom: 20px;
            }
            
            .carousel-controls button {
                min-width: 80px;
                font-size: 0.9em;
            }
            
            .photo-counter {
                font-weight: 600;
                color: #495057;
                background: #f8f9fa;
                padding: 5px 12px;
                border-radius: 15px;
                border: 1px solid #dee2e6;
            }
            
            .carousel-container {
                position: relative;
                background: #f8f9fa;
                border-radius: 8px;
                padding: 20px;
                border: 1px solid #dee2e6;
            }
            
            .carousel-slide {
                display: none;
                animation: fadeIn 0.3s ease;
            }
            
            .carousel-slide.active {
                display: block;
            }
            
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            
            .carousel-slide img {
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                max-width: 100%;
                max-height: 400px;
                object-fit: contain;
            }
            
            .slide-info {
                margin-top: 15px;
                padding: 10px;
                background: white;
                border-radius: 6px;
                border: 1px solid #dee2e6;
            }
            
            /* Estilos para opciones de cámara */
            .camera-options {
                text-align: center;
            }
            
            .camera-options p {
                font-size: 1.1em;
                color: #495057;
                margin-bottom: 20px;
            }
            
            .btn-group-vertical .btn {
                border-radius: 6px !important;
                margin-bottom: 8px;
                font-weight: 500;
                padding: 10px 20px;
                border: 1px solid transparent;
                transition: all 0.2s;
            }
            
            .btn-group-vertical .btn:hover {
                transform: translateY(-1px);
                box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            }
            
            .btn-group-vertical .btn i {
                margin-right: 8px;
            }
            
            /* Responsive */
            @media (max-width: 576px) {
                .upload-progress-popup {
                    width: 95% !important;
                    margin: 10px !important;
                }
                
                .upload-metrics .row {
                    text-align: center !important;
                }
                
                .upload-metrics .col-4 {
                    margin-bottom: 15px;
                }
                
                .carousel-controls {
                    flex-direction: column;
                    gap: 10px;
                }
                
                .carousel-controls button {
                    width: 100%;
                    max-width: 200px;
                }
                
                .file-item {
                    flex-direction: column;
                    align-items: flex-start;
                    gap: 8px;
                }
                
                .file-info {
                    margin-right: 0;
                    width: 100%;
                }
                
                .status-badge {
                    align-self: flex-end;
                }
            }
        `;
        
        document.head.appendChild(styles);
        console.log('Estilos CSS de progreso inyectados');
    },

    // ========== EVENTOS Y BINDING ==========
    bindEvents() {
        console.log('Iniciando bindEvents...');
        
        // Eventos de inputs de archivo
        if (this.fileInput) {
            console.log('Vinculando evento change para subida de archivos de galería');
            this.fileInput.addEventListener('change', (e) => this.handleMassiveUpload(e));
        }

        if (this.cameraInput) {
            console.log('Vinculando evento change para captura de cámara');
            this.cameraInput.addEventListener('change', (e) => this.handleCameraCapture(e));
        }

        // Buscar y vincular botón de cámara
        this.findAndBindCameraButton();
        
        // Otros botones
        if (this.syncButton) {
            console.log('Vinculando evento para botón de sincronización');
            this.syncButton.addEventListener('click', () => this.handleSync());
        }
        
        if (this.shareGalleryBtn) {
            console.log('Vinculando evento para botón de compartir');
            this.shareGalleryBtn.addEventListener('click', () => this.handleShareGallery());
        }
        
        // Eventos dinámicos
        this.bindDynamicEvents();
        
        console.log('Eventos vinculados correctamente');
    },

    findAndBindCameraButton() {
        const selectors = [
            '#cameraBtn',
            'button[id*="camera"]',
            '.btn-camera',
            'button[data-action="camera"]'
        ];

        for (const selector of selectors) {
            try {
                const button = document.querySelector(selector);
                if (button && !button.hasAttribute('data-camera-bound')) {
                    console.log(`Botón de cámara encontrado con selector: ${selector}`);
                    this.cameraBtn = button;
                    this.cameraBtn.addEventListener('click', () => this.handleCameraButtonClick());
                    this.cameraBtn.setAttribute('data-camera-bound', 'true');
                    return;
                }
            } catch (e) {
                // Ignorar errores de selectores inválidos
            }
        }

        console.warn('No se pudo encontrar botón de cámara por ningún método');
    },

    bindDynamicEvents() {
        if (window.MutationObserver) {
            const observer = new MutationObserver((mutations) => {
                mutations.forEach((mutation) => {
                    mutation.addedNodes.forEach((node) => {
                        if (node.nodeType === 1) {
                            this.bindButtonEvents(node);
                        }
                    });
                });
            });

            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        }

        this.bindButtonEvents(document);
    },

    bindButtonEvents(container) {
        // Botones de descarga
        container.querySelectorAll('.download-photo:not([data-bound])').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleDownload(e));
            btn.setAttribute('data-bound', 'true');
            console.log('Evento de descarga vinculado para foto ID:', btn.dataset.photoId || 'sin ID');
        });

        // Botones de eliminación
        container.querySelectorAll('.delete-photo:not([data-bound])').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleDelete(e));
            btn.setAttribute('data-bound', 'true');
            console.log('Evento de eliminación vinculado para foto ID:', btn.dataset.photoId || 'sin ID');
        });
    },

    // ========== FUNCIONES DE DESCARGA ==========
    handleDownload(event) {
        event.preventDefault();
        const button = event.currentTarget;
        const photoId = button.dataset.photoId;
        console.log(`Solicitando descarga para la foto con ID: ${photoId}`);
        
        if (!photoId) {
            this.showError('Error', 'ID de foto no encontrado');
            return;
        }
        
        button.disabled = true;
        const originalText = button.innerHTML;
        button.innerHTML = '<i class="fa fa-spinner fa-spin"></i>';

        fetch(`/gallery/download/${photoId}`)
            .then(response => {
                if (!response.ok) {
                    if (response.status === 401 || response.status === 403) {
                        throw new Error('Sesión expirada. Inicia sesión nuevamente.');
                    }
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
                
                const filename = button.getAttribute('data-filename') || `foto_${photoId}.jpg`;
                console.log(`Descargando como: ${filename}`);
                link.setAttribute('download', filename);
                
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                
                window.URL.revokeObjectURL(url);
                console.log('Archivo descargado exitosamente');
                
                button.innerHTML = '<i class="fa fa-check"></i>';
                setTimeout(() => {
                    button.innerHTML = originalText;
                }, 1000);
            })
            .catch(error => {
                console.error('Error al descargar la foto:', error);
                
                if (error.message.includes('Sesión expirada')) {
                    this.showAuthError('Sesión Expirada', error.message);
                } else {
                    this.showError('Error', 'No se pudo descargar la foto. Inténtalo de nuevo.');
                }
            })
            .finally(() => {
                button.disabled = false;
                if (button.innerHTML.includes('fa-spinner')) {
                    button.innerHTML = originalText;
                }
            });
    },

    // ========== FUNCIONES DE ELIMINACIÓN ==========
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
                if (response.status === 401 || response.status === 403) {
                    throw new Error('Sesión expirada. Inicia sesión nuevamente.');
                }
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
                    element.style.transition = 'opacity 0.3s ease';
                    element.style.opacity = '0';
                    setTimeout(() => {
                        element.remove();
                        console.log('Foto eliminada correctamente:', photoId);
                    }, 300);
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
            
            if (error.message.includes('Sesión expirada')) {
                this.showAuthError('Sesión Expirada', error.message);
            } else {
                this.showError('Error', error.message || 'No se pudo eliminar la foto');
            }
        })
        .finally(() => {
            console.log('Finalizando operación de eliminación');
            this.hideLoading();
        });
    },

    // ========== FUNCIONES DE SINCRONIZACIÓN ==========
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
                if (response.status === 401 || response.status === 403) {
                    throw new Error('Sesión expirada. Inicia sesión nuevamente.');
                }
                throw new Error(`Error de servidor: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Respuesta procesada:', data);
            if (data.success) {
                console.log('Sincronización completada');
                this.showSuccess('Sincronización completada', data.message || 'Fotos sincronizadas correctamente');
                setTimeout(() => window.location.reload(), 1500);
            } else {
                console.error(`Error reportado por el servidor: ${data.error || 'Error desconocido'}`);
                throw new Error(data.error || 'Error al sincronizar');
            }
        })
        .catch(error => {
            console.error('Error en sincronización:', error);
            
            if (error.message.includes('Sesión expirada')) {
                this.showAuthError('Sesión Expirada', error.message);
            } else {
                this.showError('Error', error.message || 'Ocurrió un error durante la sincronización');
            }
        })
        .finally(() => {
            console.log('Finalizando operación de sincronización');
            this.hideLoading();
        });
    },

    // ========== FUNCIONES DE COMPARTIR ==========
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
    }
});

// ========== EVENT LISTENERS GLOBALES ==========
window.addEventListener('beforeunload', () => {
    if (window.gallery && typeof window.gallery.cleanup === 'function') {
        window.gallery.cleanup();
    }
});

document.addEventListener('visibilitychange', () => {
    if (document.hidden && window.gallery) {
        console.log('Página oculta, pausando operaciones de cámara');
        if (window.gallery.cameraState) {
            window.gallery.cameraState.isCapturing = false;
        }
    }
});

window.addEventListener('orientationchange', () => {
    if (window.gallery && window.gallery.isMobile()) {
        console.log('Cambio de orientación detectado');
        setTimeout(() => {
            if (window.gallery.cameraState && window.gallery.cameraState.sessionActive) {
                console.log('Reajustando UI para nueva orientación');
            }
        }, 500);
    }
});

// Manejar errores globales de JavaScript
window.addEventListener('error', (event) => {
    if (event.filename.includes('gallery.js')) {
        console.error('Error en Gallery.js:', event.error);
    }
});

// Detectar cuando se pierde la conexión
window.addEventListener('offline', () => {
    if (window.gallery && window.gallery.uploadState.isUploading) {
        console.warn('Conexión perdida durante subida');
        Swal.fire({
            icon: 'warning',
            title: 'Conexión Perdida',
            text: 'Se ha perdido la conexión. La subida se pausará automáticamente.',
            toast: true,
            position: 'top-end',
            timer: 3000,
            showConfirmButton: false
        });
    }
});

// Detectar cuando se recupera la conexión
window.addEventListener('online', () => {
    console.log('Conexión recuperada');
    Swal.fire({
        icon: 'success',
        title: 'Conexión Recuperada',
        text: 'La conexión a internet se ha restablecido.',
        toast: true,
        position: 'top-end',
        timer: 2000,
        showConfirmButton: false
    });
});

// ========== INICIALIZACIÓN FINAL ==========
// Inicializar galería cuando el DOM esté listo
if (window.gallery) {
    console.log('Inicializando galería desde Parte 4...');
    window.gallery.init();
    console.log('🎉 Gallery.js Parte 4 (Final) completamente cargado e inicializado');
} else {
    console.error('❌ window.gallery no está disponible. Asegúrate de cargar las partes anteriores primero.');
}

// Verificar que todas las partes estén cargadas
const requiredMethods = [
    'init', 'handleMassiveUpload', 'handleCameraCapture', 'showAdvancedUploadProgress',
    'validateFilesLocally', 'uploadFilesInParallel', 'bindEvents', 'cleanup'
];

const missingMethods = requiredMethods.filter(method => 
    !window.gallery || typeof window.gallery[method] !== 'function'
);

if (missingMethods.length > 0) {
    console.error('❌ Métodos faltantes en gallery:', missingMethods);
    console.error('Asegúrate de cargar todas las partes del archivo en orden: 1, 2, 3, 4');
} else {
    console.log('✅ Todas las funcionalidades de gallery están disponibles');
}

// ========== FUNCIÓN DE DIAGNÓSTICO ==========
window.gallery.diagnose = function() {
    console.log('=== DIAGNÓSTICO DE GALLERY ===');
    console.log('Elementos DOM encontrados:');
    console.log('- fileInput:', this.fileInput ? '✅' : '❌');
    console.log('- cameraInput:', this.cameraInput ? '✅' : '❌');
    console.log('- photoGrid:', this.photoGrid ? '✅' : '❌');
    console.log('- syncButton:', this.syncButton ? '✅' : '❌');
    console.log('- shareGalleryBtn:', this.shareGalleryBtn ? '✅' : '❌');
    console.log('- cameraBtn:', this.cameraBtn ? '✅' : '❌');
    console.log('- reparacionId:', this.reparacionId || 'No encontrado');
    
    console.log('\nEstado actual:');
    console.log('- Fotos capturadas:', this.capturedPhotos.length);
    console.log('- Subida en progreso:', this.uploadState.isUploading);
    console.log('- Sesión de cámara activa:', this.cameraState.sessionActive);
    
    console.log('\nFuncionalidades disponibles:');
    const methods = [
        'init', 'handleMassiveUpload', 'handleCameraCapture', 'showAdvancedUploadProgress',
        'validateFilesLocally', 'uploadFilesInParallel', 'bindEvents', 'cleanup',
        'handleDownload', 'handleDelete', 'handleSync', 'handleShareGallery'
    ];
    
    methods.forEach(method => {
        console.log(`- ${method}:`, typeof this[method] === 'function' ? '✅' : '❌');
    });
    
    console.log('=== FIN DIAGNÓSTICO ===');
};

// ========== UTILIDADES DE DESARROLLO ==========
if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    console.log('🔧 Modo desarrollo detectado - Utilidades adicionales disponibles');
    
    // Función para simular subida de archivos (testing)
    window.gallery.simulateUpload = function(fileCount = 5) {
        console.log(`Simulando subida de ${fileCount} archivos...`);
        
        const mockFiles = [];
        for (let i = 0; i < fileCount; i++) {
            const mockFile = new File(
                [new Blob(['test data'], { type: 'image/jpeg' })],
                `test-image-${i + 1}.jpg`,
                { type: 'image/jpeg' }
            );
            mockFiles.push(mockFile);
        }
        
        const mockEvent = {
            target: {
                files: mockFiles,
                value: ''
            }
        };
        
        this.handleMassiveUpload(mockEvent);
    };
    
    // Función para limpiar todo (testing)
    window.gallery.reset = function() {
        console.log('🔄 Reseteando gallery...');
        this.cleanup();
        this.capturedPhotos = [];
        this.resetUploadState();
        this.initializeCameraSession();
        console.log('✅ Gallery reseteado');
    };
    
    // Función para mostrar estado detallado
    window.gallery.status = function() {
        return {
            elements: {
                fileInput: !!this.fileInput,
                cameraInput: !!this.cameraInput,
                photoGrid: !!this.photoGrid,
                syncButton: !!this.syncButton,
                shareGalleryBtn: !!this.shareGalleryBtn,
                cameraBtn: !!this.cameraBtn
            },
            state: {
                capturedPhotos: this.capturedPhotos.length,
                isUploading: this.uploadState.isUploading,
                sessionActive: this.cameraState.sessionActive,
                reparacionId: this.reparacionId
            },
            config: {
                maxParallelUploads: this.uploadConfig.maxParallelUploads,
                retryAttempts: this.uploadConfig.retryAttempts,
                compressionEnabled: this.cameraState.compressionEnabled
            }
        };
    };
}

// ========== COMPATIBILIDAD CON VERSIONES ANTERIORES ==========
// Alias para métodos que pueden haber cambiado de nombre
window.gallery.massiveUpload = window.gallery.handleMassiveUpload;
window.gallery.cameraCapture = window.gallery.handleCameraCapture;
window.gallery.shareGallery = window.gallery.handleShareGallery;

// ========== EXPOSICIÓN DE API PÚBLICA ==========
// Hacer disponibles solo los métodos públicos necesarios
window.GalleryAPI = {
    // Métodos principales
    uploadFiles: (files) => {
        const event = { target: { files: files, value: '' } };
        return window.gallery.handleMassiveUpload(event);
    },
    
    capturePhoto: () => {
        return window.gallery.triggerCameraCapture();
    },
    
    shareGallery: () => {
        return window.gallery.handleShareGallery();
    },
    
    syncWithCloud: () => {
        return window.gallery.handleSync();
    },
    
    // Información de estado
    getStatus: () => {
        return {
            isUploading: window.gallery.uploadState.isUploading,
            capturedPhotos: window.gallery.capturedPhotos.length,
            sessionActive: window.gallery.cameraState.sessionActive
        };
    },
    
    // Utilidades
    cleanup: () => {
        return window.gallery.cleanup();
    },
    
    diagnose: () => {
        return window.gallery.diagnose();
    }
};

// ========== MENSAJE FINAL ==========
console.log('🎉 GALLERY.JS COMPLETAMENTE CARGADO 🎉');
console.log('📱 Funcionalidades disponibles:');
console.log('  • Subida masiva paralela con reintentos');
console.log('  • Captura de cámara con compresión');
console.log('  • UI de progreso avanzado en tiempo real');
console.log('  • Validación local y del servidor');
console.log('  • Gestión de sesiones de subida');
console.log('  • Descarga y eliminación de fotos');
console.log('  • Sincronización con pCloud');
console.log('  • Compartir galería');
console.log('  • Responsive y mobile-friendly');
console.log('');
console.log('🔧 API pública disponible en: window.GalleryAPI');
console.log('🔍 Para diagnóstico: gallery.diagnose()');
console.log('📊 Para estado: gallery.status() (solo en desarrollo)');
console.log('');
console.log('✅ Listo para usar!');