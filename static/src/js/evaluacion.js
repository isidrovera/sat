odoo.define('sat.NombreProgressBarWidget', function (require) {
    'use strict';

    var fieldRegistry = require('web.field_registry');
    var ProgressBar = require('web.ProgressBar');

    var NombreProgressBarWidget = ProgressBar.extend({
        _render: function () {
            this._super.apply(this, arguments); // Llamada al método original
            // Aplica una lógica para añadir clases basadas en el valor
            if (this.value < 0.5) {
                this.$('.progress-bar').addClass('bg-danger');
            } else if (this.value < 0.8) {
                this.$('.progress-bar').addClass('bg-warning');
            } else {
                this.$('.progress-bar').addClass('bg-success');
            }
        },
    });

    fieldRegistry.add('nombre_progressbar', NombreProgressBarWidget);

    return NombreProgressBarWidget;
});
