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
        this.rpc = useService("rpc");

        onMounted(() => this.loadPhotos());
    }

    async loadPhotos() {
        console.log("Iniciando carga de fotos");
        try {
            this.state.isLoading = true;
            const photos = await this.orm.call(
                'reparaciones.foto',
                'get_photos_preview',
                [[this.props.record.resId]]
            );
            console.log("Fotos obtenidas:", photos);
            this.state.photos = photos;
        } catch (error) {
            console.error('Error al cargar fotos:', error);
            this.state.error = error.message || "Error al cargar las fotos";
            this.notification.add(this.state.error, {
                type: 'danger',
            });
        } finally {
            this.state.isLoading = false;
        }
    }

    toggleSelectMode() {
        console.log("Cambiando modo de selección");
        this.state.selectMode = !this.state.selectMode;
        if (!this.state.selectMode) {
            this.state.selectedPhotos.clear();
        }
    }

    async uploadPhoto(ev) {
        console.log("Iniciando subida de foto");
        const file = ev.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = async (e) => {
            const base64Data = e.target.result.split(',')[1];
            try {
                console.log("Subiendo archivo:", file.name);
                await this.orm.create(
                    'reparaciones.foto',
                    [{
                        nombre_foto: file.name,
                        foto_binario: base64Data,
                        reparacion_id: this.props.record.resId,
                    }]
                );
                await this.loadPhotos();
                this.notification.add("Foto subida exitosamente", {
                    type: 'success',
                });
            } catch (error) {
                console.error('Error al subir foto:', error);
                this.notification.add("Error al subir la foto", {
                    type: 'danger',
                });
            }
        };
        reader.readAsDataURL(file);
    }

    openPhotoModal(photo) {
        console.log("Abriendo modal para foto:", photo);
        if (photo && photo.url_foto) {
            this.state.selectedPhoto = photo;
            this.state.isModalOpen = true;
        } else {
            this.notification.add("No se puede mostrar la foto", {
                type: 'warning',
            });
        }
    }

    get hasPhotos() {
        return this.state.photos && this.state.photos.length > 0;
    }

    get debugInfo() {
        return {
            totalPhotos: this.state.photos.length,
            selectedCount: this.state.selectedPhotos.size,
            error: this.state.error,
            loading: this.state.isLoading,
        };
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