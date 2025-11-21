/** @odoo-module **/

odoo.define('sat.SatListDashboard', function (require) {
    "use strict";

    const ListController = require('web.ListController');
    const ListView = require('web.ListView');
    const viewRegistry = require('web.view_registry');
    const core = require('web.core');
    const qweb = core.qweb;

    const SatListController = ListController.extend({
        /**
         * Después de cada actualización del listado, dibujamos el dashboard.
         */
        _update: function () {
            const res = this._super.apply(this, arguments);
            this._renderSatDashboard();
            return res;
        },

        /**
         * Llamada RPC al método Python y render del template QWeb.
         */
        _renderSatDashboard: function () {
            const self = this;
            const state = this.model.get(this.handle);
            const domain = state && state.domain ? state.domain : [];

            this._rpc({
                model: 'sat.sat',
                method: 'get_sat_dashboard_values',   // método que pusimos en el modelo
                args: [],
                kwargs: { domain: domain },
            }).then(function (result) {
                // Eliminar dashboards anteriores
                self.$('.o_sat_dashboard').remove();

                // Renderizar nuevo dashboard
                const $dashboard = $(qweb.render('SatSatDashboard', {
                    values: result,
                }));
                // Insertarlo arriba de la vista lista
                self.$el.prepend($dashboard);
            });
        },
    });

    const SatListView = ListView.extend({
        config: Object.assign({}, ListView.prototype.config, {
            Controller: SatListController,
        }),
    });

    // Nombre de vista que usas en js_class del <tree>
    viewRegistry.add('sat_tree_dashboard', SatListView);
});
