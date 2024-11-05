
/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

class GalleryWidget extends Component {
    static template = "reparaciones.GalleryWidget";
    static components = { Dialog };

    setup() {
        this.state = useState({
            selectedPhoto: null,
            isModalOpen: false,
            isLoading: true,
            photos: [],
            selectedPhotos: new Map(),
            selectMode: false,
        });
        
        this.notification = useService("notification");
        this.orm = useService("orm");

        // Cargar fotos al iniciar el componente
        onWillStart(async () => {
            await this.loadPhotos();
        });
    }

    async loadPhotos() {
        try {
            const photos = await this.orm.call(
                'reparaciones.foto',
                'get_photos_preview',
                [[this.props.record.resId]]
            );
            this.state.photos = photos || [];
        } catch (error) {
            console.error('Error al cargar fotos:', error);
            this.notification.add("Error al cargar las fotos", {
                type: 'danger',
            });
        } finally {
            this.state.isLoading = false;
        }
    }

    async uploadPhotos(ev) {
        const files = Array.from(ev.target.files || []);
        if (!files.length) return;

        for (const file of files) {
            try {
                const reader = new FileReader();
                await new Promise((resolve, reject) => {
                    reader.onload = async (e) => {
                        try {
                            await this.orm.create(
                                'reparaciones.foto',
                                [{
                                    nombre_foto: file.name,
                                    foto_binario: e.target.result.split(',')[1],
                                    reparacion_id: this.props.record.resId,
                                }]
                            );
                            resolve();
                        } catch (error) {
                            reject(error);
                        }
                    };
                    reader.onerror = reject;
                    reader.readAsDataURL(file);
                });
            } catch (error) {
                console.error(`Error al subir ${file.name}:`, error);
                this.notification.add(`Error al subir ${file.name}`, {
                    type: 'danger',
                });
            }
        }

        await this.loadPhotos();
        this.notification.add("Fotos subidas exitosamente", {
            type: 'success',
        });
        ev.target.value = '';
    }

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

    async downloadPhoto(photo, ev) {
        ev?.stopPropagation();
        try {
            const result = await this.orm.call(
                'reparaciones.foto',
                'get_download_content',
                [[photo.id]]
            );
            if (result && result.content) {
                // Crear un blob y descargar
                const blob = new Blob([atob(result.content)], { type: result.mimetype });
                const url = window.URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = result.filename;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                window.URL.revokeObjectURL(url);
            }
        } catch (error) {
            console.error('Error al descargar foto:', error);
            this.notification.add("Error al descargar la foto", {
                type: 'danger',
            });
        }
    }

    async downloadSelectedPhotos() {
        if (this.state.selectedPhotos.size === 0) {
            this.notification.add("Selecciona al menos una foto", {
                type: 'warning',
            });
            return;
        }

        try {
            const selectedIds = Array.from(this.state.selectedPhotos.keys());
            const result = await this.orm.call(
                'reparaciones.foto',
                'get_photos_zip',
                [selectedIds]
            );

            if (result && result.content) {
                // Crear un blob y descargar
                const blob = new Blob([atob(result.content)], { type: 'application/zip' });
                const url = window.URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = 'fotos_seleccionadas.zip';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                window.URL.revokeObjectURL(url);
                this.state.selectMode = false;
                this.state.selectedPhotos.clear();
            }
        } catch (error) {
            console.error('Error al descargar fotos:', error);
            this.notification.add("Error al descargar las fotos", {
                type: 'danger',
            });
        }
    }

    openPhotoModal(photo) {
        if (this.state.selectMode) {
            this.togglePhotoSelection(photo);
        } else {
            this.state.selectedPhoto = photo;
            this.state.isModalOpen = true;
        }
    }

    closePhotoModal() {
        this.state.isModalOpen = false;
        this.state.selectedPhoto = null;
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