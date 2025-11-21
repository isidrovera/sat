/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, onWillUpdateProps, useState } from "@odoo/owl";

export class SatListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.dashboardData = useState({});
        
        onWillStart(async () => {
            await this.loadDashboardData();
        });

        onWillUpdateProps(async () => {
            await this.loadDashboardData();
        });
    }

    async loadDashboardData() {
        try {
            // Obtener el dominio de forma segura
            let domain = [];
            if (this.model && this.model.root) {
                domain = this.model.root.domain || [];
            } else if (this.props && this.props.domain) {
                domain = this.props.domain;
            }

            const result = await this.orm.call(
                "sat.sat",
                "get_sat_dashboard_values",
                [],
                { domain: domain }
            );
            
            Object.assign(this.dashboardData, result);
        } catch (error) {
            console.error("Error loading SAT dashboard:", error);
        }
    }
}

SatListController.template = "sat.SatSatDashboard";

export const satListView = {
    ...listView,
    Controller: SatListController,
};

registry.category("views").add("sat_tree_dashboard", satListView);