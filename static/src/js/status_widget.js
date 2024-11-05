// Custom Status Widget JavaScript (static/src/js/status_widget.js)
odoo.define('sat.StatusWidget', function (require) {
    "use strict";

    const AbstractField = require('web.AbstractField');
    const registry = require('web.field_registry');
    const core = require('web.core');
    const QWeb = core.qweb;

    const StatusWidget = AbstractField.extend({
        template: 'StatusWidgetTemplate',
        events: {
            'click .status-option': '_onStatusClick',
            'click .current-status': '_toggleDropdown'
        },
        
        init: function () {
            this._super.apply(this, arguments);
            this.status_colors = {
                'sin_revisar': '#grey',
                'para_revision': '#blue',
                'asignado': '#orange',
                'en_revision': '#yellow',
                'finalizado': '#green',
                'con_problemas': '#red',
                'de_partes': '#purple',
                'entregada': '#teal'
            };
        },

        _render: function () {
            this.$el.html(QWeb.render('StatusWidgetTemplate', {
                status_colors: this.status_colors,
                current_value: this.value,
                selection: this.field.selection,
                readonly: this.mode === 'readonly'
            }));
            this._setStatusColor();
        },

        _setStatusColor: function () {
            const color = this.status_colors[this.value];
            this.$('.status-bar').css('background-color', color);
        },

        _toggleDropdown: function () {
            if (this.mode !== 'readonly') {
                this.$('.status-dropdown').toggleClass('show');
            }
        },

        _onStatusClick: function (ev) {
            if (this.mode === 'readonly') {
                return;
            }
            const newValue = $(ev.currentTarget).data('value');
            this._setValue(newValue);
            this.$('.status-dropdown').removeClass('show');
        },

        isSet: function () {
            return true;
        },
    });

    registry.add('status_widget', StatusWidget);
    return StatusWidget;
});