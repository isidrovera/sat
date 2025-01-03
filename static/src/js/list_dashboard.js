/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useState } from "@odoo/owl";

class SatDashboardController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.state = useState({
            dashboardData: {
                total: 0,
                disponibles: 0,
                separadas: 0,
                noDisponibles: 0
            }
        });
        this.loadDashboardData();
    }

    async loadDashboardData() {
        const data = await this.orm.call('sat.sat', 'get_dashboard_data', []);
        Object.assign(this.state.dashboardData, data);
    }

    async applyFilter(filter) {
        const domain = filter ? [["disponibilidad_id", "=", filter]] : [];
        this.model.root.domain.splice(0, this.model.root.domain.length, ...domain);
        await this.model.root.load();
    }
}

// Registrar la vista personalizada
registry.category("views").add("sat_list_view", {
    ...listView,
    Controller: SatDashboardController,
    buttonTemplate: "sat.ListView.Buttons",
});
