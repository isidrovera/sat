// Archivo: /sat/static/src/js/image-viewer.js
document.addEventListener('DOMContentLoaded', function() {
    console.log('Inicializando visor de imágenes mejorado...');
    
    // Cargar los estilos CSS dinámicamente
    function loadExternalStyles() {
        const cssUrl = '/sat/static/src/css/image-viewer.css';
        
        const linkElement = document.createElement('link');
        linkElement.rel = 'stylesheet';
        linkElement.type = 'text/css';
        linkElement.href = cssUrl;
        
        document.head.appendChild(linkElement);
        
        console.log('Estilos del visor cargados dinámicamente');
        
        linkElement.onerror = function() {
            console.error('Error al cargar los estilos del visor. Aplicando estilos en línea de respaldo');
            applyInlineStyles();
        };
    }
    
    // Función de respaldo que aplica estilos en línea si falla la carga del CSS externo
    function applyInlineStyles() {
        const styles = `
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
                width: 95%;
                max-width: 1500px;
                height: 85%;
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
                position: static !important;
                top: auto !important;
                left: auto !important;
                width: auto !important;
                height: auto !important;
                max-width: 95% !important;
                max-height: 95% !important;
                object-fit: contain !important;
                transform: none !important;
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
                padding: 16px;
                margin-top: -50px;
                color: white;
                font-weight: bold;
                font-size: 30px;
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
            
            .slideshow-counter {
                position: absolute;
                bottom: 20px;
                color: white;
                font-size: 16px;
                padding: 8px 16px;
                background-color: rgba(0, 0, 0, 0.5);
                border-radius: 20px;
            }
        `;
        
        const styleElement = document.createElement('style');
        styleElement.textContent = styles;
        document.head.appendChild(styleElement);
        
        console.log('Estilos en línea aplicados como respaldo');
    }
    
    // Intentar cargar los estilos externos
    loadExternalStyles();
    
    // Aplicar directamente los estilos críticos como respaldo adicional
    function applyImageViewerStyles() {
        const slideshowImageContainer = document.querySelector('.slideshow-image-container');
        const slideshowImage = document.getElementById('slideshowImage');
        
        if (slideshowImageContainer && slideshowImage) {
            // Estilos para el contenedor de la imagen
            slideshowImageContainer.style.width = '100%';
            slideshowImageContainer.style.height = '90%';
            slideshowImageContainer.style.display = 'flex';
            slideshowImageContainer.style.alignItems = 'center';
            slideshowImageContainer.style.justifyContent = 'center';
            
            // Estilos críticos para la imagen
            slideshowImage.style.position = 'static';
            slideshowImage.style.maxWidth = '95%';
            slideshowImage.style.maxHeight = '95%';
            slideshowImage.style.width = 'auto';
            slideshowImage.style.height = 'auto';
            slideshowImage.style.objectFit = 'contain';
            slideshowImage.style.transform = 'none';
            
            console.log('Estilos críticos aplicados directamente a los elementos del visor');
        }
    }
    
    // Variables para seguimiento de imágenes
    let currentIndex = 0;
    let galleryImages = [];
    
    // Configurar los eventos del visor
    function setupViewerEvents() {
        const modal = document.getElementById('slideshowModal');
        const closeBtn = document.querySelector('.slideshow-close');
        const prevBtn = document.querySelector('.slideshow-prev');
        const nextBtn = document.querySelector('.slideshow-next');
        
        if (!modal || !closeBtn || !prevBtn || !nextBtn) {
            console.error('No se encontraron elementos necesarios del visor');
            return;
        }
        
        // Cerrar al hacer clic en X
        closeBtn.addEventListener('click', function() {
            modal.style.display = 'none';
            document.body.style.overflow = '';
        });
        
        // Cerrar al hacer clic fuera de la imagen
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                modal.style.display = 'none';
                document.body.style.overflow = '';
            }
        });
        
        // Navegación: anterior
        prevBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            currentIndex = (currentIndex - 1 + galleryImages.length) % galleryImages.length;
            updateViewerImage();
        });
        
        // Navegación: siguiente
        nextBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            currentIndex = (currentIndex + 1) % galleryImages.length;
            updateViewerImage();
        });
        
        // Navegación con teclado
        document.addEventListener('keydown', function(e) {
            if (modal.style.display === 'block') {
                if (e.key === 'ArrowLeft') {
                    currentIndex = (currentIndex - 1 + galleryImages.length) % galleryImages.length;
                    updateViewerImage();
                } else if (e.key === 'ArrowRight') {
                    currentIndex = (currentIndex + 1) % galleryImages.length;
                    updateViewerImage();
                } else if (e.key === 'Escape') {
                    modal.style.display = 'none';
                    document.body.style.overflow = '';
                }
            }
        });
        
        console.log('Eventos del visor configurados');
    }
    
    // Actualizar la imagen en el visor
    function updateViewerImage() {
        const viewerImage = document.getElementById('slideshowImage');
        const caption = document.getElementById('slideshowCaption');
        const currentCounter = document.getElementById('slideshowCurrent');
        
        if (!viewerImage || !caption || !currentCounter) {
            console.error('No se encontraron elementos necesarios para actualizar la imagen');
            return;
        }
        
        // Indicador de carga
        viewerImage.style.opacity = '0.2';
        
        // Asegurarnos de usar la URL de la imagen completa, no la miniatura
        let fullUrl = galleryImages[currentIndex].fullUrl;
        if (fullUrl.includes('/thumb/')) {
            fullUrl = fullUrl.replace('/thumb/', '/');
        }
        
        // Cargar la nueva imagen
        const newImage = new Image();
        newImage.onload = function() {
            // Actualizar la imagen en el DOM solo después de que se haya cargado
            viewerImage.src = fullUrl;
            viewerImage.alt = galleryImages[currentIndex].name || '';
            
            // Restablecer todos los estilos críticos
            viewerImage.style.position = 'static';
            viewerImage.style.top = 'auto';
            viewerImage.style.left = 'auto';
            viewerImage.style.width = 'auto';
            viewerImage.style.height = 'auto';
            viewerImage.style.maxWidth = '95%';
            viewerImage.style.maxHeight = '95%';
            viewerImage.style.objectFit = 'contain';
            viewerImage.style.transform = 'none';
            
            // Mostrar la imagen con transición
            setTimeout(() => {
                viewerImage.style.opacity = '1';
            }, 50);
        };
        
        // Iniciar la carga de la imagen
        newImage.src = fullUrl;
        
        // Actualizar pie de foto y contador
        caption.textContent = galleryImages[currentIndex].name || '';
        currentCounter.textContent = currentIndex + 1;
        
        console.log(`Mostrando imagen ${currentIndex + 1} de ${galleryImages.length}`);
    }
    
    // Abrir el visor con una imagen específica
    function openImageViewer(imageId) {
        console.log(`Abriendo visor mejorado para imagen ID: ${imageId}`);
        
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
                // Obtener URL de imagen completa (reemplazar /thumb/ si existe)
                let fullUrl = img.src;
                if (fullUrl.includes('/thumb/')) {
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
    
    // Configurar eventos de clic en las imágenes de la galería
    function setupGalleryClicks() {
        const photoCards = document.querySelectorAll('.photo-card');
        console.log(`Configurando eventos de clic para ${photoCards.length} tarjetas de fotos`);
        
        photoCards.forEach(card => {
            // Solo configurar evento en la parte de la imagen
            const photoContainer = card.querySelector('.photo-container');
            if (photoContainer) {
                photoContainer.addEventListener('click', function(e) {
                    // Prevenir propagación y comportamiento por defecto
                    e.preventDefault();
                    e.stopPropagation();
                    
                    const photoId = card.dataset.photoId;
                    console.log(`Clic en contenedor de foto ${photoId}`);
                    openImageViewer(photoId);
                });
            }
        });
    }
    
    // Iniciar la configuración
    setupViewerEvents();
    setupGalleryClicks();
    
    console.log('Inicialización del visor mejorado completada');
});