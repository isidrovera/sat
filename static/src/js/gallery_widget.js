
/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onMounted } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

class GalleryWidget extends Component {
    static template = "reparaciones.GalleryWidget";
    static components = { Dialog };

    setup() {
        this.state = useState({
            selectedPhoto: null,
            isModalOpen: false,
            isLoading: true,
            isUploading: false,
            photos: [],
            selectedPhotos: new Map(),
            selectMode: false,
            error: null,
            uploadProgress: 0,
            totalFiles: 0,
            processedFiles: 0
        });
        
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.dialogService = useService("dialog");
    }

    // Carga inicial de fotos
    async loadPhotos() {
        console.log("Cargando fotos para record:", this.props.record.resId);
        try {
            this.state.isLoading = true;
            this.state.error = null;
            
            const photos = await this.orm.call(
                'reparaciones.foto',
                'get_photos_preview',
                [[this.props.record.resId]]
            );
            
            console.log("Fotos obtenidas:", photos);
            this.state.photos = photos || [];
        } catch (error) {
            console.error('Error al cargar fotos:', error);
            this.state.error = "Error al cargar las fotos";
            this.notification.add(this.state.error, { type: 'danger' });
        } finally {
            this.state.isLoading = false;
        }
    }

    // Subida de fotos
    async uploadPhotos(ev) {
        const files = Array.from(ev.target.files || []);
        if (!files.length) return;

        this.state.isUploading = true;
        this.state.totalFiles = files.length;
        this.state.processedFiles = 0;
        this.state.uploadProgress = 0;

        try {
            const uploadPromises = files.map((file, index) => {
                return new Promise((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onload = async (e) => {
                        try {
                            const base64Data = e.target.result.split(',')[1];
                            await this.orm.create(
                                'reparaciones.foto',
                                [{
                                    nombre_foto: file.name,
                                    foto_binario: base64Data,
                                    reparacion_id: this.props.record.resId,
                                }]
                            );
                            this.state.processedFiles++;
                            this.state.uploadProgress = (this.state.processedFiles / this.state.totalFiles) * 100;
                            resolve();
                        } catch (error) {
                            console.error(`Error al subir ${file.name}:`, error);
                            reject(error);
                        }
                    };
                    reader.onerror = reject;
                    reader.readAsDataURL(file);
                });
            });

            await Promise.allSettled(uploadPromises);
            await this.loadPhotos();

            const successCount = this.state.processedFiles;
            const failCount = files.length - successCount;

            if (failCount > 0) {
                this.notification.add(
                    `Se subieron ${successCount} fotos. ${failCount} fotos fallaron.`,
                    { type: 'warning' }
                );
            } else {
                this.notification.add(
                    `Se subieron ${successCount} fotos exitosamente`,
                    { type: 'success' }
                );
            }
        } catch (error) {
            console.error('Error en la subida masiva:', error);
            this.notification.add("Error al subir las fotos", { type: 'danger' });
        } finally {
            this.state.isUploading = false;
            this.state.uploadProgress = 0;
            this.state.totalFiles = 0;
            this.state.processedFiles = 0;
            ev.target.value = ''; // Resetear input para permitir subir los mismos archivos
        }
    }

    // Manejo de selección
    toggleSelectMode() {
        this.state.selectMode = !this.state.selectMode;
        this.state.selectedPhotos.clear();
    }

    togglePhotoSelection(photo) {
        if (this.state.selectedPhotos.has(photo.id)) {
            this.state.selectedPhotos.delete(photo.id);
        } else {
            this.state.selectedPhotos.set(photo.id, photo);
        }
    }

    selectAll() {
        if (this.state.selectedPhotos.size === this.state.photos.length) {
            this.state.selectedPhotos.clear();
        } else {
            this.state.photos.forEach(photo => {
                this.state.selectedPhotos.set(photo.id, photo);
            });
        }
    }

    isPhotoSelected(photoId) {
        return this.state.selectedPhotos.has(photoId);
    }

    get selectedCount() {
        return this.state.selectedPhotos.size;
    }

    // Manejo de descargas
    async downloadSelectedPhotos() {
        if (this.selectedCount === 0) {
            this.notification.add("Selecciona al menos una foto", {
                type: 'warning',
            });
            return;
        }

        try {
            const selectedIds = Array.from(this.state.selectedPhotos.keys());
            const result = await this.orm.call(
                'reparaciones.foto',
                'download_multiple',
                [selectedIds]
            );

            if (result && result.url) {
                window.location.href = result.url;
                this.toggleSelectMode();
            } else {
                throw new Error("No se pudo crear el archivo ZIP");
            }
        } catch (error) {
            console.error('Error al descargar fotos:', error);
            this.notification.add("Error al descargar las fotos", {
                type: 'danger',
            });
        }
    }

    async downloadPhoto(photo, ev) {
        ev?.stopPropagation();
        if (!photo?.download_url) return;

        try {
            const url = await this.orm.call(
                'reparaciones.foto',
                'get_download_url',
                [[photo.id]]
            );
            
            if (url) {
                window.open(url, '_blank');
            } else {
                throw new Error("No se pudo obtener la URL de descarga");
            }
        } catch (error) {
            console.error('Error al descargar foto:', error);
            this.notification.add("Error al descargar la foto", {
                type: 'danger',
            });
        }
    }

    // Manejo del modal de vista previa
    openPhotoModal(photo) {
        if (this.state.selectMode) {
            this.togglePhotoSelection(photo);
        } else {
            this.state.selectedPhoto = { ...photo }; // Clonar el objeto
            this.state.isModalOpen = true;
        }
    }

    closePhotoModal() {
        this.state.selectedPhoto = null;
        this.state.isModalOpen = false;
    }

    // Manejo de eliminación
    async deleteSelectedPhotos() {
        if (this.selectedCount === 0) return;

        const confirmed = await new Promise(resolve => {
            this.dialogService.add(Dialog, {
                title: "Confirmar Eliminación",
                body: `¿Estás seguro de que deseas eliminar ${this.selectedCount} foto(s)?`,
                confirmLabel: "Eliminar",
                cancelLabel: "Cancelar",
                confirm: () => resolve(true),
                cancel: () => resolve(false),
            });
        });

        if (confirmed) {
            try {
                const selectedIds = Array.from(this.state.selectedPhotos.keys());
                await this.orm.unlink('reparaciones.foto', selectedIds);
                await this.loadPhotos();
                this.toggleSelectMode();
                this.notification.add(
                    `${selectedIds.length} foto(s) eliminada(s) correctamente`,
                    { type: 'success' }
                );
            } catch (error) {
                console.error('Error al eliminar fotos:', error);
                this.notification.add("Error al eliminar las fotos", {
                    type: 'danger',
                });
            }
        }
    }

    // Utilidades
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
}

export const galleryWidget = {
    component: GalleryWidget,
    supportedTypes: ['one2many', 'many2many'],
    extractProps: ({ attrs, field }) => ({
        name: field.name,
        record: field.record,
        readonly: attrs.readonly === "1" || attrs.readonly === true,
    }),
};

registry.category("fields").add("gallery_widget", galleryWidget);