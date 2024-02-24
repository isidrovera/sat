odoo.define('sat.sat_list_controller', function (require) {
    "use strict";
    
    var ListController = require('web.ListController');
    
    var SatListController = ListController.include({
        renderButtons: function($node) {
            this._super.apply(this, arguments);
            if (this.$buttons) {
                var btn = this.$buttons.find('.btn-secondary');
                btn.on('click', this.proxy('miFuncionPersonalizada'));
            }
        },
        miFuncionPersonalizada: function() {
            // Aquí pones la lógica para abrir un formulario, acción o wizard
        },
    });
    
    return SatListController;
    
    });
    