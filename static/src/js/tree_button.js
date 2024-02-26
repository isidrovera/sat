odoo.define('sat.tree_button', function (require) {
    "use strict";

    var ListController = require('web.ListController');

    var MyListController = ListController.include({
        renderButtons: function ($node) {
            this._super.apply(this, arguments); // Llama a la función original para conservar los botones existentes
            var self = this;
            if (this.$buttons) { // Asegúrate de que los botones están renderizados
                var myButton = $("<button type='button' class='btn btn-secondary'>Mi Botón</button>")
                    .click(this.proxy('miMetodoPersonalizado'));
                this.$buttons.prepend(myButton); // Agregar el botón al DOM
                if ($node) {
                    $node.append(this.$buttons); // Agregar los botones al nodo especificado
                }
            }
        },
        miMetodoPersonalizado: function () {
            // Tu lógica de negocio aquí, por ejemplo abrir un wizard
            alert("¡Haz clic en mi botón personalizado!");
        },
    });

    return MyListController;
});
