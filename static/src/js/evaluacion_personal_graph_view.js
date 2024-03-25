// static/src/js/evaluacion_personal_graph_view.js
odoo.define('sat.evaluacion_personal_graph_view', function (require) {
    "use strict";

    var AbstractView = require('web.AbstractView');
    var viewRegistry = require('web.view_registry');

    var EvaluacionPersonalGraphView = AbstractView.extend({
        // Define the type of your view
        type: 'evaluacion_personal_graph',

        // Define the JS template to use
        template: 'EvaluacionPersonalGraphView',

        // Define the CSS classes to apply to the view
        className: 'o_evaluacion_personal_graph_view',

        // Define the JS libraries to load
        jsLibs: [
            '/web/static/lib/Chart/Chart.js',
        ],

        // Define the CSS libraries to load
        cssLibs: [
            '/web/static/lib/Chart/Chart.css',
        ],

        // Define the initialization function
        init: function () {
            this._super.apply(this, arguments);
            console.log('EvaluacionPersonalGraphView init');  // Agrega esta línea
            // Initialize your view
        },

        // Define the function to render the view
        render: function () {
            this._super.apply(this, arguments);
            console.log('EvaluacionPersonalGraphView render');  // Agrega esta línea
            // Render your view
        },
    });

    // Register your view
    viewRegistry.add('evaluacion_personal_graph', EvaluacionPersonalGraphView);
});