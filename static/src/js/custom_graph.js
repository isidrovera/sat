odoo.define('sat.custom_graph', function (require) {
    'use strict';
    
    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    
    var CustomGraph = AbstractAction.extend({
        contentTemplate: 'CustomGraphView',
    
        start: function () {
            this._super.apply(this, arguments);
            // Aquí podrías inicializar tu gráfico o realizar otras operaciones de configuración
            console.log("Mi vista de gráfico personalizada se está inicializando");
        },
    });
    
    core.action_registry.add('custom_graph', CustomGraph);
    
    });
    