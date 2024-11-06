odoo.define('sat.estado_ventas_color', function (require) {
    "use strict";

    const { registry } = require('web.field_registry');
    const Statusbar = require('web.basic_fields').Statusbar;

    const ColoredStatusbar = Statusbar.extend({
        _render: function () {
            this._super.apply(this, arguments);
            this.$el.removeClass((index, className) => {
                return (className.match(/(^|\s)estado-\S+/g) || []).join(' ');
            });
            if (this.value) {
                this.$el.addClass(`estado-${this.value}`);
            }
        }
    });

    registry.add('colored_statusbar', ColoredStatusbar);
});
