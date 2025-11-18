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
            error: null,
            retryCount: 0,
            isUploading: false,
            uploadProgress: {
                total: 0,
                current: 0,
                percentage: 0
            }
        });
        
        this.notification = useService("notification");
        this.orm = useService("orm");

        // Bindeamos los métodos
        this.uploadPhotos = this.uploadPhotos.bind(this);
        this.downloadPhoto = this.downloadPhoto.bind(this);
        this.toggleSelectMode = this.toggleSelectMode.bind(this);
        this.togglePhotoSelection = this.togglePhotoSelection.bind(this);
        this.openPhotoModal = this.openPhotoModal.bind(this);
        this.closePhotoModal = this.closePhotoModal.bind(this);
        this.downloadSelectedPhotos = this.downloadSelectedPhotos.bind(this);
        this.loadPhotos = this.loadPhotos.bind(this);
        this.selectAll = this.selectAll.bind(this);

        onWillStart(async () => {
            await this.loadPhotos(true);
        });
    }

    async loadPhotos(isInitial = false) {
    try {
        // Verificar si el componente fue destruido antes de comenzar
        if (this.__owl__.status === 5) { // 5 = DESTROYED
            return;
        }

        this.state.isLoading = true;
        this.state.error = null;

        const photos = await this.orm.call(
            'reparaciones.foto',
            'get_photos_preview',
            [[this.props.record.resId]],
            {
                context: {
                    ...this.env.context,
                    retry_count: this.state.retryCount
                }
            }
        );

        // Verificar nuevamente después de la operación asíncrona
        if (this.__owl__.status === 5) {
            return;
        }

        if (photos && photos.length > 0) {
            this.state.photos = photos;
            this.state.retryCount = 0;
        } else if (isInitial && this.state.retryCount < 3) {
            // Reintentar la carga inicial hasta 3 veces
            this.state.retryCount++;
            await new Promise(resolve => setTimeout(resolve, 1000));
            await this.loadPhotos(true);
        }
    } catch (error) {
        // Ignorar errores si el componente fue destruido
        if (this.__owl__.status === 5 || error.message === 'Component is destroyed') {
            return;
        }
        
        console.error('Error al cargar fotos:', error);
        this.state.error = "Error al cargar las fotos";
        if (isInitial && this.state.retryCount < 3) {
            this.state.retryCount++;
            await new Promise(resolve => setTimeout(resolve, 1000));
            await this.loadPhotos(true);
        }
    } finally {
        // Solo actualizar estado si el componente sigue vivo
        if (this.__owl__.status !== 5) {
            this.state.isLoading = false;
        }
    }
}
    async uploadPhotos(ev) {
        const files = Array.from(ev.target.files || []);
        if (!files.length) return;

        this.state.isUploading = true;
        this.state.uploadProgress = {
            total: files.length,
            current: 0,
            percentage: 0
        };

        try {
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
                                this.state.uploadProgress.current++;
                                this.state.uploadProgress.percentage = 
                                    (this.state.uploadProgress.current / this.state.uploadProgress.total) * 100;
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
        } catch (error) {
            console.error('Error en la subida de fotos:', error);
            this.notification.add("Error al subir las fotos", {
                type: 'danger',
            });
        } finally {
            this.state.isUploading = false;
            this.state.uploadProgress = {
                total: 0,
                current: 0,
                percentage: 0
            };
            ev.target.value = ''; // Limpiar input
        }
    }

    async downloadPhoto(photo, ev) {
        ev?.stopPropagation();
        try {
            if (!photo?.id) {
                throw new Error("Foto no válida");
            }

            const result = await this.orm.call(
                'reparaciones.foto',
                'get_download_link',
                [[photo.id]]
            );
            
            if (result && result.content) {
                // Crear blob y forzar descarga
                const blob = new Blob(
                    [Uint8Array.from(atob(result.content), c => c.charCodeAt(0))],
                    { type: result.mimetype }
                );
                const url = window.URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = result.filename;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                window.URL.revokeObjectURL(url);
            } else {
                throw new Error("No se pudo obtener el contenido de la foto");
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
            console.log("No se seleccionaron fotos para descargar.");
            this.notification.add("Selecciona al menos una foto", {
                type: 'warning',
            });
            return;
        }
    
        // Obtener los IDs de las fotos seleccionadas
        const selectedIds = Array.from(this.state.selectedPhotos.keys());
        console.log("IDs de fotos seleccionadas para el ZIP:", selectedIds);
    
        try {
            console.log("Iniciando llamada al backend para obtener el ZIP...");
            
            // Llamada al backend
            const result = await this.orm.call(
                'reparaciones.foto',
                'get_photos_zip',
                [selectedIds]
            );
    
            // Verificar respuesta del backend
            console.log("Respuesta del backend para ZIP:", result);
    
            if (result && result.content) {
                console.log("Contenido del ZIP recibido, iniciando descarga...");
                
                // Crear blob y forzar descarga
                const blob = new Blob(
                    [Uint8Array.from(atob(result.content), c => c.charCodeAt(0))],
                    { type: result.mimetype }
                );
                const url = window.URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = result.filename;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                window.URL.revokeObjectURL(url);
                
                console.log("Descarga completada. Limpiando selección...");
                this.toggleSelectMode();
                this.notification.add("Fotos descargadas exitosamente", {
                    type: 'success',
                });
            } else {
                console.error("No se pudo crear el archivo ZIP. Respuesta del backend:", result);
                throw new Error("No se pudo crear el archivo ZIP");
            }
        } catch (error) {
            console.error("Error al descargar fotos:", error);
            this.notification.add("Error al descargar las fotos", {
                type: 'danger',
            });
        }
    }
    
    

    toggleSelectMode() {
        this.state.selectMode = !this.state.selectMode;
        this.state.selectedPhotos.clear();
    }

    togglePhotoSelection(photo, ev) {
        ev?.stopPropagation();
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

    openPhotoModal(photo) {
        if (this.state.selectMode) {
            this.togglePhotoSelection(photo);
        } else if (photo) {
            this.state.selectedPhoto = { ...photo };
            this.state.isModalOpen = true;
        }
    }

    closePhotoModal() {
        this.state.isModalOpen = false;
        this.state.selectedPhoto = null;
    }

    get hasPhotos() {
        return this.state.photos.length > 0;
    }

    get selectedCount() {
        return this.state.selectedPhotos.size;
    }

    get isAllSelected() {
        return this.state.selectedPhotos.size === this.state.photos.length;
    }

    formatFileSize(bytes) {
        if (!bytes) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
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