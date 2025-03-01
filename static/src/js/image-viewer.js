// Archivo: /sat/static/src/js/image-viewer.js

document.addEventListener('DOMContentLoaded', function() {
    console.log('Inicializando visor de imágenes mejorado v2...');
    
    // Variables para seguimiento de imágenes
    let currentIndex = 0;
    let galleryImages = [];
    
    // Aplicar estilos críticos directamente al DOM
    function applyImageViewerStyles() {
        const slideshowModal = document.getElementById('slideshowModal');
        const slideshowImageContainer = document.querySelector('.slideshow-image-container');
        const slideshowImage = document.getElementById('slideshowImage');
        
        if (slideshowModal) {
            // Estilos para el modal
            slideshowModal.style.zIndex = '10000';
        }
        
        if (slideshowImageContainer) {
            // Estilos para el contenedor de la imagen
            slideshowImageContainer.style.width = '100%';
            slideshowImageContainer.style.height = '90%';
            slideshowImageContainer.style.display = 'flex';
            slideshowImageContainer.style.alignItems = 'center';
            slideshowImageContainer.style.justifyContent = 'center';
            slideshowImageContainer.style.overflow = 'hidden';
        }
        
        if (slideshowImage) {
            // Estilos críticos para la imagen - estos sobreescriben cualquier otro estilo
            Object.assign(slideshowImage.style, {
                position: 'static',
                top: 'auto',
                left: 'auto',
                width: 'auto',
                height: 'auto',
                maxWidth: '90%',
                maxHeight: '90%',
                objectFit: 'contain',
                transform: 'none',
                transition: 'opacity 0.3s ease',
                opacity: '1'
            });
        }
        
        console.log('Estilos críticos aplicados directamente a los elementos del visor');
    }
    
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
        
        // Indicar carga en progreso
        viewerImage.style.opacity = '0.2';
        
        // Asegurarnos de usar la URL de la imagen completa, no la miniatura
        let fullUrl = galleryImages[currentIndex].fullUrl;
        if (fullUrl.includes('/thumb/')) {
            fullUrl = fullUrl.replace('/thumb/', '/');
        }
        if (fullUrl.includes('/gallery/preview/')) {
            fullUrl = fullUrl.replace('/gallery/preview/', '/gallery/download/');
        }
        
        console.log(`Cargando imagen desde URL: ${fullUrl}`);
        
        // Cargar la nueva imagen
        const newImage = new Image();
        newImage.onload = function() {
            console.log('Imagen cargada correctamente');
            
            // Actualizar la imagen en el DOM solo después de que se haya cargado
            viewerImage.src = fullUrl;
            viewerImage.alt = galleryImages[currentIndex].name || '';
            
            // Restablecer todos los estilos críticos
            Object.assign(viewerImage.style, {
                position: 'static',
                top: 'auto',
                left: 'auto',
                width: 'auto',
                height: 'auto',
                maxWidth: '90%',
                maxHeight: '90%',
                objectFit: 'contain',
                transform: 'none'
            });
            
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
                
                // Si es una URL de vista previa, cambiarla a URL de descarga
                if (fullUrl.includes('/gallery/preview/')) {
                    fullUrl = fullUrl.replace('/gallery/preview/', '/gallery/download/');
                }
                
                // Si tiene /thumb/ en la ruta, cambiarlo
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
    
    // Aplicar estilos iniciales al cargar la página
    applyImageViewerStyles();
    
    console.log('Inicialización del visor mejorado completada');
});