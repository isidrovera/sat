/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const TAG = "[MobileTicket]";

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
            actionLoading: false,
            lastActionName: null,
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
            const oldValue = this.uiState.isMobile;
            const newValue = this._checkMobile();

            this.uiState.isMobile = newValue;

            console.log(TAG, "[resize]", {
                oldIsMobile: oldValue,
                newIsMobile: newValue,
                width: window.innerWidth,
            });

            if (this.uiState.isMobile) {
                document.body.classList.add("o_mobile_ticket_active");
            } else {
                document.body.classList.remove("o_mobile_ticket_active");
                this.uiState.menuOpen = false;
            }
        };

        onMounted(() => {
            console.log(TAG, "[mounted]", {
                isMobile: this.uiState.isMobile,
                record: this.record,
                data: this.data,
                resModel: this.record?.resModel,
                resId: this.record?.resId,
            });

            window.addEventListener("resize", this._onResize);

            if (this.uiState.isMobile) {
                document.body.classList.add("o_mobile_ticket_active");
            }
        });

        onWillUnmount(() => {
            console.log(TAG, "[willUnmount]");

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

        console.log(TAG, "[toggleAccordion]", {
            sectionId,
            exists: !!accordion,
            before: accordion?.open,
        });

        if (!accordion) {
            return;
        }

        accordion.open = !accordion.open;

        console.log(TAG, "[toggleAccordion] after", {
            sectionId,
            after: accordion.open,
        });
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

        console.log(TAG, "[toggleMenu]", {
            menuOpen: this.uiState.menuOpen,
        });
    }

    closeMenu() {
        this.uiState.menuOpen = false;
    }

    async reloadRecord() {
        console.log(TAG, "[reloadRecord] start", {
            hasLoad: !!this.record?.load,
            resModel: this.record?.resModel,
            resId: this.record?.resId,
        });

        if (this.record?.load) {
            await this.record.load();
        }

        console.log(TAG, "[reloadRecord] done", {
            data: this.data,
        });
    }

    async getViewId(xmlid) {
        console.log(TAG, "[getViewId] start", {
            xmlid,
        });

        try {
            const viewId = await this.orm.call("ir.model.data", "_xmlid_to_res_id", [xmlid]);

            console.log(TAG, "[getViewId] success", {
                xmlid,
                viewId,
            });

            return viewId;

        } catch (error) {
            console.error(TAG, "[getViewId] error", {
                xmlid,
                error,
            });

            return false;
        }
    }

    async saveMobileValues(values) {
        console.log(TAG, "[saveMobileValues] start", {
            values,
            resModel: this.record?.resModel,
            resId: this.record?.resId,
            saving: this.uiState.saving,
        });

        if (!this.record?.resModel || !this.record?.resId) {
            console.warn(TAG, "[saveMobileValues] no resModel/resId");
            return;
        }

        if (this.uiState.saving) {
            console.warn(TAG, "[saveMobileValues] already saving");
            return;
        }

        this.uiState.saving = true;

        try {
            await this.orm.write(this.record.resModel, [this.record.resId], values);

            console.log(TAG, "[saveMobileValues] write OK");

            await this.reloadRecord();

            this.notification.add("Cambios guardados.", {
                type: "success",
            });

        } catch (error) {
            console.error(TAG, "[saveMobileValues] error", error);

            this.notification.add("No se pudo guardar el cambio.", {
                type: "danger",
            });

        } finally {
            this.uiState.saving = false;

            console.log(TAG, "[saveMobileValues] finally", {
                saving: this.uiState.saving,
            });
        }
    }

    async onChangeContadorK(ev) {
        console.log(TAG, "[onChangeContadorK]", ev.target.value);

        await this.saveMobileValues({
            contometrok_id: Number(ev.target.value || 0),
        });
    }

    async onChangeContadorColor(ev) {
        console.log(TAG, "[onChangeContadorColor]", ev.target.value);

        await this.saveMobileValues({
            contometroc_id: Number(ev.target.value || 0),
        });
    }

    async onChangeContadorScan(ev) {
        console.log(TAG, "[onChangeContadorScan]", ev.target.value);

        await this.saveMobileValues({
            contometros_id: Number(ev.target.value || 0),
        });
    }

    async onChangeDescription(ev) {
        console.log(TAG, "[onChangeDescription]", ev.target.value);

        await this.saveMobileValues({
            description: ev.target.value || "",
        });
    }

    async onChangeInforme(ev) {
        console.log(TAG, "[onChangeInforme]", ev.target.value);

        await this.saveMobileValues({
            informe_id: ev.target.value || "",
        });
    }

    normalizeAction(action, actionName = "") {
        console.log(TAG, "[normalizeAction] input", {
            actionName,
            action,
        });

        if (!action || typeof action !== "object") {
            console.log(TAG, "[normalizeAction] action vacía o no objeto", {
                actionName,
                action,
            });

            return action;
        }

        if (action.type === "ir.actions.act_window") {
            const viewMode = action.view_mode || "form";

            /*
             * Odoo 18 necesita action.views.
             * Desde la interfaz estándar a veces Odoo completa esto,
             * pero desde este componente móvil debemos normalizarlo.
             */
            if (!action.views) {
                const firstViewMode = viewMode.split(",")[0] || "form";
                let viewId = false;

                if (Array.isArray(action.view_id)) {
                    viewId = action.view_id[0] || false;
                } else if (typeof action.view_id === "number") {
                    viewId = action.view_id;
                } else {
                    viewId = false;
                }

                action.views = [[viewId, firstViewMode]];

                console.warn(TAG, "[normalizeAction] action.views no venía definido. Se agregó.", {
                    actionName,
                    viewMode,
                    viewId,
                    views: action.views,
                });
            }

            if (!action.view_mode) {
                action.view_mode = action.views.map((view) => view[1]).join(",");

                console.warn(TAG, "[normalizeAction] action.view_mode no venía definido. Se agregó.", {
                    actionName,
                    view_mode: action.view_mode,
                });
            }

            if (!action.target) {
                action.target = "current";

                console.warn(TAG, "[normalizeAction] action.target no venía definido. Se agregó current.", {
                    actionName,
                });
            }
        }

        console.log(TAG, "[normalizeAction] output", {
            actionName,
            action,
        });

        return action;
    }

    async callAction(actionName, kwargs = {}) {
        this.closeMenu();

        console.log(TAG, "[callAction] start", {
            actionName,
            kwargs,
            resModel: this.record?.resModel,
            resId: this.record?.resId,
            currentState: this.currentState,
            data: this.data,
        });

        if (!this.record?.resModel || !this.record?.resId) {
            console.warn(TAG, "[callAction] no resModel/resId", {
                actionName,
                record: this.record,
            });

            this.notification.add("No se pudo ejecutar la acción: ticket sin ID.", {
                type: "warning",
            });

            return;
        }

        if (this.uiState.actionLoading) {
            console.warn(TAG, "[callAction] acción bloqueada porque otra está en ejecución", {
                actionName,
                lastActionName: this.uiState.lastActionName,
            });

            return;
        }

        this.uiState.actionLoading = true;
        this.uiState.lastActionName = actionName;

        try {
            /*
             * Importante:
             * Para llamar métodos type='object' de un recordset,
             * usamos [[resId]], no [resId].
             */
            console.log(TAG, "[callAction] orm.call before", {
                model: this.record.resModel,
                method: actionName,
                args: [[this.record.resId]],
                kwargs,
            });

            const result = await this.orm.call(
                this.record.resModel,
                actionName,
                [[this.record.resId]],
                kwargs
            );

            console.log(TAG, "[callAction] orm.call result", {
                actionName,
                result,
            });

            if (result && typeof result === "object" && result.type) {
                const normalizedAction = this.normalizeAction(result, actionName);

                console.log(TAG, "[callAction] doAction before", {
                    actionName,
                    normalizedAction,
                });

                await this.action.doAction(normalizedAction);

                console.log(TAG, "[callAction] doAction success", {
                    actionName,
                    normalizedAction,
                });
            } else {
                console.log(TAG, "[callAction] método sin acción retornada", {
                    actionName,
                    result,
                });
            }

            /*
             * Si abrió un wizard modal target='new', no forzamos reload inmediato.
             * Si no, recargamos el ticket.
             */
            if (!(result && result.type === "ir.actions.act_window" && result.target === "new")) {
                await this.reloadRecord();
            } else {
                console.log(TAG, "[callAction] no reload porque se abrió modal/wizard", {
                    actionName,
                    result,
                });
            }

        } catch (error) {
            console.error(TAG, "[callAction] error", {
                actionName,
                error,
            });

            this.notification.add("No se pudo ejecutar la acción.", {
                type: "danger",
            });

        } finally {
            this.uiState.actionLoading = false;
            this.uiState.lastActionName = null;

            console.log(TAG, "[callAction] finally", {
                actionName,
                actionLoading: this.uiState.actionLoading,
            });
        }
    }

    async onMenuAction(actionItem) {
        console.log(TAG, "[onMenuAction]", {
            actionItem,
        });

        if (!actionItem || !actionItem.method) {
            console.warn(TAG, "[onMenuAction] actionItem inválido", {
                actionItem,
            });

            return;
        }

        await this.callAction(actionItem.method);
    }

    async onCargarContadores() {
        console.log(TAG, "[onCargarContadores] start", {
            canCargarContadores: this.canCargarContadores,
        });

        if (!this.canCargarContadores) {
            console.warn(TAG, "[onCargarContadores] no permitido");
            return;
        }

        if (!confirm("¿Cargar los contadores desde el equipo?")) {
            console.log(TAG, "[onCargarContadores] cancelado por usuario");
            return;
        }

        await this.callAction("action_cargar_contadores");
    }

    async onCerrarTicket() {
        console.log(TAG, "[onCerrarTicket] start", {
            canCerrarTicket: this.canCerrarTicket,
            currentState: this.currentState,
            resId: this.record?.resId,
        });

        if (!this.canCerrarTicket) {
            console.warn(TAG, "[onCerrarTicket] no permitido por estado", {
                currentState: this.currentState,
            });

            return;
        }

        if (!confirm("¿Cerrar este ticket?")) {
            console.log(TAG, "[onCerrarTicket] cancelado por usuario");
            return;
        }

        await this.callAction("action_finalizar");
    }

    async onAbrirMapa() {
        console.log(TAG, "[onAbrirMapa]");

        await this.callAction("action_abrir_mapa_equipo");
    }

    async onNavegar() {
        console.log(TAG, "[onNavegar]");

        await this.callAction("action_navegar_a_equipo");
    }

    async openComponentes() {
        this.closeMenu();

        console.log(TAG, "[openComponentes] start", {
            resId: this.record?.resId,
            resModel: this.record?.resModel,
        });

        if (!this.record?.resId) {
            console.warn(TAG, "[openComponentes] no resId");
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

        console.log(TAG, "[openComponentes] doAction OK");
    }

    async openAccesorios() {
        this.closeMenu();

        console.log(TAG, "[openAccesorios] start", {
            resId: this.record?.resId,
            resModel: this.record?.resModel,
        });

        if (!this.record?.resId) {
            console.warn(TAG, "[openAccesorios] no resId");
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

        console.log(TAG, "[openAccesorios] doAction OK");
    }

    async openPedidos() {
        this.closeMenu();

        console.log(TAG, "[openPedidos] start", {
            resId: this.record?.resId,
            resModel: this.record?.resModel,
        });

        if (!this.record?.resId) {
            console.warn(TAG, "[openPedidos] no resId");
            return;
        }

        const action = {
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
        };

        console.log(TAG, "[openPedidos] doAction", {
            action,
        });

        await this.action.doAction(action);
    }

    async openFullForm() {
        this.closeMenu();

        console.log(TAG, "[openFullForm] start", {
            resModel: this.record?.resModel,
            resId: this.record?.resId,
        });

        if (!this.record?.resModel || !this.record?.resId) {
            console.warn(TAG, "[openFullForm] no resModel/resId");
            return;
        }

        const action = {
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
        };

        console.log(TAG, "[openFullForm] doAction", {
            action,
        });

        await this.action.doAction(action);
    }

    callPhone(phone) {
        console.log(TAG, "[callPhone]", {
            phone,
        });

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