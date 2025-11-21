/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class SatListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.dashboardData = useState({ values: {} });
        
        onWillStart(async () => {
            await this.loadDashboardData();
        });
    }

    async loadDashboardData() {
        const domain = this.model.root.domain || [];
        const result = await this.orm.call(
            "sat.sat",
            "get_sat_dashboard_values",
            [],
            { domain: domain }
        );
        this.dashboardData.values = result;
    }

    async onUpdated() {
        await super.onUpdated(...arguments);
        await this.loadDashboardData();
    }
}

export const satListView = {
    ...listView,
    Controller: SatListController,
    buttonTemplate: "sat.SatSatDashboard",
};

registry.category("views").add("sat_tree_dashboard", satListView);