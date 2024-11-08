// sat/static/src/js/gallery.js
document.addEventListener('DOMContentLoaded', function() {
    const gallery = {
        init() {
            console.log('Iniciando galería...');
            // Obtener elementos del DOM
            this.fileInput = document.getElementById('fileUpload');
            this.progressBar = document.querySelector('.upload-progress');
            this.photoGrid = document.querySelector('#photoGrid');
            this.syncButton = document.getElementById('syncButton');
            
            // Obtener ID de reparación de la URL
            this.reparacionId = window.location.pathname.split('/').pop();
            console.log('ID de reparación:', this.reparacionId);

            if (!this.fileInput) {
                console.error('No se encontró el input de archivo');
                return;
            }
            
            // Vincular eventos
            this.bindEvents();
        },

        bindEvents() {
            console.log('Vinculando eventos...');
            // Evento de subida de archivos
            if (this.fileInput) {
                this.fileInput.addEventListener('change', (e) => this.handleFileUpload(e));
                console.log('Evento de subida de archivos vinculado');
            }

            // Evento de sincronización
            if (this.syncButton) {
                this.syncButton.addEventListener('click', () => this.handleSync());
                console.log('Evento de sincronización vinculado');
            }

            // Eventos de eliminación
            const deleteButtons = document.querySelectorAll('.delete-photo');
            deleteButtons.forEach(btn => {
                btn.addEventListener('click', (e) => this.handleDelete(e));
            });
            console.log('Eventos de eliminación vinculados:', deleteButtons.length);
        },

        handleFileUpload(event) {
            console.log('Iniciando subida de archivos...');
            const files = event.target.files;
            if (!files || !files.length) {
                console.log('No se seleccionaron archivos');
                return;
            }

            // Crear FormData
            const formData = new FormData();
            Array.from(files).forEach(file => {
                if (this.validateFile(file)) {
                    formData.append('files[]', file);
                    console.log('Archivo agregado:', file.name);
                } else {
                    console.warn('Archivo no válido:', file.name);
                }
            });

            // Si no hay archivos válidos, salir
            if (!formData.has('files[]')) {
                this.showError('No hay archivos válidos', 'Por favor seleccione imágenes válidas');
                return;
            }

            // Mostrar progreso
            this.showLoading('Subiendo fotos...');

            // Realizar la subida
            fetch(`/gallery/upload/${this.reparacionId}`, {
                method: 'POST',
                body: formData
            })
            .then(response => {
                console.log('Respuesta del servidor:', response);
                return response.json();
            })
            .then(data => {
                console.log('Datos de respuesta:', data);
                if (data.success) {
                    this.showSuccess('Éxito', 'Fotos subidas correctamente');
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    throw new Error(data.error || 'Error al subir las fotos');
                }
            })
            .catch(error => {
                console.error('Error en subida:', error);
                this.showError('Error', error.message);
            })
            .finally(() => {
                if (this.fileInput) this.fileInput.value = '';
                this.hideLoading();
            });
        },

        validateFile(file) {
            // Validar tipo de archivo
            if (!file.type.startsWith('image/')) {
                this.showError('Archivo no válido', `${file.name} no es una imagen`);
                return false;
            }

            // Validar tamaño (10MB máximo)
            const maxSize = 10 * 1024 * 1024;
            if (file.size > maxSize) {
                this.showError('Archivo muy grande', `${file.name} excede el tamaño máximo de 10MB`);
                return false;
            }

            return true;
        },

        handleSync() {
            console.log('Iniciando sincronización...');
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
                    this.deletePhoto(photoId);
                }
            });
        },

        deletePhoto(photoId) {
            this.showLoading('Eliminando foto...');

            fetch(`/gallery/delete/${photoId}`, {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const element = document.querySelector(`[data-photo-id="${photoId}"]`);
                    if (element) {
                        element.remove();
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
            Swal.fire({
                title: message,
                allowOutsideClick: false,
                didOpen: () => {
                    Swal.showLoading();
                }
            });
        },

        hideLoading() {
            Swal.close();
        },

        showError(title, message) {
            Swal.fire({
                icon: 'error',
                title: title,
                text: message,
                confirmButtonText: 'Aceptar'
            });
        },

        showSuccess(title, message) {
            Swal.fire({
                icon: 'success',
                title: title,
                text: message,
                confirmButtonText: 'Aceptar'
            });
        }
    };

    // Inicializar galería
    gallery.init();
});