// sat/static/src/js/gallery.js
document.addEventListener('DOMContentLoaded', function() {
    const gallery = {
        init() {
            this.fileInput = document.getElementById('fileUpload');
            this.syncButton = document.getElementById('syncButton');
            this.photoGrid = document.getElementById('photoGrid');
            this.reparacionId = window.location.pathname.split('/').pop();
            this.bindEvents();
        },

        bindEvents() {
            this.fileInput?.addEventListener('change', (e) => this.handleFileUpload(e));
            this.syncButton?.addEventListener('click', () => this.handleSync());
            
            document.querySelectorAll('.delete-photo').forEach(btn => {
                btn.addEventListener('click', (e) => this.handleDelete(e));
            });
        },

        handleFileUpload(event) {
            const files = event.target.files;
            if (!files.length) return;

            const formData = new FormData();
            Array.from(files).forEach(file => {
                formData.append('files[]', file);
            });

            this.showLoading('Subiendo fotos...');

            fetch(`/gallery/upload/${this.reparacionId}`, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.showSuccess('Éxito', 'Fotos subidas correctamente');
                    window.location.reload();
                } else {
                    throw new Error(data.error || 'Error al subir las fotos');
                }
            })
            .catch(error => {
                this.showError('Error', error.message);
            })
            .finally(() => {
                this.hideLoading();
                this.fileInput.value = '';
            });
        },

        handleDelete(event) {
            const photoId = event.currentTarget.dataset.photoId;
            
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

        handleSync() {
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
                    window.location.reload();
                } else {
                    throw new Error(data.error || 'Error al sincronizar');
                }
            })
            .catch(error => {
                this.showError('Error', error.message);
            })
            .finally(() => {
                this.hideLoading();
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
                    document.querySelector(`[data-photo-id="${photoId}"]`)?.remove();
                    this.showSuccess('Éxito', 'Foto eliminada correctamente');
                } else {
                    throw new Error(data.error || 'Error al eliminar la foto');
                }
            })
            .catch(error => {
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

    gallery.init();
});