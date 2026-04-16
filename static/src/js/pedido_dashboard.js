/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";

export class PedidoDashboard extends Component {
    static template = "sat.PedidoDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            data: {
                total_pedidos:             0,
                total_borrador:            0,
                total_esperando_gerencia:  0,
                total_informe_solicitado:  0,
                total_informe_recibido:    0,
                total_aprobado:            0,
                total_rechazado:           0,
                total_stock_en_revision:   0,
                total_stock_completo:      0,
                total_en_camino:           0,
                total_entregado:           0,
                total_instalado:           0,
                total_cancelado:           0,
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
            if (props.list && props.list.model && props.list.model.root) {
                domain = props.list.model.root.domain || [];
            }

            const result = await this.orm.call(
                "ticket.repuesto.pedido",
                "get_pedido_dashboard_values",
                [],
                { domain: domain }
            );

            Object.assign(this.state.data, result);

        } catch (error) {
            console.error("Error cargando dashboard Pedidos:", error);
        }
    }

    filterByState(state) {
        console.log("Filtrando pedidos por estado:", state);

        let domain = [];

        switch (state) {
            case 'borrador':
                domain = [['estado', '=', 'borrador']];
                break;
            case 'esperando_gerencia':
                domain = [['estado', '=', 'esperando_gerencia']];
                break;
            case 'informe_solicitado':
                domain = [['estado', '=', 'informe_solicitado']];
                break;
            case 'informe_recibido':
                domain = [['estado', '=', 'informe_recibido']];
                break;
            case 'aprobado':
                domain = [['estado', '=', 'aprobado']];
                break;
            case 'rechazado':
                domain = [['estado', '=', 'rechazado']];
                break;
            case 'stock_en_revision':
                domain = [['estado', '=', 'stock_en_revision']];
                break;
            case 'stock_completo':
                domain = [['estado', '=', 'stock_completo']];
                break;
            case 'en_camino':
                domain = [['estado', '=', 'en_camino']];
                break;
            case 'entregado':
                domain = [['estado', '=', 'entregado']];
                break;
            case 'instalado':
                domain = [['estado', '=', 'instalado']];
                break;
            case 'cancelado':
                domain = [['estado', '=', 'cancelado']];
                break;
            case 'all':
            default:
                domain = [];
                break;
        }

        console.log("Dominio aplicado:", domain);

        try {
            this.action.doAction({
                type: 'ir.actions.act_window',
                res_model: 'ticket.repuesto.pedido',
                name: 'Pedidos de Repuestos',
                views: [[false, 'list'], [false, 'form']],
                domain: domain,
                context: {},
                target: 'current',
            });
        } catch (error) {
            console.error("Error al aplicar filtro con doAction:", error);

            try {
                if (this.props.list && this.props.list.model && this.props.list.model.root) {
                    this.props.list.model.root.domain = domain;
                    this.props.list.model.root.load();
                }
            } catch (error2) {
                console.error("Error al aplicar filtro con model.load:", error2);
            }
        }
    }
}

export class PedidoListController extends ListController {
    setup() {
        super.setup();
    }
}

PedidoListController.components = {
    ...ListController.components,
    PedidoDashboard,
};

PedidoListController.template = "sat.PedidoListView";

export const pedidoListView = {
    ...listView,
    Controller: PedidoListController,
};

registry.category("views").add("pedido_tree_dashboard", pedidoListView);