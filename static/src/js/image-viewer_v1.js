// Archivo: /sat/static/src/js/image-viewer.js
document.addEventListener('DOMContentLoaded', function() {
    console.log('Inicializando visor de imágenes - VERSIÓN MÓVIL OPTIMIZADA');
    
    // Variables para seguimiento de imágenes
    let currentIndex = 0;
    let galleryImages = [];
    
    // Detectar si es dispositivo móvil
    function isMobileDevice() {
        const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
        console.log('Detección de dispositivo móvil:', isMobile);
        return isMobile;
    }
    
    // Función principal de inicialización
    function init() {
        console.log('Inicializando módulo de visor de imágenes');
        
        // Configurar o crear HTML del visor si no existe
        setupViewerHTML();
        
        // Aplicar estilos iniciales
        applyImageViewerStyles();
        
        // Configurar eventos
        setupViewerEvents();
        
        // Configurar eventos de clic en las imágenes de la galería
        setupGalleryClicks();
        
        // Agregar estilos adicionales
        addExtraStyles();
        
        console.log('Inicialización del visor completada');
    }
    
    // Configurar o crear el HTML del visor
    function setupViewerHTML() {
        let modal = document.getElementById('slideshowModal');
        
        if (!modal) {
            console.log('Modal no encontrado. Creando modal del visor de imágenes...');
            
            // Crear elemento del modal
            modal = document.createElement('div');
            modal.id = 'slideshowModal';
            modal.className = 'slideshow-modal';
            
            // Contenido HTML del modal
            modal.innerHTML = `
                <div class="slideshow-content">
                    <span class="slideshow-close">×</span>
                    <div class="slideshow-container">
                        <div class="slideshow-image-container" style="display:flex !important; align-items:center !important; justify-content:center !important;">
                            <img id="slideshowImage" src="" alt=""
                                 style="position:static !important; 
                                        width:auto !important; 
                                        height:auto !important; 
                                        max-width:95% !important; 
                                        max-height:95% !important; 
                                        object-fit:contain !important;
                                        transform:none !important;
                                        margin:0 auto !important;" />
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
        } else {
            // Si ya existe, asegurarse de que la imagen tenga los estilos inline necesarios
            const slideshowImage = document.getElementById('slideshowImage');
            if (slideshowImage) {
                console.log('Asegurando que la imagen del visor tiene los estilos correctos');
                slideshowImage.setAttribute('style', 
                    'position:static !important; width:auto !important; height:auto !important; ' +
                    'max-width:95% !important; max-height:95% !important; object-fit:contain !important; ' +
                    'transform:none !important; transition:opacity 0.3s ease !important; margin:0 auto !important;');
            }
        }
    }
    
    // Agregar estilos adicionales directamente al DOM
    function addExtraStyles() {
        const styleId = 'imageViewerExtraStyles';
        
        // Evitar duplicados
        if (document.getElementById(styleId)) {
            return;
        }
        
        const styleEl = document.createElement('style');
        styleEl.id = styleId;
        
        // Estilos adicionales con mejoras para móviles
        styleEl.textContent = `
            /* Contenedor principal del visor */
            .slideshow-container {
                position: relative !important;
                width: 95% !important;
                max-width: 1600px !important;
                height: 85% !important;
                display: flex !important;
                flex-direction: column !important;
                align-items: center !important;
                justify-content: center !important;
                margin: 0 auto !important;
            }
            
            /* Modal con mejor soporte para móviles */
            .slideshow-modal {
                display: none !important;
                position: fixed !important;
                z-index: 10000 !important;
                left: 0 !important;
                top: 0 !important;
                width: 100% !important;
                height: 100% !important;
                overflow: hidden !important;
                background-color: rgba(0, 0, 0, 0.9) !important;
                -webkit-user-select: none !important;
                user-select: none !important;
                touch-action: manipulation !important;
            }
            
            /* Contenido del modal */
            .slideshow-content {
                margin: auto !important;
                display: block !important;
                width: 100% !important;
                height: 100% !important;
                max-width: none !important;
                position: relative !important;
            }
            
            /* Contenedor de la imagen */
            .slideshow-image-container {
                width: 100% !important;
                height: 90% !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                overflow: hidden !important;
                background-color: rgba(0, 0, 0, 0.1) !important;
                border-radius: 5px !important;
                padding: 10px !important;
                box-sizing: border-box !important;
                touch-action: manipulation !important;
            }
            
            /* Imagen en el visor */
            #slideshowImage {
                position: static !important;
                top: auto !important;
                left: auto !important;
                width: auto !important;
                height: auto !important;
                max-width: 95% !important;
                max-height: 95% !important;
                object-fit: contain !important;
                transform: none !important;
                transition: all 0.3s ease !important;
                margin: 0 auto !important;
                box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2) !important;
                touch-action: manipulation !important;
                -webkit-user-select: none !important;
                user-select: none !important;
            }
            
            /* Estilos para imágenes verticales */
            #slideshowImage.vertical {
                max-height: 95% !important;
                max-width: 90% !important;
            }
            
            /* Estilos para imágenes horizontales */
            #slideshowImage.horizontal {
                max-width: 95% !important;
                max-height: 90% !important;
            }
            
            /* Botones de navegación adaptados para móviles */
            .slideshow-prev, .slideshow-next {
                cursor: pointer !important;
                position: absolute !important;
                top: 50% !important;
                transform: translateY(-50%) !important;
                padding: 16px !important;
                color: white !important;
                font-weight: bold !important;
                font-size: 24px !important;
                transition: 0.3s ease !important;
                user-select: none !important;
                -webkit-user-select: none !important;
                background-color: rgba(0, 0, 0, 0.5) !important;
                border-radius: 50% !important;
                height: 50px !important;
                width: 50px !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                z-index: 10 !important;
                touch-action: manipulation !important;
                -webkit-tap-highlight-color: transparent !important;
            }
            
            /* Botones más grandes en móviles */
            @media (max-width: 768px) {
                .slideshow-prev, .slideshow-next {
                    height: 60px !important;
                    width: 60px !important;
                    font-size: 28px !important;
                    padding: 20px !important;
                }
            }
            
            .slideshow-next {
                right: 15px !important;
            }
            
            .slideshow-prev {
                left: 15px !important;
            }
            
            .slideshow-prev:hover, .slideshow-next:hover,
            .slideshow-prev:active, .slideshow-next:active {
                background-color: rgba(0, 0, 0, 0.8) !important;
            }
            
            /* Contador mejorado */
            .slideshow-counter {
                position: absolute !important;
                bottom: 20px !important;
                color: white !important;
                font-size: 16px !important;
                padding: 8px 20px !important;
                background-color: rgba(0, 0, 0, 0.5) !important;
                border-radius: 20px !important;
                z-index: 5 !important;
                font-weight: bold !important;
                left: 50% !important;
                transform: translateX(-50%) !important;
            }
            
            /* Botón de cierre mejorado para móviles */
            .slideshow-close {
                position: absolute !important;
                top: 15px !important;
                right: 25px !important;
                color: #f1f1f1 !important;
                font-size: 40px !important;
                font-weight: bold !important;
                transition: 0.3s !important;
                z-index: 20 !important;
                cursor: pointer !important;
                width: 50px !important;
                height: 50px !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                border-radius: 50% !important;
                background-color: rgba(0, 0, 0, 0.5) !important;
                line-height: 1 !important;
                touch-action: manipulation !important;
                -webkit-tap-highlight-color: transparent !important;
            }
            
            /* Botón de cierre más grande en móviles */
            @media (max-width: 768px) {
                .slideshow-close {
                    width: 60px !important;
                    height: 60px !important;
                    font-size: 45px !important;
                    top: 20px !important;
                    right: 20px !important;
                }
            }
            
            .slideshow-close:hover,
            .slideshow-close:active {
                background-color: rgba(0, 0, 0, 0.8) !important;
            }
            
            /* Título/caption responsive */
            .slideshow-caption {
                color: white !important;
                text-align: center !important;
                margin: 10px 0 !important;
                font-size: 16px !important;
                padding: 0 20px !important;
                max-height: 10% !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
            }
            
            @media (max-width: 768px) {
                .slideshow-caption {
                    font-size: 14px !important;
                    padding: 0 15px !important;
                }
            }
            
            /* Efecto de zoom reducido en móviles */
            @media (min-width: 769px) {
                #slideshowImage:hover {
                    transform: scale(1.02) !important;
                }
            }
            
            /* Mejorar áreas táctiles para móviles */
            .photo-container {
                touch-action: manipulation !important;
                -webkit-tap-highlight-color: transparent !important;
            }
            
            .photo-container img {
                touch-action: manipulation !important;
                -webkit-user-select: none !important;
                user-select: none !important;
            }
        `;
        
        document.head.appendChild(styleEl);
        console.log('Estilos adicionales inyectados (optimizados para móviles)');
    }
    
    // Aplicar estilos críticos directamente al DOM
    function applyImageViewerStyles() {
        const slideshowModal = document.getElementById('slideshowModal');
        const slideshowImageContainer = document.querySelector('.slideshow-image-container');
        const slideshowImage = document.getElementById('slideshowImage');
        
        if (slideshowModal) {
            // Estilos para el modal
            slideshowModal.style.zIndex = '10000';
            slideshowModal.style.touchAction = 'manipulation';
        }
        
        if (slideshowImageContainer) {
            // Estilos para el contenedor de la imagen
            Object.assign(slideshowImageContainer.style, {
                width: '100%',
                height: '90%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden',
                touchAction: 'manipulation'
            });
        }
        
        if (slideshowImage) {
            // Estilos críticos para la imagen - estos sobreescriben cualquier otro estilo
            Object.assign(slideshowImage.style, {
                position: 'static',
                top: 'auto',
                left: 'auto',
                width: 'auto',
                height: 'auto',
                maxWidth: '95%',
                maxHeight: '95%',
                objectFit: 'contain',
                transform: 'none',
                transition: 'opacity 0.3s ease',
                opacity: '1',
                margin: '0 auto',
                touchAction: 'manipulation'
            });
        }
        
        console.log('Estilos críticos aplicados directamente a los elementos del visor');
    }
    
    // Configurar los eventos del visor con soporte para móviles
    function setupViewerEvents() {
        const modal = document.getElementById('slideshowModal');
        const closeBtn = document.querySelector('.slideshow-close');
        const prevBtn = document.querySelector('.slideshow-prev');
        const nextBtn = document.querySelector('.slideshow-next');
        
        if (!modal || !closeBtn || !prevBtn || !nextBtn) {
            console.error('No se encontraron elementos necesarios del visor');
            return;
        }
        
        // Función para cerrar el modal
        function closeModal() {
            modal.style.display = 'none';
            document.body.style.overflow = '';
            console.log('Modal cerrado');
        }
        
        // Cerrar al hacer clic/tocar en X
        closeBtn.addEventListener('click', closeModal);
        if (isMobileDevice()) {
            closeBtn.addEventListener('touchend', function(e) {
                e.preventDefault();
                closeModal();
            });
        }
        
        // Cerrar al hacer clic fuera de la imagen
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeModal();
            }
        });
        
        // Navegación: anterior
        function prevImage(e) {
            e.stopPropagation();
            e.preventDefault();
            navigateViewer(-1);
        }
        
        function nextImage(e) {
            e.stopPropagation();
            e.preventDefault();
            navigateViewer(1);
        }
        
        prevBtn.addEventListener('click', prevImage);
        nextBtn.addEventListener('click', nextImage);
        
        // Eventos táctiles para móviles
        if (isMobileDevice()) {
            prevBtn.addEventListener('touchend', function(e) {
                e.preventDefault();
                prevImage(e);
            });
            
            nextBtn.addEventListener('touchend', function(e) {
                e.preventDefault();
                nextImage(e);
            });
        }
        
        // Navegación con teclado
        document.addEventListener('keydown', function(e) {
            if (modal.style.display === 'block') {
                if (e.key === 'ArrowLeft') {
                    navigateViewer(-1);
                } else if (e.key === 'ArrowRight') {
                    navigateViewer(1);
                } else if (e.key === 'Escape') {
                    closeModal();
                }
            }
        });
        
        console.log('Eventos del visor configurados (con soporte móvil)');
    }
    
    // Actualizar la imagen en el visor con ajuste automático según sus dimensiones
    function updateViewerImage() {
        const viewerImage = document.getElementById('slideshowImage');
        const caption = document.getElementById('slideshowCaption');
        const currentCounter = document.getElementById('slideshowCurrent');
        
        if (!viewerImage || !caption || !currentCounter) {
            console.error('No se encontraron elementos necesarios para actualizar la imagen');
            return;
        }
        
        // Indicar carga en progreso
        viewerImage.style.opacity = '0.2';
        
        // Asegurarnos de usar la URL de la imagen completa, no la miniatura
        let fullUrl = galleryImages[currentIndex].fullUrl;
        
        // Convertir URL de preview a URL de descarga
        if (fullUrl.includes('/gallery/preview/')) {
            fullUrl = fullUrl.replace('/gallery/preview/', '/gallery/download/');
        } else if (fullUrl.includes('/thumb/')) {
            fullUrl = fullUrl.replace('/thumb/', '/');
        }
        
        console.log(`Cargando imagen desde URL: ${fullUrl}`);
        
        // Cargar la nueva imagen y determinar si es vertical u horizontal
        const newImage = new Image();
        newImage.onload = function() {
            console.log(`Imagen cargada correctamente. Dimensiones: ${newImage.width}x${newImage.height}`);
            
            // Determinar la orientación de la imagen
            const isVertical = newImage.height > newImage.width;
            
            // Actualizar la imagen en el DOM
            viewerImage.src = fullUrl;
            viewerImage.alt = galleryImages[currentIndex].name || '';
            
            // Aplicar clase según orientación
            viewerImage.className = isVertical ? 'visor-full vertical' : 'visor-full horizontal';
            
            // Calcular dimensiones óptimas
            const container = document.querySelector('.slideshow-image-container');
            const containerWidth = container ? container.clientWidth * 0.95 : window.innerWidth * 0.9;
            const containerHeight = container ? container.clientHeight * 0.95 : window.innerHeight * 0.8;
            
            // Calcular proporciones
            const imageRatio = newImage.width / newImage.height;
            
            // Aplicar dimensiones específicas para aprovechar mejor el espacio
            if (isVertical) {
                // Imagen vertical
                if (newImage.height > containerHeight) {
                    const newHeight = containerHeight;
                    const newWidth = newHeight * imageRatio;
                    
                    if (newWidth > containerWidth) {
                        viewerImage.style.width = `${containerWidth}px`;
                        viewerImage.style.height = 'auto';
                    } else {
                        viewerImage.style.height = `${newHeight}px`;
                        viewerImage.style.width = 'auto';
                    }
                } else {
                    viewerImage.style.height = 'auto';
                    viewerImage.style.width = 'auto';
                }
            } else {
                // Imagen horizontal
                if (newImage.width > containerWidth) {
                    const newWidth = containerWidth;
                    const newHeight = newWidth / imageRatio;
                    
                    if (newHeight > containerHeight) {
                        viewerImage.style.height = `${containerHeight}px`;
                        viewerImage.style.width = 'auto';
                    } else {
                        viewerImage.style.width = `${newWidth}px`;
                        viewerImage.style.height = 'auto';
                    }
                } else {
                    viewerImage.style.width = 'auto';
                    viewerImage.style.height = 'auto';
                }
            }
            
            // Restablecer estilos críticos adicionales
            Object.assign(viewerImage.style, {
                position: 'static',
                top: 'auto',
                left: 'auto',
                objectFit: 'contain',
                transform: 'none',
                margin: '0 auto',
                transition: 'all 0.3s ease',
                touchAction: 'manipulation'
            });
            
            // Aplicar estilos de visualización mejorados
            viewerImage.style.boxShadow = '0 5px 15px rgba(0, 0, 0, 0.2)';
            viewerImage.style.borderRadius = '4px';
            
            // Mostrar la imagen con transición
            setTimeout(() => {
                viewerImage.style.opacity = '1';
            }, 50);
        };
        
        newImage.onerror = function() {
            console.error(`Error al cargar la imagen desde: ${fullUrl}`);
            viewerImage.src = '/sat/static/src/img/placeholder.png';
            viewerImage.style.opacity = '1';
        };
        
        // Iniciar la carga de la imagen
        newImage.src = fullUrl;
        
        // Actualizar pie de foto y contador
        caption.textContent = galleryImages[currentIndex].name || '';
        currentCounter.textContent = currentIndex + 1;
        
        console.log(`Mostrando imagen ${currentIndex + 1} de ${galleryImages.length}`);
    }
    
    // Navegación del visor
    function navigateViewer(step) {
        if (!galleryImages || galleryImages.length === 0) {
            console.error('No hay imágenes para navegar');
            return;
        }
        
        currentIndex = (currentIndex + step + galleryImages.length) % galleryImages.length;
        updateViewerImage();
    }
    
    // Abrir el visor con una imagen específica
    function openImageViewer(imageId) {
        console.log(`Abriendo visor optimizado para imagen ID: ${imageId}`);
        
        // Recopilar todas las imágenes de la galería
        const photoCards = document.querySelectorAll('.photo-card');
        console.log(`Encontradas ${photoCards.length} tarjetas de fotos`);
        
        galleryImages = [];
        currentIndex = 0;
        
        photoCards.forEach((card, index) => {
            const id = card.dataset.photoId;
            const img = card.querySelector('img');
            const nameEl = card.querySelector('.photo-name');
            
            if (img) {
                // Obtener URL de imagen completa (no miniatura)
                let fullUrl = img.src;
                
                // Si es una URL de vista previa, cambiarla a URL de descarga
                if (fullUrl.includes('/gallery/preview/')) {
                    fullUrl = fullUrl.replace('/gallery/preview/', '/gallery/download/');
                } else if (fullUrl.includes('/thumb/')) {
                    fullUrl = fullUrl.replace('/thumb/', '/');
                }
                
                galleryImages.push({
                    id: id,
                    fullUrl: fullUrl,
                    thumbUrl: img.src,
                    name: nameEl ? nameEl.textContent : ''
                });
                
                // Si es la imagen que se hizo clic, guardar el índice
                if (id === imageId) {
                    currentIndex = galleryImages.length - 1;
                }
            }
        });
        
        // Verificar que tenemos imágenes
        if (galleryImages.length === 0) {
            console.error('No se encontraron imágenes en la galería');
            return;
        }
        
        // Actualizar contador total
        const totalCounter = document.getElementById('slideshowTotal');
        if (totalCounter) {
            totalCounter.textContent = galleryImages.length;
        }
        
        // Mostrar el visor
        const modal = document.getElementById('slideshowModal');
        if (!modal) {
            console.error('No se encontró el elemento del modal');
            return;
        }
        
        // Asegurar que los estilos se aplican correctamente
        applyImageViewerStyles();
        
        modal.style.display = 'block';
        document.body.style.overflow = 'hidden';  // Prevenir scroll
        
        // Actualizar la imagen mostrada
        updateViewerImage();
    }
    
    // Configurar eventos de clic en las imágenes de la galería (optimizado para móviles)
    function setupGalleryClicks() {
        const photoCards = document.querySelectorAll('.photo-card');
        console.log(`Configurando eventos de clic para ${photoCards.length} tarjetas de fotos`);
        
        photoCards.forEach(card => {
            // Solo configurar evento en la parte de la imagen
            const photoContainer = card.querySelector('.photo-container');
            if (photoContainer) {
                // Función para manejar el clic/toque
                function handleImageClick(e) {
                    console.log('Evento detectado:', e.type);
                    
                    // Verificar si el clic fue en un botón o enlace
                    const isActionClick = e.target.tagName === 'BUTTON' || 
                                        e.target.tagName === 'A' || 
                                        e.target.closest('button') || 
                                        e.target.closest('a') || 
                                        e.target.closest('.actions-bar') ||
                                        e.target.closest('.download-photo') ||
                                        e.target.closest('.delete-photo');
                    
                    // Si el clic fue en un botón o enlace, no hacer nada
                    if (isActionClick) {
                        console.log('Clic en un elemento de acción, no se abrirá el visor');
                        return;
                    }
                    
                    // Prevenir propagación y comportamiento por defecto
                    e.preventDefault();
                    e.stopPropagation();
                    
                    const photoId = card.dataset.photoId;
                    console.log(`${e.type} en contenedor de foto ${photoId}`);
                    openImageViewer(photoId);
                }
                
                // Eliminar cualquier controlador de eventos existente (para evitar duplicados)
                const newPhotoContainer = photoContainer.cloneNode(true);
                if (photoContainer.parentNode) {
                    photoContainer.parentNode.replaceChild(newPhotoContainer, photoContainer);
                }
                
                // Agregar eventos tanto para móviles como para escritorio
                if (isMobileDevice()) {
                    console.log('Configurando eventos táctiles para móvil');
                    
                    // Para móviles, usar touchend que es más confiable
                    newPhotoContainer.addEventListener('touchend', function(e) {
                        // Solo procesar si es un toque simple (no un gesto de scroll/zoom)
                        if (e.touches.length === 0 && e.changedTouches.length === 1) {
                            handleImageClick(e);
                        }
                    }, { passive: false });
                    
                    // También mantener click como respaldo
                    newPhotoContainer.addEventListener('click', handleImageClick);
                } else {
                    console.log('Configurando eventos de clic para escritorio');
                    // Para escritorio, solo usar click
                    newPhotoContainer.addEventListener('click', handleImageClick);
                }
                
                // Mejorar la experiencia táctil
                newPhotoContainer.style.touchAction = 'manipulation';
                newPhotoContainer.style.webkitTapHighlightColor = 'transparent';
            }
        });
        
        console.log('Configuración de clics en galería completada (optimizada para móviles)');
    }
    
    // Iniciar la inicialización
    init();
});