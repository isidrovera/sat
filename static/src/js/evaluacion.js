odoo.define('sat.ColorProgressBar', function(require) {
    "use strict";
    
    var ProgressBar = require('web.ProgressBar');
    var field_registry = require('web.field_registry');
    
    var ColorProgressBar = ProgressBar.extend({
    
        // Función para actualizar el color de la barra de progreso
        _render: function () {
            this._super.apply(this, arguments); // Llamada al método original
            if (this.recordData.is_red) {
                this.$('.progress-bar').css('background-color', '#ff0000'); // Rojo
            } else if (this.recordData.is_yellow) {
                this.$('.progress-bar').css('background-color', '#ffff00'); // Amarillo
            } else if (this.recordData.is_green) {
                this.$('.progress-bar').css('background-color', '#00ff00'); // Verde
            }
        },
    });
    
    field_registry.add('color_progressbar', ColorProgressBar);
    
    return ColorProgressBar;
    });
    