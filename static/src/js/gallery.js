// sat/static/src/js/gallery.js
document.addEventListener('DOMContentLoaded', function() {
    const gallery = {
        init() {
            this.fileInput = document.getElementById('fileUpload');
            this.progressBar = document.querySelector('.upload-progress');
            this.bindEvents();
        },

        bindEvents() {
            this.fileInput?.addEventListener('change', (e) => this.handleFileUpload(e));
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

            this.progressBar.style.display = 'block';
            const reparacionId = window.location.pathname.split('/').pop();

            fetch(`/gallery/upload/${reparacionId}`, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    Swal.fire({
                        icon: 'success',
                        title: 'Éxito',
                        text: 'Fotos subidas correctamente'
                    }).then(() => {
                        window.location.reload();
                    });
                } else {
                    throw new Error(data.error || 'Error al subir las fotos');
                }
            })
            .catch(error => {
                Swal.fire({
                    icon: 'error',
                    title: 'Error',
                    text: error.message
                });
            })
            .finally(() => {
                this.progressBar.style.display = 'none';
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
                confirmButtonText: 'Sí, eliminar',
                cancelButtonText: 'Cancelar'
            }).then((result) => {
                if (result.isConfirmed) {
                    this.deletePhoto(photoId);
                }
            });
        },

        deletePhoto(photoId) {
            fetch(`/gallery/delete/${photoId}`, {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const photoCard = document.querySelector(`[data-photo-id="${photoId}"]`);
                    photoCard?.remove();
                    Swal.fire({
                        icon: 'success',
                        title: 'Éxito',
                        text: 'Foto eliminada correctamente'
                    });
                } else {
                    throw new Error(data.error || 'Error al eliminar la foto');
                }
            })
            .catch(error => {
                Swal.fire({
                    icon: 'error',
                    title: 'Error',
                    text: error.message
                });
            });
        }
    };

    gallery.init();
});