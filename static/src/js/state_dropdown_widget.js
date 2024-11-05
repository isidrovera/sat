// static/src/js/state_dropdown_widget.js
odoo.define('sat.state_dropdown_widget', function (require) {
    "use strict";

    var FieldSelection = require('web.relational_fields').FieldSelection;
    var fieldRegistry = require('web.field_registry');

    var StateDropdownWidget = FieldSelection.extend({
        className: 'o_state_dropdown_widget',
        init: function () {
            this._super.apply(this, arguments);
        },

        _renderEdit: function () {
            var self = this;
            this.$el.empty();
            var select = $('<select>', { class: 'custom-state-dropdown' });
            this.field.selection.forEach(function (option) {
                var colorClass = self._getColorClass(option[0]);
                select.append($('<option>', {
                    value: option[0],
                    text: option[1],
                    class: colorClass
                }));
            });
            select.val(this.value);
            this.$el.append(select);
        },

        _getColorClass: function (state) {
            // Define colores según cada estado
            switch (state) {
                case 'draft': return 'status-draft';
                case 'done': return 'status-done';
                case 'canceled': return 'status-canceled';
                default: return 'status-default';
            }
        },

        _renderReadonly: function () {
            var colorClass = this._getColorClass(this.value);
            this.$el.html('<span class="' + colorClass + '">' + this._getDisplayString() + '</span>');
        }
    });

    fieldRegistry.add('state_dropdown_widget', StateDropdownWidget);
});
