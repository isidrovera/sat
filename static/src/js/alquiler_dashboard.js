/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";

export class AlquilerDashboard extends Component {
    static template = "alquiler.AlquilerDashboard";
    static props = {
        "*": true,
    };
    
    setup() {
        this.orm = useService("orm");
        this.state = useState({ 
            data: {
                total_equipos: 0,
                total_sin_revisar: 0,
                total_revisada: 0,
                total_lista: 0,
                total_alquilada: 0,
                total_con_problemas: 0,
                total_partes: 0,
                total_externo: 0,
                total_vendida: 0,
            }
        });
        
        onWillStart(async () => {
            await this.loadData();
        });

        onWillUpdateProps(async (nextProps) => {
            await this.loadData(nextProps);
        });
    }
    
    async loadData(props) {
        try {
            props = props || this.props;
            
            let domain = [];
            const model = props.model;
            if (model && model.root) {
                domain = model.root.domain || [];
            }
            
            const result = await this.orm.call(
                "alquiler",
                "get_alquiler_dashboard_values",
                [],
                { domain: domain }
            );
            
            Object.assign(this.state.data, result);
            
        } catch (error) {
            console.error("Error cargando dashboard Alquiler:", error);
        }
    }

    async filterByState(state) {
        console.log("🔍 Filtrando alquiler por estado:", state);
        
        let domain = [];
        
        switch(state) {
            case 'sin_revisar':
                domain = [['estado_alquiler_id', '=', 'sin_revisar']];
                break;
            case 'revisada':
                domain = [['estado_alquiler_id', '=', 'revisada']];
                break;
            case 'lista':
                domain = [['estado_alquiler_id', '=', 'lista']];
                break;
            case 'alquilada':
                domain = [['estado_alquiler_id', '=', 'alquilada']];
                break;
            case 'con_problemas':
                domain = [['estado_alquiler_id', '=', 'con_problemas']];
                break;
            case 'partes':
                domain = [['estado_alquiler_id', '=', 'partes']];
                break;
            case 'externo':
                domain = [['estado_alquiler_id', '=', 'externo']];
                break;
            case 'vendida':
                domain = [['estado_alquiler_id', '=', 'vendida']];
                break;
            case 'all':
                domain = [['estado_alquiler_id', '!=', 'vendida']];
                break;
        }

        console.log("📋 Dominio a aplicar:", domain);

        // Método que SÍ funciona en Odoo 18
        const model = this.props.model;
        if (model && model.root) {
            try {
                // Usar replaceWith para cambiar completamente el dominio
                await model.root.replaceWith({
                    ...model.root,
                    domain: domain,
                });
                console.log("✅ Filtro aplicado exitosamente");
            } catch (error) {
                console.error("❌ Error al aplicar filtro:", error);
                
                // Fallback: Intentar con load
                try {
                    model.root.domain = domain;
                    await model.root.load();
                    console.log("✅ Filtro aplicado con load()");
                } catch (error2) {
                    console.error("❌ Error con load():", error2);
                }
            }
        } else {
            console.error("❌ No se encontró el modelo");
        }
    }
}

export class AlquilerListController extends ListController {
    setup() {
        super.setup();
    }
}

AlquilerListController.components = {
    ...ListController.components,
    AlquilerDashboard,
};

AlquilerListController.template = "alquiler.AlquilerListView";

export const alquilerListView = {
    ...listView,
    Controller: AlquilerListController,
};

registry.category("views").add("alquiler_tree_dashboard", alquilerListView);