/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const STATE_LABELS = {
    nuevo: "NUEVO",
    proceso: "PROCESO",
    en_ruta: "EN RUTA",
    en_sitio: "EN SITIO",
    en_revision: "EN REVISIÓN",
    finalizado: "FINALIZADO",
};

export class MobileTicketLayout extends Component {
    static template = "sat.MobileTicketLayout";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.uiState = useState({
            isMobile: this._checkMobile(),
            menuOpen: false,
            saving: false,
            accordions: {
                componentes: { open: true },
                accesorios: { open: true },
                informe: { open: false },
                pedidos: { open: false },
                ubicacion: { open: false },
                gps: { open: false },
            },
        });

        this._onResize = () => {
            this.uiState.isMobile = this._checkMobile();

            if (this.uiState.isMobile) {
                document.body.classList.add("o_mobile_ticket_active");
            } else {
                document.body.classList.remove("o_mobile_ticket_active");
                this.uiState.menuOpen = false;
            }
        };

        onMounted(() => {
            window.addEventListener("resize", this._onResize);

            if (this.uiState.isMobile) {
                document.body.classList.add("o_mobile_ticket_active");
            }
        });

        onWillUnmount(() => {
            window.removeEventListener("resize", this._onResize);
            document.body.classList.remove("o_mobile_ticket_active");
        });
    }

    _checkMobile() {
        return window.innerWidth <= 768;
    }

    get record() {
        return this.props.record;
    }

    get data() {
        return this.record?.data || {};
    }

    _readM2O(fieldName) {
        const value = this.data[fieldName];

        if (!value) {
            return "";
        }

        if (Array.isArray(value)) {
            return value[1] || "";
        }

        if (typeof value === "object") {
            return value.display_name || value.name || "";
        }

        return String(value);
    }

    get ticketNumber() {
        return this.data.name || "";
    }

    get currentState() {
        return this.data.estado || "nuevo";
    }

    get stateLabel() {
        return STATE_LABELS[this.currentState] || String(this.currentState || "").toUpperCase();
    }

    get stateClass() {
        return `o_status_${this.currentState}`;
    }

    get clientName() {
        return this._readM2O("partner_id") || "Sin cliente";
    }

    get clientInitials() {
        return this.clientName
            .split(" ")
            .filter((word) => word)
            .slice(0, 2)
            .map((word) => word[0])
            .join("")
            .toUpperCase();
    }

    get clientAddress() {
        return this.data.equipo_direccion_completa || "";
    }

    get clientLocation() {
        return [
            this.data.equipo_distrito,
            this.data.equipo_provincia,
            this.data.equipo_departamento,
        ]
            .filter((part) => part)
            .join(", ");
    }

    get clientReference() {
        return this.data.equipo_direccion_referencia || "";
    }

    get hasCoordinates() {
        return !!this.data.equipo_tiene_coordenadas;
    }

    get contactName() {
        return this._readM2O("contacto_id_r");
    }

    get reporterName() {
        return this.data.reporter_name || "";
    }

    get reporterPhone() {
        return this.data.reporter_phone || "";
    }

    get tipoServicio() {
        return this._readM2O("tipo_servicio_id");
    }

    get agendaTexto() {
        return this.data.agenda_local || this.data.agenda || "";
    }

    get responsableName() {
        return this._readM2O("responsable");
    }

    get asistenciaName() {
        return this._readM2O("asistencia_id");
    }

    get equipoMarca() {
        return this._readM2O("marca_id_r");
    }

    get equipoSerie() {
        return this._readM2O("serie_id_r");
    }

    get equipoModelo() {
        return this.data.product_alquiler || "";
    }

    get esColor() {
        return this.data.tipo_id === "color";
    }

    get contadorK() {
        return this.data.contometrok_id || 0;
    }

    get contadorColor() {
        return this.data.contometroc_id || 0;
    }

    get contadorScan() {
        return this.data.contometros_id || 0;
    }

    get descripcionProblema() {
        return this.data.description || "";
    }

    get tienePhoto() {
        return !!this.data.problem_photo;
    }

    get informeHtml() {
        return this.data.informe_id || "";
    }

    _countList(fieldName) {
        const list = this.data[fieldName];

        if (!list) {
            return 0;
        }

        if (Array.isArray(list)) {
            return list.length;
        }

        if (list.records) {
            return list.records.length;
        }

        return 0;
    }

    _countWithEstado(fieldName) {
        const list = this.data[fieldName];

        if (!list || !list.records) {
            return 0;
        }

        return list.records.filter((item) => !!item.data.estado_id).length;
    }

    get componentesCount() {
        return this._countList("ticket_componente_eval_ids");
    }

    get componentesEvaluados() {
        return this._countWithEstado("ticket_componente_eval_ids");
    }

    get componentesPendientes() {
        return Math.max(this.componentesCount - this.componentesEvaluados, 0);
    }

    get componentesCompleto() {
        return this.componentesCount > 0 && this.componentesPendientes === 0;
    }

    get accesoriosCount() {
        return this._countList("ticket_accesorio_eval_ids");
    }

    get accesoriosEvaluados() {
        return this._countWithEstado("ticket_accesorio_eval_ids");
    }

    get accesoriosPendientes() {
        return Math.max(this.accesoriosCount - this.accesoriosEvaluados, 0);
    }

    get accesoriosCompleto() {
        return this.accesoriosCount > 0 && this.accesoriosPendientes === 0;
    }

    get pedidosCount() {
        return this._countList("ticket_pedido_ids");
    }

    get canCargarContadores() {
        return !!this.data.mostrar_boton_contadores;
    }

    get canCerrarTicket() {
        return ["proceso", "en_ruta", "en_sitio", "en_revision"].includes(this.currentState);
    }

    get menuActions() {
        const state = this.currentState;
        const actions = [];

        if (state === "nuevo") {
            actions.push({
                icon: "fa-paper-plane",
                label: "Asignar ticket",
                method: "action_asignar_ticket",
            });
        }

        if (state === "proceso") {
            actions.push({
                icon: "fa-car",
                label: "🚗 En ruta",
                method: "action_en_ruta",
            });
        }

        if (["proceso", "en_ruta"].includes(state)) {
            actions.push({
                icon: "fa-map-marker",
                label: "📍 Llegué al sitio",
                method: "action_en_sitio",
            });
        }

        if (state === "en_sitio") {
            actions.push({
                icon: "fa-wrench",
                label: "🔧 Iniciar revisión",
                method: "action_en_revision",
            });
        }

        actions.push(
            {
                icon: "fa-refresh",
                label: "Regenerar informe",
                method: "action_regenerar_informe",
            },
            {
                icon: "fa-eraser",
                label: "Limpiar informe",
                method: "action_limpiar_informe",
            },
            {
                icon: "fa-check-circle",
                label: "Generar evaluación",
                method: "action_crear_evaluacion",
            },
            {
                icon: "fa-paper-plane",
                label: "📤 Enviar a Administración",
                method: "action_enviar_informe_administracion",
            }
        );

        return actions;
    }

    accordionClass(sectionId) {
        const accordion = this.uiState.accordions[sectionId];

        if (!accordion) {
            return "o_mobile_accordion";
        }

        let className = "o_mobile_accordion";

        if (accordion.open) {
            className += " o_accordion_open";
        }

        if (sectionId === "componentes") {
            if (this.componentesCompleto) {
                className += " o_accordion_complete";
            } else if (this.componentesPendientes > 0) {
                className += " o_accordion_pending";
            }
        }

        if (sectionId === "accesorios") {
            if (this.accesoriosCompleto) {
                className += " o_accordion_complete";
            } else if (this.accesoriosPendientes > 0) {
                className += " o_accordion_pending";
            }
        }

        return className;
    }

    isAccordionOpen(sectionId) {
        return !!this.uiState.accordions[sectionId]?.open;
    }

    toggleAccordion(sectionId) {
        const accordion = this.uiState.accordions[sectionId];

        if (!accordion) {
            return;
        }

        accordion.open = !accordion.open;
    }

    toggleComponentes() {
        this.toggleAccordion("componentes");
    }

    toggleAccesorios() {
        this.toggleAccordion("accesorios");
    }

    toggleInforme() {
        this.toggleAccordion("informe");
    }

    toggleMenu() {
        this.uiState.menuOpen = !this.uiState.menuOpen;
    }

    closeMenu() {
        this.uiState.menuOpen = false;
    }

    async reloadRecord() {
        if (this.record?.load) {
            await this.record.load();
        }
    }

    async getViewId(xmlid) {
        try {
            return await this.orm.call("ir.model.data", "_xmlid_to_res_id", [xmlid]);
        } catch (error) {
            console.error("[MobileTicket] No se pudo obtener view_id:", xmlid, error);
            return false;
        }
    }

    async saveMobileValues(values) {
        if (!this.record?.resModel || !this.record?.resId) {
            return;
        }

        if (this.uiState.saving) {
            return;
        }

        this.uiState.saving = true;

        try {
            await this.orm.write(this.record.resModel, [this.record.resId], values);
            await this.reloadRecord();

            this.notification.add("Cambios guardados.", {
                type: "success",
            });
        } catch (error) {
            console.error("[MobileTicket] Error guardando valores móviles:", error);

            this.notification.add("No se pudo guardar el cambio.", {
                type: "danger",
            });
        } finally {
            this.uiState.saving = false;
        }
    }

    async onChangeContadorK(ev) {
        await this.saveMobileValues({
            contometrok_id: Number(ev.target.value || 0),
        });
    }

    async onChangeContadorColor(ev) {
        await this.saveMobileValues({
            contometroc_id: Number(ev.target.value || 0),
        });
    }

    async onChangeContadorScan(ev) {
        await this.saveMobileValues({
            contometros_id: Number(ev.target.value || 0),
        });
    }

    async onChangeDescription(ev) {
        await this.saveMobileValues({
            description: ev.target.value || "",
        });
    }

    async onChangeInforme(ev) {
        await this.saveMobileValues({
            informe_id: ev.target.value || "",
        });
    }

    async callAction(actionName) {
        this.closeMenu();

        if (!this.record?.resModel || !this.record?.resId) {
            return;
        }

        try {
            const result = await this.orm.call(
                this.record.resModel,
                actionName,
                [this.record.resId],
                {}
            );

            if (result && typeof result === "object" && result.type) {
                await this.action.doAction(result);
            }

            await this.reloadRecord();
        } catch (error) {
            console.error("[MobileTicket] Error en acción:", actionName, error);

            this.notification.add("No se pudo ejecutar la acción.", {
                type: "danger",
            });
        }
    }

    async onMenuAction(actionItem) {
        if (!actionItem || !actionItem.method) {
            return;
        }

        await this.callAction(actionItem.method);
    }

    async onCargarContadores() {
        if (!this.canCargarContadores) {
            return;
        }

        if (!confirm("¿Cargar los contadores desde el equipo?")) {
            return;
        }

        await this.callAction("action_cargar_contadores");
    }

    async onCerrarTicket() {
        if (!this.canCerrarTicket) {
            return;
        }

        if (!confirm("¿Cerrar este ticket?")) {
            return;
        }

        await this.callAction("action_finalizar");
    }

    async onAbrirMapa() {
        await this.callAction("action_abrir_mapa_equipo");
    }

    async onNavegar() {
        await this.callAction("action_navegar_a_equipo");
    }

    async openComponentes() {
    this.closeMenu();

    if (!this.record?.resId) {
        return;
    }

    await this.action.doAction("sat.action_ticket_componente_evaluacion_mobile", {
        additionalContext: {
            active_id: this.record.resId,
            active_ids: [this.record.resId],
            active_model: this.record.resModel,
            default_ticket_id: this.record.resId,
            mobile_ticket_eval: true,
        },
    });
}

