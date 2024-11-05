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
            photos: [],
            selectedPhotos: new Set(),
            selectMode: false,
            error: null
        });
        this.notification = useService("notification");
        this.orm = useService("orm");

        onMounted(() => this.loadPhotos());
    }

    async loadPhotos() {
        console.log("Cargando fotos para record:", this.props.record.resId);
        try {
            this.state.isLoading = true;
            this.state.error = null;
            
            // Usar el método get_photos_preview del modelo
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
            this.notification.add(this.state.error, {
                type: 'danger',
            });
        } finally {
            this.state.isLoading = false;
        }
    }

    async uploadPhoto(ev) {
        const files = Array.from(ev.target.files || []);
        if (!files.length) return;

        this.state.isLoading = true;
        const uploadPromises = files.map(file => {
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
                        resolve();
                    } catch (error) {
                        console.error('Error al subir foto:', error);
                        reject(error);
                    }
                };
                reader.readAsDataURL(file);
            });
        });

        try {
            await Promise.all(uploadPromises);
            await this.loadPhotos();
            this.notification.add("Fotos subidas exitosamente", {
                type: 'success',
            });
        } catch (error) {
            this.notification.add("Error al subir algunas fotos", {
                type: 'danger',
            });
        } finally {
            this.state.isLoading = false;
        }
    }

    onPhotoClick(photo) {
        console.log("Click en foto:", photo);
        if (!this.state.selectMode) {
            this.openPhotoModal(photo);
        } else {
            this.togglePhotoSelection(photo);
        }
    }

    openPhotoModal(photo) {
        console.log("Abriendo modal con foto:", photo);
        this.state.selectedPhoto = photo;
        this.state.isModalOpen = true;
    }

    closePhotoModal() {
        this.state.isModalOpen = false;
        this.state.selectedPhoto = null;
    }

    toggleSelectMode(ev) {
        this.state.selectMode = !this.state.selectMode;
        this.state.selectedPhotos.clear();
    }

    togglePhotoSelection(photo) {
        if (this.state.selectedPhotos.has(photo.id)) {
            this.state.selectedPhotos.delete(photo.id);
        } else {
            this.state.selectedPhotos.add(photo.id);
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
            const zipUrl = await this.orm.call(
                'reparaciones.foto',
                'get_photos_zip',
                [[...this.state.selectedPhotos]]
            );
            if (zipUrl) {
                window.open(zipUrl, '_blank');
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

    async downloadPhoto(photo, ev) {
        ev?.stopPropagation();
        if (photo?.url_foto) {
            try {
                const url = await this.orm.call(
                    'reparaciones.foto',
                    'get_download_url',
                    [[photo.id]]
                );
                if (url) {
                    window.open(url, '_blank');
                } else {
                    this.notification.add("No se pudo obtener la URL de descarga", {
                        type: 'warning',
                    });
                }
            } catch (error) {
                console.error('Error al obtener URL de descarga:', error);
                this.notification.add("Error al descargar la foto", {
                    type: 'danger',
                });
            }
        }
    }

    get hasPhotos() {
        return this.state.photos.length > 0;
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