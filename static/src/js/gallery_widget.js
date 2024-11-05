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

        // Bindeamos los métodos
        this.onPhotoClick = this.onPhotoClick.bind(this);
        this.openPhotoModal = this.openPhotoModal.bind(this);
        this.closePhotoModal = this.closePhotoModal.bind(this);
        this.downloadPhoto = this.downloadPhoto.bind(this);
        this.toggleSelectMode = this.toggleSelectMode.bind(this);

        onMounted(() => this.loadPhotos());
    }

    async loadPhotos() {
        console.log("Cargando fotos para record:", this.props.record.resId);
        try {
            this.state.isLoading = true;
            this.state.error = null;
            const result = await this.orm.call(
                'reparaciones.foto',
                'search_read',
                [[['reparacion_id', '=', this.props.record.resId]]],
                {
                    fields: ['id', 'nombre_foto', 'foto_binario']
                }
            );
            console.log("Fotos obtenidas:", result);
            this.state.photos = result.map(photo => ({
                ...photo,
                imageUrl: `/web/content/reparaciones.foto/${photo.id}/foto_binario`,
                downloadUrl: `/web/content/reparaciones.foto/${photo.id}/foto_binario?download=true`
            }));
        } catch (error) {
            console.error('Error al cargar fotos:', error);
            this.state.error = "Error al cargar las fotos";
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
        ev?.preventDefault();
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

    downloadPhoto(photo, ev) {
        ev?.stopPropagation();
        ev?.preventDefault();
        if (photo?.downloadUrl) {
            window.open(photo.downloadUrl, '_blank');
        }
    }

    async uploadPhoto(ev) {
        const files = Array.from(ev.target.files || []);
        if (!files.length) return;

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