async openAccesorios() {
    this.closeMenu();

    if (!this.record?.resId) {
        return;
    }

    await this.action.doAction("sat.action_ticket_accesorio_evaluacion_mobile", {
        additionalContext: {
            active_id: this.record.resId,
            active_ids: [this.record.resId],
            active_model: this.record.resModel,
            default_ticket_id: this.record.resId,
            mobile_ticket_eval: true,
        },
    });
}

    async openPedidos() {
        this.closeMenu();

        if (!this.record?.resId) {
            return;
        }

        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Pedidos de repuestos",
            res_model: "ticket.repuesto.pedido",
            view_mode: "list,form",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            target: "current",
            domain: [["ticket_id", "=", this.record.resId]],
            context: {
                default_ticket_id: this.record.resId,
                active_id: this.record.resId,
                active_ids: [this.record.resId],
                active_model: this.record.resModel,
            },
        });
    }

    async openFullForm() {
        this.closeMenu();

        if (!this.record?.resModel || !this.record?.resId) {
            return;
        }

        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Ticket",
            res_model: this.record.resModel,
            res_id: this.record.resId,
            view_mode: "form",
            views: [[false, "form"]],
            target: "current",
            context: {
                active_id: this.record.resId,
                active_ids: [this.record.resId],
                active_model: this.record.resModel,
            },
        });
    }

    callPhone(phone) {
        if (phone) {
            window.location.href = `tel:${phone}`;
        }
    }
}

export const mobileTicketLayoutField = {
    component: MobileTicketLayout,
    supportedTypes: ["char", "text", "boolean", "integer"],
};

registry.category("fields").add("mobile_layout", mobileTicketLayoutField);