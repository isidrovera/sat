// sat/static/src/js/gallery.js
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM Cargado. Iniciando script de galería...');
    
    const gallery = {
        init() {
            console.log('Iniciando galería...');
            this.initializeElements();
            this.bindEvents();
            this.initializeImagePreviews();
            
            // Configurar el visor de imágenes
            this.setupPhotoCardClicks();
            console.log('Inicialización completa de galería');
        },

        initializeElements() {
            console.log('Inicializando elementos DOM...');
            this.fileInput = document.getElementById('fileUpload');
            this.photoGrid = document.querySelector('#photoGrid');
            this.syncButton = document.getElementById('syncButton');
            this.shareGalleryBtn = document.getElementById('shareGalleryBtn');
            this.loadingOverlay = document.getElementById('loadingOverlay');
            this.reparacionId = window.location.pathname.split('/').pop();
            
            console.log('Elementos inicializados:', {
                fileInput: this.fileInput ? 'Encontrado' : 'No encontrado',
                photoGrid: this.photoGrid ? 'Encontrado' : 'No encontrado',
                syncButton: this.syncButton ? 'Encontrado' : 'No encontrado',
                shareGalleryBtn: this.shareGalleryBtn ? 'Encontrado' : 'No encontrado',
                loadingOverlay: this.loadingOverlay ? 'Encontrado' : 'No encontrado',
                reparacionId: this.reparacionId,
            });
            
            this.setupFileInput();
        },

        setupFileInput() {
            if (this.fileInput) {
                console.log('Configurando input para múltiples fotos...');
                this.fileInput.setAttribute('multiple', 'multiple');
                this.fileInput.setAttribute('accept', 'image/*');

                if (this.isMobile()) {
                    console.log('Configuración específica para dispositivos móviles');
                    this.fileInput.addEventListener('click', function() {
                        this.setAttribute('multiple', 'multiple');
                    });
                    this.fileInput.addEventListener('change', (e) => {
                        console.log('Evento change en input de archivos (móvil)');
                        this.handleMassiveUpload(e);
                    });
                }
            } else {
                console.warn('No se encontró el elemento fileInput');
            }
        },

        isMobile() {
            const isMobileDevice = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
            console.log('Detección de dispositivo móvil:', isMobileDevice);
            return isMobileDevice;
        },

        bindEvents() {
            console.log('Iniciando bindEvents...');
            
            // Inicializar variables para el visor de imágenes
            this.slideshowEventsInitialized = false;
            this.viewerPhotos = [];
            this.viewerCurrentIndex = 0;
            
            if (this.fileInput && !this.isMobile()) {
                console.log('Vinculando evento change para subida de archivos (escritorio)');
                this.fileInput.addEventListener('change', (e) => this.handleMassiveUpload(e));
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
        
        setupPhotoCardClicks() {
            console.log('Configurando clics en tarjetas de fotos para el visor de imágenes');
            const cards = document.querySelectorAll('.photo-card');
            console.log(`Encontradas ${cards.length} tarjetas de fotos para configurar eventos de clic`);
            
            cards.forEach(card => {
                // Asignar un identificador único a la tarjeta si no tiene ya un data-photo-id
                if (!card.dataset.photoId) {
                    console.warn('Tarjeta sin ID encontrada, generando ID aleatorio');
                    card.dataset.photoId = 'photo-' + Math.random().toString(36).substr(2, 9);
                }
                
                // Asignar evento directamente a la tarjeta (no a la imagen)
                card.addEventListener('click', (e) => {
                    // Verificar si el clic fue en un botón o enlace
                    const isActionClick = e.target.tagName === 'BUTTON' || e.target.tagName === 'A' || 
                                         e.target.closest('button') || e.target.closest('a') || 
                                         e.target.closest('.actions-bar');
                                         
                    if (isActionClick) {
                        console.log('Clic en un elemento de acción, no se abrirá el visor');
                        return;
                    }
                    
                    const photoId = card.dataset.photoId;
                    console.log(`Clic detectado en tarjeta de foto ${photoId}, abriendo visor...`);
                    this.showPhotoInViewer(photoId);
                    e.preventDefault();
                });
                
                console.log(`Configurado evento de clic para tarjeta con ID: ${card.dataset.photoId}`);
            });
            
            if (cards.length === 0) {
                console.warn('No se encontraron tarjetas de fotos para configurar eventos');
            } else {
                console.log('Configuración de eventos de clic completada');
            }
        },
        showPhotoInViewer(photoId) {
            console.log(`Iniciando función showPhotoInViewer para foto ${photoId}`);
            
            // Recopilar todas las fotos
            const photoCards = document.querySelectorAll('.photo-card');
            console.log(`Total de tarjetas de fotos encontradas: ${photoCards.length}`);
            
            const photos = [];
            let currentIndex = -1;
            
            photoCards.forEach((card, index) => {
                const id = card.dataset.photoId;
                const img = card.querySelector('img');
                const nameEl = card.querySelector('.photo-name');
                
                if (img) {
                    // Obtener URL de imagen completa (no thumbnail)
                    let fullUrl = img.src;
                    console.log(`URL original de imagen: ${fullUrl}`);
                    
                    if (fullUrl.includes('/thumb/')) {
                        fullUrl = fullUrl.replace('/thumb/', '/');
                        console.log(`URL convertida a imagen completa: ${fullUrl}`);
                    }
                    
                    const name = nameEl ? nameEl.textContent : `Foto ${index + 1}`;
                    
                    photos.push({
                        id: id,
                        url: fullUrl,
                        name: name
                    });
                    
                    console.log(`Foto procesada: ID=${id}, Nombre=${name}`);
                    
                    if (id === photoId) {
                        currentIndex = index;
                        console.log(`Foto actual encontrada en índice ${index}`);
                    }
                } else {
                    console.warn(`No se encontró imagen en tarjeta con ID ${id}`);
                }
            });
            
            if (currentIndex === -1 || photos.length === 0) {
                console.error('No se pudo encontrar la foto o no hay fotos disponibles');
                return;
            }
            
            // Comprobar si el modal ya existe o crearlo
            let modal = document.getElementById('photoViewerModal');
            
            if (!modal) {
                console.log('Modal no encontrado. Creando modal del visor de imágenes...');
                
                // Crear elemento del modal
                modal = document.createElement('div');
                modal.id = 'photoViewerModal';
                modal.className = 'slideshow-modal';
                
                // Contenido HTML del modal
                modal.innerHTML = `
                    <div class="slideshow-content">
                        <span class="slideshow-close">×</span>
                        <div class="slideshow-container">
                            <div class="slideshow-image-container">
                                <img id="slideshowImage" src="" alt="">
                            </div>
                            <h4 id="slideshowCaption" class="slideshow-caption"></h4>
                            <a class="slideshow-prev">&#10094;</a>
                            <a class="slideshow-next">&#10095;</a>
                        </div>
                        <div class="slideshow-counter">
                            <span id="slideshowCurrent">1</span> / <span id="slideshowTotal">0</span>
                        </div>
                    </div>
                `;
                
                console.log('Agregando modal al documento');
                document.body.appendChild(modal);
                
                // Configurar eventos del modal
                console.log('Configurando eventos del modal');
                
                const closeBtn = modal.querySelector('.slideshow-close');
                const prevBtn = modal.querySelector('.slideshow-prev');
                const nextBtn = modal.querySelector('.slideshow-next');
                
                closeBtn.addEventListener('click', () => {
                    console.log('Clic en botón cerrar');
                    modal.style.display = 'none';
                    document.body.style.overflow = '';
                });
                
                prevBtn.addEventListener('click', () => {
                    console.log('Clic en botón anterior');
                    this.navigateViewer(-1);
                });
                
                nextBtn.addEventListener('click', () => {
                    console.log('Clic en botón siguiente');
                    this.navigateViewer(1);
                });
                
                // Cerrar al hacer clic fuera de la imagen
                modal.addEventListener('click', (e) => {
                    if (e.target === modal) {
                        console.log('Clic fuera del contenido del modal. Cerrando...');
                        modal.style.display = 'none';
                        document.body.style.overflow = '';
                    }
                });
                
                // Navegación con teclado
                document.addEventListener('keydown', (e) => {
                    if (modal.style.display === 'block') {
                        console.log(`Tecla presionada: ${e.key}`);
                        if (e.key === 'ArrowLeft') {
                            this.navigateViewer(-1);
                        } else if (e.key === 'ArrowRight') {
                            this.navigateViewer(1);
                        } else if (e.key === 'Escape') {
                            modal.style.display = 'none';
                            document.body.style.overflow = '';
                        }
                    }
                });
                
                // Agregar estilos CSS si no existen
                if (!document.getElementById('viewerStyles')) {
                    console.log('Agregando estilos CSS para el visor');
                    const style = document.createElement('style');
                    style.id = 'viewerStyles';
                    style.textContent = `
                        .slideshow-modal {
                            display: none;
                            position: fixed;
                            z-index: 10000;
                            left: 0;
                            top: 0;
                            width: 100%;
                            height: 100%;
                            background-color: rgba(0, 0, 0, 0.9);
                            overflow: hidden;
                        }
                        
                        .slideshow-content {
                            position: relative;
                            width: 100%;
                            height: 100%;
                            display: flex;
                            flex-direction: column;
                            justify-content: center;
                            align-items: center;
                        }
                        
                        .slideshow-close {
                            position: absolute;
                            top: 15px;
                            right: 25px;
                            color: #f1f1f1;
                            font-size: 40px;
                            font-weight: bold;
                            transition: 0.3s;
                            z-index: 20;
                            cursor: pointer;
                        }
                        
                        .slideshow-close:hover {
                            color: #bbb;
                        }
                        
                        .slideshow-container {
                            position: relative;
                            width: 90%;
                            max-width: 1200px;
                            height: 80%;
                            display: flex;
                            flex-direction: column;
                            align-items: center;
                        }
                        
                        .slideshow-image-container {
                            width: 100%;
                            height: 90%;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            overflow: hidden;
                        }
                        
                        .slideshow-image-container img {
                            max-width: 100%;
                            max-height: 100%;
                            object-fit: contain;
                            transition: opacity 0.3s ease;
                        }
                        
                        .slideshow-caption {
                            color: #fff;
                            margin-top: 10px;
                            text-align: center;
                            font-size: 16px;
                            max-width: 80%;
                            overflow: hidden;
                            text-overflow: ellipsis;
                            white-space: nowrap;
                        }
                        
                        .slideshow-prev, .slideshow-next {
                            cursor: pointer;
                            position: absolute;
                            top: 50%;
                            width: auto;
                            padding: 16px;
                            margin-top: -50px;
                            color: white;
                            font-weight: bold;
                            font-size: 30px;
                            transition: 0.6s ease;
                            user-select: none;
                            -webkit-user-select: none;
                            background-color: rgba(0, 0, 0, 0.2);
                            border-radius: 50%;
                            height: 60px;
                            width: 60px;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                        }
                        
                        .slideshow-next {
                            right: 0;
                        }
                        
                        .slideshow-prev {
                            left: 0;
                        }
                        
                        .slideshow-prev:hover, .slideshow-next:hover {
                            background-color: rgba(0, 0, 0, 0.8);
                        }
                        
                        .slideshow-counter {
                            position: absolute;
                            bottom: 20px;
                            color: white;
                            font-size: 16px;
                            padding: 8px 16px;
                            background-color: rgba(0, 0, 0, 0.5);
                            border-radius: 20px;
                        }
                        
                        @media only screen and (max-width: 768px) {
                            .slideshow-prev, .slideshow-next {
                                font-size: 20px;
                                padding: 10px;
                                height: 40px;
                                width: 40px;
                            }
                            
                            .slideshow-close {
                                font-size: 30px;
                                top: 10px;
                                right: 15px;
                            }
                        }
                    `;
                    document.head.appendChild(style);
                }
            }
            
            // Guardar las fotos y el índice actual en el objeto gallery
            this.viewerPhotos = photos;
            this.viewerCurrentIndex = currentIndex;
            
            // Actualizar el contenido del modal
            console.log('Actualizando contenido del modal');
            const img = document.getElementById('slideshowImage');
            const caption = document.getElementById('slideshowCaption');
            const current = document.getElementById('slideshowCurrent');
            const total = document.getElementById('slideshowTotal');
            
            if (!img || !caption || !current || !total) {
                console.error('No se encontraron los elementos del modal');
                return;
            }
            
            // Mostrar imagen actual
            img.src = photos[currentIndex].url;
            caption.textContent = photos[currentIndex].name;
            current.textContent = currentIndex + 1;
            total.textContent = photos.length;
            
            // Mostrar el modal
            modal.style.display = 'block';
            document.body.style.overflow = 'hidden'; // Evitar scroll
            
            console.log(`Visor mostrando imagen ${currentIndex + 1} de ${photos.length}`);
        },

        navigateViewer(step) {
            console.log(`Navegando ${step > 0 ? 'adelante' : 'atrás'} en el visor`);
            
            if (!this.viewerPhotos || this.viewerPhotos.length === 0) {
                console.error('No hay fotos disponibles para navegar');
                return;
            }
            
            // Calcular nuevo índice con manejo circular
            const newIndex = (this.viewerCurrentIndex + step + this.viewerPhotos.length) % this.viewerPhotos.length;
            console.log(`Navegando de imagen ${this.viewerCurrentIndex + 1} a ${newIndex + 1} de ${this.viewerPhotos.length}`);
            
            this.viewerCurrentIndex = newIndex;
            
            // Actualizar elementos del visor
            const img = document.getElementById('slideshowImage');
            const caption = document.getElementById('slideshowCaption');
            const current = document.getElementById('slideshowCurrent');
            
            if (!img || !caption || !current) {
                console.error('No se encontraron los elementos del visor para actualizar');
                return;
            }
            
            // Efecto de transición
            img.style.opacity = '0.3';
            
            // Actualizar contenido
            img.src = this.viewerPhotos[newIndex].url;
            caption.textContent = this.viewerPhotos[newIndex].name;
            current.textContent = newIndex + 1;
            
            // Restaurar opacidad después de cargar
            img.onload = function() {
                img.style.opacity = '1';
            };
            
            console.log('Navegación completada');
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
                    
                    // Obtener nombre de archivo para descargar
                    const filename = button.getAttribute('data-filename') || 'foto.jpg';
                    console.log(`Descargando como: ${filename}`);
                    link.setAttribute('download', filename);
                    
                    // Añadir link al DOM, hacer clic y luego remover
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                    
                    // Liberar URL
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
        
            // Intento de copiar URL al portapapeles usando Clipboard API
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
        
        getCurrentPageUrl() {
            console.log('Obteniendo URL canónica o limpia...');
            // Obtener la URL canónica si existe, si no, usar la URL actual
            const canonicalElement = document.querySelector("link[rel='canonical']");
            if (canonicalElement) {
                console.log(`URL canónica encontrada: ${canonicalElement.href}`);
                return canonicalElement.href;
            }
            
            // Si no hay URL canónica, usar la URL actual limpia
            const url = new URL(window.location.href);
            console.log(`URL original: ${url.toString()}`);
            
            // Eliminar parámetros UTM y otros parámetros de tracking si existen
            const paramsToRemove = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content'];
            paramsToRemove.forEach(param => {
                if (url.searchParams.has(param)) {
                    console.log(`Eliminando parámetro: ${param}`);
                    url.searchParams.delete(param);
                }
            });
            
            console.log(`URL limpia: ${url.toString()}`);
            return url.toString();
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
        handleMassiveUpload(event) {
            console.log('Iniciando proceso de subida masiva de archivos');
            const files = Array.from(event.target.files);
            console.log(`Total de archivos seleccionados: ${files.length}`);
            
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
                        element.remove();  // Elimina la tarjeta de la galería sin recargar
                        console.log('Foto eliminada correctamente:', photoId);
                        this.showSuccess('Éxito', 'Foto eliminada correctamente');
                    } else {
                        console.warn(`No se encontró elemento DOM para foto ID: ${photoId}`);
                        // Recargar página si no se encuentra el elemento
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
            
            // Obtenemos todas las imágenes de las tarjetas de fotos
            const photoCards = document.querySelectorAll('.photo-card');
            console.log(`Se encontraron ${photoCards.length} tarjetas de fotos`);
            
            // Usar IntersectionObserver para cargar imágenes de forma eficiente
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

                // Observar todas las imágenes en las tarjetas
                photoCards.forEach(card => {
                    const img = card.querySelector('img');
                    if (img && !img.classList.contains('loaded')) {
                        imageObserver.observe(img);
                    }
                });
            } else {
                console.log('IntersectionObserver no disponible, cargando todas las imágenes directamente');
                // Fallback para navegadores que no soporten IntersectionObserver
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