odoo.define('reparaciones.foto_galeria', function (require) {
    "use strict";
    var FormController = require('web.FormController');

    FormController.include({
        events: _.extend({}, FormController.prototype.events, {
            'click .gallery-item button': '_onSharePhoto',
        }),

        _onSharePhoto: function (event) {
            var fotoUrl = $(event.currentTarget).siblings('img').attr('src');
            alert('Compartiendo foto: ' + fotoUrl);  // Puedes personalizar esta lógica
        },
    });
});
