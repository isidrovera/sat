/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

class PhotoGallery extends Component {
    setup() {
        this.orm = useService("orm");
        this.dialogService = useService("dialog");
        this.photos = this.props.photos || [];
    }

    async addPhoto() {
        this.dialogService.add({
            title: "Agregar Foto",
            body: "Funcionalidad para capturar y agregar una foto",
        });
    }
}

PhotoGallery.template = "your_module_name.PhotoGalleryTemplate";
PhotoGallery.props = {
    photos: { type: Array },
};

registry.category("fields").add("photo_gallery", PhotoGallery);
