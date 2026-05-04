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

    _readM2O(field) {
        const val = this.data[field];

        if (!val) {
            return "";
        }

        if (Array.isArray(val)) {
            return val[1] || "";
        }

        if (typeof val === "object") {
            return val.display_name || val.name || "";
        }

        return String(val);
    }

    _readRawM2OId(field) {
        const val = this.data[field];

        if (!val) {
            return false;
        }

        if (Array.isArray(val)) {
            return val[0] || false;
        }

        if (typeof val === "object") {
            return val.resId || val.id || false;
        }

        return false;
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
            .filter((w) => w)
            .slice(0, 2)
            .map((w) => w[0])
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
            .filter((p) => p)
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

    _countList(field) {
        const list = this.data[field];

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

    _countWithEstado(field) {
        const list = this.data[field];

        if (!list || !list.records) {
            return 0;
        }

        return list.records.filter((r) => !!r.data.estado_id).length;
    }

    get componentesCount() {
        return this._countList("ticket_componente_eval_ids");
    }

    get componentesEvaluados() {
        return this._countWithEstado("ticket_componente_eval_ids");
    }

    get componentesPendientes() {
        return this.componentesCount - this.componentesEvaluados;
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
        return this.accesoriosCount - this.accesoriosEvaluados;
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

    toggleAccordion(sectionId) {
        const acc = this.uiState.accordions[sectionId];

        if (!acc) {
            return;
        }

        acc.open = !acc.open;
    }

    isAccordionOpen(sectionId) {
        return !!this.uiState.accordions[sectionId]?.open;
    }

    accordionClass(sectionId) {
        const acc = this.uiState.accordions[sectionId];

        if (!acc) {
            return "o_mobile_accordion";
        }

        let cls = "o_mobile_accordion";

        if (acc.open) {
            cls += " o_accordion_open";
        }

        if (sectionId === "componentes") {
            if (this.componentesCompleto) {
                cls += " o_accordion_complete";
            } else if (this.componentesPendientes > 0) {
                cls += " o_accordion_pending";
            }
        }

        if (sectionId === "accesorios") {
            if (this.accesoriosCompleto) {
                cls += " o_accordion_complete";
            } else if (this.accesoriosPendientes > 0) {
                cls += " o_accordion_pending";
            }
        }

        return cls;
    }

    toggleMenu() {
        this.uiState.menuOpen = !this.uiState.menuOpen;
    }

    closeMenu() {
        this.uiState.menuOpen = false;
    }

    async _saveRecordChanges(values) {
        if (!this.record || this.uiState.saving) {
            return;
        }

        this.uiState.saving = true;

        try {
            await this.record.update(values);

            if (this.record.save) {
                await this.record.save();
            }

            this.notification.add("Cambios guardados.", {
                type: "success",
            });
        } catch (err) {
            console.error("[MobileTicket] Error guardando cambios:", err);
            this.notification.add("No se pudo guardar el cambio.", {
                type: "danger",
            });
        } finally {
            this.uiState.saving = false;
        }
    }

    async onChangeContadorK(ev) {
        const value = Number(ev.target.value || 0);
        await this._saveRecordChanges({
            contometrok_id: value,
        });
    }

    async onChangeContadorColor(ev) {
        const value = Number(ev.target.value || 0);
        await this._saveRecordChanges({
            contometroc_id: value,
        });
    }

    async onChangeContadorScan(ev) {
        const value = Number(ev.target.value || 0);
        await this._saveRecordChanges({
            contometros_id: value,
        });
    }

    async onChangeDescription(ev) {
        await this._saveRecordChanges({
            description: ev.target.value || "",
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

            if (this.record.load) {
                await this.record.load();
            }
        } catch (err) {
            console.error("[MobileTicket] Error en acción:", actionName, err);
            this.notification.add("No se pudo ejecutar la acción.", {
                type: "danger",
            });
        }
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

    async openFullForm() {
        this.closeMenu();

        if (!this.record?.resId) {
            return;
        }

        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: this.record.resModel,
            res_id: this.record.resId,
            views: [[false, "form"]],
            target: "current",
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
    supportedTypes: ["char", "text"],
};

registry.category("fields").add("mobile_layout", mobileTicketLayoutField);