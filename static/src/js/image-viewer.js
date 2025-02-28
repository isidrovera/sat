// Agregar este código al final de tu archivo gallery.js
// O crear un nuevo archivo y agregarlo después de cargar gallery.js

document.addEventListener('DOMContentLoaded', function() {
    console.log('Inicializando visor de imágenes...');
    
    // Añadir HTML para el visor modal
    const modalHTML = `
    <div id="imageViewer" class="modal-viewer" style="display:none;">
        <span class="close-viewer">&times;</span>
        <div class="modal-content-viewer">
            <img id="viewerImage" src="">
            <div class="navigation">
                <a class="prev-btn">&#10094;</a>
                <a class="next-btn">&#10095;</a>
            </div>
            <div class="image-counter">
                <span id="currentImage">1</span> / <span id="totalImages">0</span>
            </div>
        </div>
    </div>`;
    
    // Añadir estilos para el visor
    const styleCSS = `
    .modal-viewer {
        display: none;
        position: fixed;
        z-index: 9999;
        padding-top: 30px;
        left: 0;
        top: 0;
        width: 100%;
        height: 100%;
        overflow: auto;
        background-color: rgba(0,0,0,0.9);
    }
    
    .modal-content-viewer {
        position: relative;
        margin: auto;
        display: block;
        width: 90%;
        height: 90%;
        max-width: 1200px;
        text-align: center;
    }
    
    #viewerImage {
        max-height: 85vh;
        max-width: 100%;
        object-fit: contain;
    }
    
    .close-viewer {
        position: absolute;
        top: 10px;
        right: 25px;
        color: #f1f1f1;
        font-size: 40px;
        font-weight: bold;
        transition: 0.3s;
        z-index: 10000;
        cursor: pointer;
    }
    
    .close-viewer:hover,
    .close-viewer:focus {
        color: #bbb;
        text-decoration: none;
        cursor: pointer;
    }
    
    .navigation {
        position: absolute;
        top: 50%;
        width: 100%;
        margin-top: -30px;
    }
    
    .prev-btn, .next-btn {
        cursor: pointer;
        position: absolute;
        color: white;
        font-weight: bold;
        font-size: 30px;
        transition: 0.6s ease;
        user-select: none;
        -webkit-user-select: none;
        background-color: rgba(0, 0, 0, 0.3);
        padding: 16px;
        border-radius: 50%;
        height: 30px;
        width: 30px;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    
    .next-btn {
        right: 0;
    }
    
    .prev-btn {
        left: 0;
    }
    
    .prev-btn:hover, .next-btn:hover {
        background-color: rgba(0, 0, 0, 0.8);
    }
    
    .image-counter {
        position: absolute;
        bottom: 20px;
        width: 100%;
        text-align: center;
        color: white;
        font-size: 16px;
        padding: 10px;
    }
    `;
    
    // Agregar el HTML y estilos al documento
    function initializeViewer() {
        // Agregar estilos
        const styleElement = document.createElement('style');
        styleElement.textContent = styleCSS;
        document.head.appendChild(styleElement);
        
        // Agregar el modal al body
        const modalElement = document.createElement('div');
        modalElement.innerHTML = modalHTML;
        document.body.appendChild(modalElement.firstElementChild);
        
        console.log('Visor inicializado y agregado al DOM');
    }
    
    // Variables para seguimiento de imágenes
    let currentIndex = 0;
    let galleryImages = [];
    
    // Configurar los eventos del visor
    function setupViewerEvents() {
        const modal = document.getElementById('imageViewer');
        const closeBtn = document.querySelector('.close-viewer');
        const prevBtn = document.querySelector('.prev-btn');
        const nextBtn = document.querySelector('.next-btn');
        
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
        const viewerImage = document.getElementById('viewerImage');
        const currentImageEl = document.getElementById('currentImage');
        
        viewerImage.src = galleryImages[currentIndex].fullUrl;
        currentImageEl.textContent = currentIndex + 1;
        
        console.log(`Mostrando imagen ${currentIndex + 1} de ${galleryImages.length}`);
    }
    
    // Abrir el visor con una imagen específica
    function openImageViewer(imageId) {
        console.log(`Abriendo visor para imagen ID: ${imageId}`);
        
        // Recopilar todas las imágenes de la galería
        const photoCards = document.querySelectorAll('.photo-card');
        console.log(`Encontradas ${photoCards.length} tarjetas de fotos`);
        
        galleryImages = [];
        currentIndex = 0;
        
        photoCards.forEach((card, index) => {
            const id = card.dataset.photoId;
            const img = card.querySelector('img');
            
            if (img) {
                // Obtener URL de imagen completa (reemplazar /thumb/ si existe)
                let fullUrl = img.src;
                if (fullUrl.includes('/thumb/')) {
                    fullUrl = fullUrl.replace('/thumb/', '/');
                }
                
                galleryImages.push({
                    id: id,
                    fullUrl: fullUrl,
                    thumbUrl: img.src
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
        document.getElementById('totalImages').textContent = galleryImages.length;
        
        // Mostrar el visor
        const modal = document.getElementById('imageViewer');
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
            card.addEventListener('click', function(e) {
                // No abrir el visor si se hace clic en los botones de acción
                if (e.target.closest('.actions-bar') || e.target.closest('button') || e.target.closest('a')) {
                    return;
                }
                
                const photoId = this.dataset.photoId;
                console.log(`Clic en tarjeta de foto ${photoId}`);
                openImageViewer(photoId);
            });
        });
    }
    
    // Inicializar todo
    initializeViewer();
    setupViewerEvents();
    setupGalleryClicks();
});