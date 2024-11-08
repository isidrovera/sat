// sat/static/src/js/gallery.js
document.addEventListener('DOMContentLoaded', function() {
    const gallery = {
        init: function() {
            this.bindEvents();
        },

        bindEvents: function() {
            document.getElementById('fileUpload')?.addEventListener('change', this.handleFileUpload.bind(this));
            document.querySelectorAll('.delete-photo').forEach(button => {
                button.addEventListener('click', this.handleDelete.bind(this));
            });
        },

        handleFileUpload: function(event) {
            const files = event.target.files;
            if (files.length > 0) {
                this.uploadFiles(files);
            }
        },

        handleDelete: function(event) {
            event.preventDefault();
            const photoId = event.target.closest('.delete-photo').dataset.photoId;
            if (confirm('¿Está seguro de eliminar esta foto?')) {
                this.deletePhoto(photoId);
            }
        },

        uploadFiles: function(files) {
            const formData = new FormData();
            const progressBar = document.getElementById('uploadProgress');
            const progressBarInner = progressBar.querySelector('.progress-bar');
            const reparacionId = document.querySelector('.gallery-container').dataset.reparacionId;

            Array.from(files).forEach(file => {
                formData.append('files[]', file);
            });

            progressBar.classList.remove('d-none');

            fetch(`/gallery/upload/${reparacionId}`, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    window.location.reload();
                } else {
                    this.showError(data.error || 'Error al subir las fotos');
                }
            })
            .catch(error => {
                this.showError('Error al subir las fotos: ' + error.message);
            })
            .finally(() => {
                progressBar.classList.add('d-none');
                progressBarInner.style.width = '0%';
            });
        },

        deletePhoto: function(photoId) {
            fetch(`/gallery/delete/${photoId}`, {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const photoElement = document.querySelector(`[data-photo-id="${photoId}"]`);
                    photoElement?.remove();
                    this.showSuccess('Foto eliminada correctamente');
                } else {
                    this.showError(data.error || 'Error al eliminar la foto');
                }
            })
            .catch(error => {
                this.showError('Error al eliminar la foto: ' + error.message);
            });
        },

        showError: function(message) {
            // Implementa tu propio sistema de notificaciones o usa alert
            alert(message);
        },

        showSuccess: function(message) {
            // Implementa tu propio sistema de notificaciones o usa alert
            alert(message);
        }
    };

    gallery.init();
});