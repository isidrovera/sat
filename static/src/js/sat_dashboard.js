/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class SatDashboard extends Component {
    static template = "sat.SatSatDashboard";
    
    setup() {
        this.orm = useService("orm");
        this.state = useState({ 
            data: {
                total_maquinas: 0,
                total_disponibles: 0,
                total_separadas: 0,
                total_problemas: 0,
                company_currency_symbol: '',
                avg_precio_compra: 0,
                stock_value_available: 0,
                ingresadas_7: 0,
                entregadas_30: 0,
            }
        });
        
        onWillStart(async () => {
            await this.loadData();
        });
    }
    
    async loadData() {
        try {
            // Obtener dominio de forma segura desde props
            const domain = this.props.domain || [];
            
            const result = await this.orm.call(
                "sat.sat",
                "get_sat_dashboard_values",
                [],
                { domain: domain }
            );
            
            // Actualizar state con los datos recibidos
            Object.assign(this.state.data, result);
            
        } catch (error) {
            console.error("Error cargando dashboard SAT:", error);
        }
    }
}

export class SatListController extends ListController {
    setup() {
        super.setup();
        // No necesitamos hacer nada especial aquí
    }
}

// Configurar la vista personalizada
export const satListView = {
    ...listView,
    Controller: SatListController,
    // Agregar el dashboard como banner (aparecerá arriba de la lista)
    banner: SatDashboard,
};

// Registrar la vista
registry.category("views").add("sat_tree_dashboard", satListView);