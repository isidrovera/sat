// sat/static/src/js/gallery.js
document.addEventListener('DOMContentLoaded', function() {
    const gallery = {
        init() {
            console.log('Iniciando galería...');
            this.fileInput = document.getElementById('fileUpload');
            this.syncButton = document.getElementById('syncButton');
            this.photoGrid = document.getElementById('photoGrid');
            this.reparacionId = window.location.pathname.split('/').pop();
            console.log('ID de reparación:', this.reparacionId);
            this.bindEvents();
        },

        bindEvents() {
            console.log('Vinculando eventos...');
            if (this.fileInput) {
                this.fileInput.addEventListener('change', (e) => this.handleFileUpload(e));
                console.log('Evento de subida de archivos vinculado');
            }

            if (this.syncButton) {
                this.syncButton.addEventListener('click', () => this.handleSync());
                console.log('Evento de sincronización vinculado');
            }
            
            document.querySelectorAll('.delete-photo').forEach(btn => {
                btn.addEventListener('click', (e) => this.handleDelete(e));
            });
            console.log('Eventos de eliminación vinculados');
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
            .then(response => {
                console.log('Respuesta recibida:', response);
                return response.json();
            })
            .then(data => {
                console.log('Datos de sincronización:', data);
                if (data.success) {
                    this.showSuccess('Sincronización completada', data.message);
                    console.log('Recargando página...');
                    window.location.reload();
                } else {
                    throw new Error(data.error || 'Error al sincronizar');
                }
            })
            .catch(error => {
                console.error('Error en sincronización:', error);
                this.showError('Error', error.message);
            })
            .finally(() => {
                console.log('Finalizando sincronización');
                this.hideLoading();
            });
        },

        handleFileUpload(event) {
            console.log('Iniciando subida de archivos...');
            const files = event.target.files;
            if (!files.length) {
                console.log('No se seleccionaron archivos');
                return;
            }

            console.log('Archivos seleccionados:', files.length);
            const formData = new FormData();
            Array.from(files).forEach(file => {
                formData.append('files[]', file);
                console.log('Archivo agregado:', file.name);
            });

            this.showLoading('Subiendo fotos...');

            fetch(`/gallery/upload/${this.reparacionId}`, {
                method: 'POST',
                body: formData
            })
            .then(response => {
                console.log('Respuesta de subida:', response);
                return response.json();
            })
            .then(data => {
                console.log('Datos de respuesta:', data);
                if (data.success) {
                    this.showSuccess('Éxito', 'Fotos subidas correctamente');
                    console.log('Recargando página después de subida');
                    window.location.reload();
                } else {
                    throw new Error(data.error || 'Error al subir las fotos');
                }
            })
            .catch(error => {
                console.error('Error en subida:', error);
                this.showError('Error', error.message);
            })
            .finally(() => {
                console.log('Finalizando subida');
                this.hideLoading();
                this.fileInput.value = '';
            });
        },

        handleDelete(event) {
            const photoId = event.currentTarget.dataset.photoId;
            console.log('Iniciando eliminación de foto:', photoId);
            
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
                    console.log('Confirmada eliminación de foto:', photoId);
                    this.deletePhoto(photoId);
                } else {
                    console.log('Cancelada eliminación de foto:', photoId);
                }
            });
        },

        deletePhoto(photoId) {
            console.log('Ejecutando eliminación de foto:', photoId);
            this.showLoading('Eliminando foto...');

            fetch(`/gallery/delete/${photoId}`, {
                method: 'POST'
            })
            .then(response => {
                console.log('Respuesta de eliminación:', response);
                return response.json();
            })
            .then(data => {
                console.log('Datos de eliminación:', data);
                if (data.success) {
                    const element = document.querySelector(`[data-photo-id="${photoId}"]`);
                    if (element) {
                        element.remove();
                        console.log('Elemento eliminado del DOM');
                    }
                    this.showSuccess('Éxito', 'Foto eliminada correctamente');
                } else {
                    throw new Error(data.error || 'Error al eliminar la foto');
                }
            })
            .catch(error => {
                console.error('Error en eliminación:', error);
                this.showError('Error', error.message);
            })
            .finally(() => {
                console.log('Finalizando eliminación');
                this.hideLoading();
            });
        },

        showLoading(message = 'Cargando...') {
            console.log('Mostrando loading:', message);
            Swal.fire({
                title: message,
                allowOutsideClick: false,
                didOpen: () => {
                    Swal.showLoading();
                }
            });
        },

        hideLoading() {
            console.log('Ocultando loading');
            Swal.close();
        },

        showError(title, message) {
            console.error('Mostrando error:', title, message);
            Swal.fire({
                icon: 'error',
                title: title,
                text: message,
                confirmButtonText: 'Aceptar'
            });
        },

        showSuccess(title, message) {
            console.log('Mostrando éxito:', title, message);
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