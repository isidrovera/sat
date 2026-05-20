/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Bandeja moderna WhatsApp para Odoo 18
 *
 * IMPORTANTE:
 * - No reemplaza vistas existentes.
 * - No toca modelos.
 * - Usa los modelos actuales:
 *   whatsapp.session
 *   whatsapp.message
 *   whatsapp.outbox
 *   whatsapp.media
 *   whatsapp.handoff
 *   whatsapp.auto.response
 *   whatsapp.intent.rule
 *   whatsapp.template
 *   whatsapp.business.hours
 *   whatsapp.calendar.event
 *   whatsapp.api.log
 */
export class WhatsappInboxApp extends Component {
    static template = "sat.WhatsappInboxApp";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            loadingSessions: false,
            loadingMessages: false,

            query: "",
            activeFilter: "open",

            sessions: [],
            messages: [],

            selectedSession: null,
            selectedMessage: null,

            draftMessage: "",

            counters: {
                open: 0,
                human: 0,
                closed: 0,
                expired: 0,
                pending: 0,
                failedOutbox: 0,
                errors: 0,
                mediaPending: 0,
            },
        });

        onWillStart(async () => {
            await this.loadDashboard();
        });
    }

    // =========================================================
    // CARGA PRINCIPAL
    // =========================================================

    async loadDashboard() {
        this.state.loading = true;

        try {
            await Promise.all([
                this.loadCounters(),
                this.loadSessions(),
            ]);
        } catch (error) {
            console.error("[WhatsappInboxApp] Error loadDashboard:", error);
            this.notifyDanger("No se pudo cargar la bandeja WhatsApp.");
        } finally {
            this.state.loading = false;
        }
    }

    async refresh() {
        try {
            await this.loadDashboard();

            if (this.state.selectedSession) {
                await this.loadMessages(this.state.selectedSession.id);
            }

            this.notifySuccess("Bandeja actualizada.");
        } catch (error) {
            console.error("[WhatsappInboxApp] Error refresh:", error);
            this.notifyDanger("No se pudo actualizar la bandeja.");
        }
    }

    async loadCounters() {
        try {
            const [
                openCount,
                humanCount,
                closedCount,
                expiredCount,
                pendingOutboxCount,
                failedOutboxCount,
                apiErrorCount,
                mediaPendingCount,
            ] = await Promise.all([
                this.orm.searchCount("whatsapp.session", [["state", "=", "open"]]),
                this.orm.searchCount("whatsapp.session", [["state", "=", "human"]]),
                this.orm.searchCount("whatsapp.session", [["state", "=", "closed"]]),
                this.orm.searchCount("whatsapp.session", [["state", "=", "expired"]]),
                this.orm.searchCount("whatsapp.outbox", [["state", "=", "pending"]]),
                this.orm.searchCount("whatsapp.outbox", [["state", "=", "failed"]]),
                this.orm.searchCount("whatsapp.api.log", [["status", "=", "error"]]),
                this.orm.searchCount("whatsapp.media", [["is_processed", "=", false]]),
            ]);

            this.state.counters.open = openCount;
            this.state.counters.human = humanCount;
            this.state.counters.closed = closedCount;
            this.state.counters.expired = expiredCount;
            this.state.counters.pending = pendingOutboxCount;
            this.state.counters.failedOutbox = failedOutboxCount;
            this.state.counters.errors = apiErrorCount;
            this.state.counters.mediaPending = mediaPendingCount;
        } catch (error) {
            console.error("[WhatsappInboxApp] Error loadCounters:", error);
            throw error;
        }
    }

    getSessionDomain() {
        const domain = [];

        if (this.state.activeFilter === "open") {
            domain.push(["state", "=", "open"]);
        } else if (this.state.activeFilter === "human") {
            domain.push(["state", "=", "human"]);
        } else if (this.state.activeFilter === "closed") {
            domain.push(["state", "=", "closed"]);
        } else if (this.state.activeFilter === "expired") {
            domain.push(["state", "=", "expired"]);
        } else if (this.state.activeFilter === "active") {
            domain.push(["is_active", "=", true]);
        }

        const q = (this.state.query || "").trim();

        if (q) {
            domain.push(
                "|",
                "|",
                "|",
                "|",
                ["name", "ilike", q],
                ["phone", "ilike", q],
                ["last_intent", "ilike", q],
                ["last_user_message", "ilike", q],
                ["last_bot_message", "ilike", q]
            );
        }

        return domain;
    }

    async loadSessions() {
        this.state.loadingSessions = true;

        try {
            const sessions = await this.orm.searchRead(
                "whatsapp.session",
                this.getSessionDomain(),
                [
                    "name",
                    "partner_id",
                    "active_company_id",
                    "phone",
                    "jid",
                    "lid",
                    "raw_jid",
                    "source",
                    "state",
                    "last_intent",
                    "started_at",
                    "last_message_at",
                    "closed_at",
                    "message_count",
                    "last_user_message",
                    "last_bot_message",
                    "is_active",
                    "note",
                ],
                {
                    limit: 100,
                    order: "last_message_at desc, id desc",
                }
            );

            this.state.sessions = sessions;

            if (!sessions.length) {
                this.state.selectedSession = null;
                this.state.messages = [];
                return;
            }

            if (!this.state.selectedSession) {
                await this.selectSession(sessions[0]);
                return;
            }

            const current = sessions.find((session) => session.id === this.state.selectedSession.id);

            if (current) {
                this.state.selectedSession = current;
            } else {
                await this.selectSession(sessions[0]);
            }
        } catch (error) {
            console.error("[WhatsappInboxApp] Error loadSessions:", error);
            this.notifyDanger("No se pudieron cargar las conversaciones.");
        } finally {
            this.state.loadingSessions = false;
        }
    }

    async selectSession(session) {
        if (!session) {
            this.state.selectedSession = null;
            this.state.messages = [];
            return;
        }

        this.state.selectedSession = session;
        this.state.selectedMessage = null;

        await this.loadMessages(session.id);
    }

    async loadMessages(sessionId) {
        if (!sessionId) {
            this.state.messages = [];
            return;
        }

        this.state.loadingMessages = true;

        try {
            const messages = await this.orm.searchRead(
                "whatsapp.message",
                [["session_id", "=", sessionId]],
                [
                    "message_date",
                    "session_id",
                    "partner_id",
                    "company_id",
                    "direction",
                    "role",
                    "message_type",
                    "intent",
                    "content",
                    "phone",
                    "jid",
                    "lid",
                    "raw_jid",
                    "media_url",
                    "media_mimetype",
                    "external_message_id",
                    "is_error",
                    "error_message",
                ],
                {
                    limit: 300,
                    order: "message_date asc, id asc",
                }
            );

            this.state.messages = messages;
        } catch (error) {
            console.error("[WhatsappInboxApp] Error loadMessages:", error);
            this.notifyDanger("No se pudieron cargar los mensajes.");
        } finally {
            this.state.loadingMessages = false;
        }
    }

    // =========================================================
    // FILTROS Y BÚSQUEDA
    // =========================================================

    async setFilter(filter) {
        this.state.activeFilter = filter;
        this.state.selectedSession = null;
        this.state.selectedMessage = null;
        this.state.messages = [];

        await this.loadSessions();
    }

    async onSearchInput(ev) {
        this.state.query = ev.target.value || "";

        await this.loadSessions();
    }

    clearSearch() {
        this.state.query = "";
        this.loadSessions();
    }

    // =========================================================
    // NOTIFICACIONES
    // =========================================================

    notifySuccess(message) {
        this.notification.add(message, {
            type: "success",
        });
    }

    notifyWarning(message) {
        this.notification.add(message, {
            type: "warning",
        });
    }

    notifyDanger(message) {
        this.notification.add(message, {
            type: "danger",
        });
    }

    // =========================================================
    // ACCIONES DE SESIÓN
    // =========================================================

    async callSessionMethod(methodName, successMessage) {
        if (!this.state.selectedSession) {
            this.notifyWarning("Selecciona una conversación.");
            return;
        }

        try {
            await this.orm.call(
                "whatsapp.session",
                methodName,
                [[this.state.selectedSession.id]]
            );

            this.notifySuccess(successMessage);

            const selectedId = this.state.selectedSession.id;

            await Promise.all([
                this.loadCounters(),
                this.loadSessions(),
            ]);

            const current = this.state.sessions.find((session) => session.id === selectedId);

            if (current) {
                await this.selectSession(current);
            }
        } catch (error) {
            console.error(`[WhatsappInboxApp] Error ${methodName}:`, error);
            this.notifyDanger("No se pudo ejecutar la acción.");
        }
    }

    async actionSetHuman() {
        await this.callSessionMethod("action_set_human", "Sesión enviada a modo humano.");
    }

    async actionClose() {
        await this.callSessionMethod("action_close", "Sesión cerrada.");
    }

    async actionReopen() {
        await this.callSessionMethod("action_reopen", "Sesión reabierta.");
    }

    async actionExpire() {
        await this.callSessionMethod("action_expire", "Sesión expirada.");
    }

    async deleteCurrentSession() {
        if (!this.state.selectedSession) {
            this.notifyWarning("Selecciona una conversación para eliminar.");
            return;
        }

        const sessionName = this.getPartnerName(this.state.selectedSession);

        const confirmed = window.confirm(
            `¿Seguro que deseas eliminar la sesión de ${sessionName}?\n\n` +
            "Esta acción eliminará el registro seleccionado según las reglas del modelo. " +
            "Si tiene mensajes u otros registros relacionados, Odoo puede impedir la eliminación."
        );

        if (!confirmed) {
            return;
        }

        try {
            await this.orm.call(
                "whatsapp.session",
                "unlink",
                [[this.state.selectedSession.id]]
            );

            this.notifySuccess("Sesión eliminada correctamente.");

            this.state.selectedSession = null;
            this.state.selectedMessage = null;
            this.state.messages = [];

            await this.loadDashboard();
        } catch (error) {
            console.error("[WhatsappInboxApp] Error deleteCurrentSession:", error);
            this.notifyDanger(
                "No se pudo eliminar la sesión. Puede tener mensajes, media, handoff o restricciones relacionadas."
            );
        }
    }

    // =========================================================
    // MENSAJES
    // =========================================================

    selectMessage(message) {
        this.state.selectedMessage = message || null;
    }

    async deleteSelectedMessage(message) {
        if (!message) {
            return;
        }

        const confirmed = window.confirm(
            "¿Seguro que deseas eliminar este mensaje?\n\n" +
            "Si tiene media u otros datos relacionados, Odoo puede impedir la eliminación."
        );

        if (!confirmed) {
            return;
        }

        try {
            await this.orm.call(
                "whatsapp.message",
                "unlink",
                [[message.id]]
            );

            this.notifySuccess("Mensaje eliminado correctamente.");

            if (this.state.selectedSession) {
                await this.loadMessages(this.state.selectedSession.id);
            }

            await this.loadCounters();
        } catch (error) {
            console.error("[WhatsappInboxApp] Error deleteSelectedMessage:", error);
            this.notifyDanger(
                "No se pudo eliminar el mensaje. Puede tener registros relacionados."
            );
        }
    }

    async openMessageForm(message) {
        if (!message) {
            return;
        }

        this.openRecordForm("Mensaje WhatsApp", "whatsapp.message", message.id);
    }

    // =========================================================
    // ENVÍO / COLA DE SALIDA
    // =========================================================

    async sendMessage() {
        const session = this.state.selectedSession;
        const content = (this.state.draftMessage || "").trim();

        if (!session) {
            this.notifyWarning("Selecciona una conversación.");
            return;
        }

        if (!content) {
            this.notifyWarning("Escribe un mensaje antes de enviar.");
            return;
        }

        try {
            const vals = {
                session_id: session.id,
                partner_id: this.getMany2oneId(session.partner_id),
                company_id: this.getMany2oneId(session.active_company_id),
                phone: session.phone || "",
                jid: session.jid || "",
                lid: session.lid || "",
                message_type: "text",
                content: content,
                state: "pending",
            };

            await this.orm.create("whatsapp.outbox", [vals]);

            this.state.draftMessage = "";

            this.notifySuccess("Mensaje agregado a la cola de salida.");

            await Promise.all([
                this.loadCounters(),
                this.loadMessages(session.id),
            ]);
        } catch (error) {
            console.error("[WhatsappInboxApp] Error sendMessage:", error);
            this.notifyDanger(
                "No se pudo agregar el mensaje a la cola. Revisa campos obligatorios del modelo whatsapp.outbox."
            );
        }
    }

    onDraftInput(ev) {
        this.state.draftMessage = ev.target.value || "";
    }

    onDraftKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }

    clearDraft() {
        this.state.draftMessage = "";
    }

    // =========================================================
    // ACCIONES GENERALES DE ODOO
    // =========================================================

    openModelList(name, resModel, domain = [], context = {}) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name,
            res_model: resModel,
            views: [
                [false, "list"],
                [false, "form"],
            ],
            target: "current",
            domain: domain,
            context: context,
        });
    }

    openModelKanbanList(name, resModel, domain = [], context = {}) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name,
            res_model: resModel,
            views: [
                [false, "kanban"],
                [false, "list"],
                [false, "form"],
            ],
            target: "current",
            domain: domain,
            context: context,
        });
    }

    openRecordForm(name, resModel, resId, context = {}) {
        if (!resId) {
            this.notifyWarning("No hay registro seleccionado.");
            return;
        }

        this.action.doAction({
            type: "ir.actions.act_window",
            name: name,
            res_model: resModel,
            res_id: resId,
            views: [[false, "form"]],
            target: "current",
            context: context,
        });
    }

    createRecord(name, resModel, context = {}) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name,
            res_model: resModel,
            views: [[false, "form"]],
            target: "current",
            context: context,
        });
    }

    openModel(name, resModel, domain = [], context = {}) {
        this.openModelList(name, resModel, domain, context);
    }

    // =========================================================
    // ABRIR REGISTROS ACTUALES
    // =========================================================

    openCurrentSessionForm() {
        if (!this.state.selectedSession) {
            this.notifyWarning("Selecciona una conversación.");
            return;
        }

        this.openRecordForm(
            "Sesión WhatsApp",
            "whatsapp.session",
            this.state.selectedSession.id
        );
    }

    openCurrentPartner() {
        if (!this.state.selectedSession || !this.state.selectedSession.partner_id) {
            this.notifyWarning("La sesión no tiene contacto asociado.");
            return;
        }

        this.openRecordForm(
            "Contacto",
            "res.partner",
            this.getMany2oneId(this.state.selectedSession.partner_id)
        );
    }

    openCurrentCompany() {
        if (!this.state.selectedSession || !this.state.selectedSession.active_company_id) {
            this.notifyWarning("La sesión no tiene empresa activa asociada.");
            return;
        }

        this.openRecordForm(
            "Empresa / Cliente",
            "res.partner",
            this.getMany2oneId(this.state.selectedSession.active_company_id)
        );
    }

    // =========================================================
    // OPERACIÓN
    // =========================================================

    openSessions() {
        this.openModelList(
            "Sesiones WhatsApp",
            "whatsapp.session",
            []
        );
    }

    openMessages() {
        const domain = this.state.selectedSession
            ? [["session_id", "=", this.state.selectedSession.id]]
            : [];

        this.openModelList(
            "Mensajes WhatsApp",
            "whatsapp.message",
            domain
        );
    }

    openOutbox() {
        this.openModelList(
            "Cola de salida WhatsApp",
            "whatsapp.outbox",
            []
        );
    }

    openOutboxPending() {
        this.openModelList(
            "Cola pendiente WhatsApp",
            "whatsapp.outbox",
            [["state", "=", "pending"]]
        );
    }

    openOutboxFailed() {
        this.openModelList(
            "Cola fallida WhatsApp",
            "whatsapp.outbox",
            [["state", "=", "failed"]]
        );
    }

    openMedia() {
        const domain = this.state.selectedSession
            ? [["session_id", "=", this.state.selectedSession.id]]
            : [];

        this.openModelList(
            "Media WhatsApp",
            "whatsapp.media",
            domain
        );
    }

    openMediaPending() {
        this.openModelList(
            "Media pendiente de procesar",
            "whatsapp.media",
            [["is_processed", "=", false]]
        );
    }

    openHandoff() {
        const domain = this.state.selectedSession
            ? [["session_id", "=", this.state.selectedSession.id]]
            : [];

        this.openModelList(
            "Handoff humano WhatsApp",
            "whatsapp.handoff",
            domain
        );
    }

    openOpenHandoff() {
        this.openModelList(
            "Handoff humano activo",
            "whatsapp.handoff",
            [["state", "=", "open"]]
        );
    }

    // =========================================================
    // CONFIGURACIÓN
    // =========================================================

    openAutoResponses() {
        this.openModelList(
            "Auto respuestas WhatsApp",
            "whatsapp.auto.response",
            []
        );
    }

    openIntentRules() {
        this.openModelList(
            "Reglas de intención WhatsApp",
            "whatsapp.intent.rule",
            []
        );
    }

    openTemplates() {
        this.openModelList(
            "Plantillas WhatsApp",
            "whatsapp.template",
            []
        );
    }

    openBusinessHours() {
        this.openModelList(
            "Horarios WhatsApp",
            "whatsapp.business.hours",
            []
        );
    }

    openCalendar() {
        this.openModelList(
            "Calendario WhatsApp",
            "whatsapp.calendar.event",
            []
        );
    }

    // =========================================================
    // AUDITORÍA
    // =========================================================

    openLogs() {
        this.openModelList(
            "Logs API WhatsApp",
            "whatsapp.api.log",
            []
        );
    }

    openErrorLogs() {
        this.openModelList(
            "Errores API WhatsApp",
            "whatsapp.api.log",
            [["status", "=", "error"]]
        );
    }

    openUnauthorizedLogs() {
        this.openModelList(
            "No autorizados API WhatsApp",
            "whatsapp.api.log",
            [["status", "=", "unauthorized"]]
        );
    }

    // =========================================================
    // CREACIÓN RÁPIDA - OPERACIÓN
    // =========================================================

    createSession() {
        this.createRecord(
            "Nueva sesión WhatsApp",
            "whatsapp.session",
            {}
        );
    }

    createMessage() {
        const context = {};

        if (this.state.selectedSession) {
            context.default_session_id = this.state.selectedSession.id;
            context.default_partner_id = this.getMany2oneId(this.state.selectedSession.partner_id);
            context.default_company_id = this.getMany2oneId(this.state.selectedSession.active_company_id);
            context.default_phone = this.state.selectedSession.phone || "";
            context.default_jid = this.state.selectedSession.jid || "";
            context.default_lid = this.state.selectedSession.lid || "";
            context.default_raw_jid = this.state.selectedSession.raw_jid || "";
            context.default_direction = "out";
            context.default_role = "agent";
            context.default_message_type = "text";
        }

        this.createRecord(
            "Nuevo mensaje WhatsApp",
            "whatsapp.message",
            context
        );
    }

    createOutbox() {
        const context = {};

        if (this.state.selectedSession) {
            context.default_session_id = this.state.selectedSession.id;
            context.default_partner_id = this.getMany2oneId(this.state.selectedSession.partner_id);
            context.default_company_id = this.getMany2oneId(this.state.selectedSession.active_company_id);
            context.default_phone = this.state.selectedSession.phone || "";
            context.default_jid = this.state.selectedSession.jid || "";
            context.default_lid = this.state.selectedSession.lid || "";
            context.default_message_type = "text";
            context.default_state = "pending";
        }

        this.createRecord(
            "Nuevo mensaje en cola WhatsApp",
            "whatsapp.outbox",
            context
        );
    }

    createMedia() {
        const context = {};

        if (this.state.selectedSession) {
            context.default_session_id = this.state.selectedSession.id;
            context.default_partner_id = this.getMany2oneId(this.state.selectedSession.partner_id);
            context.default_company_id = this.getMany2oneId(this.state.selectedSession.active_company_id);
        }

        this.createRecord(
            "Nueva media WhatsApp",
            "whatsapp.media",
            context
        );
    }

    createHandoff() {
        const context = {};

        if (this.state.selectedSession) {
            context.default_session_id = this.state.selectedSession.id;
            context.default_partner_id = this.getMany2oneId(this.state.selectedSession.partner_id);
            context.default_company_id = this.getMany2oneId(this.state.selectedSession.active_company_id);
        }

        this.createRecord(
            "Nuevo handoff humano",
            "whatsapp.handoff",
            context
        );
    }

    // =========================================================
    // CREACIÓN RÁPIDA - CONFIGURACIÓN
    // =========================================================

    createAutoResponse() {
        this.createRecord(
            "Nueva auto respuesta WhatsApp",
            "whatsapp.auto.response",
            {
                default_active: true,
            }
        );
    }

    createIntentRule() {
        this.createRecord(
            "Nueva regla de intención WhatsApp",
            "whatsapp.intent.rule",
            {
                default_active: true,
            }
        );
    }

    createTemplate() {
        this.createRecord(
            "Nueva plantilla WhatsApp",
            "whatsapp.template",
            {
                default_active: true,
            }
        );
    }

    createBusinessHours() {
        this.createRecord(
            "Nuevo horario WhatsApp",
            "whatsapp.business.hours",
            {
                default_active: true,
            }
        );
    }

    createCalendarEvent() {
        this.createRecord(
            "Nuevo evento calendario WhatsApp",
            "whatsapp.calendar.event",
            {
                default_active: true,
            }
        );
    }

    // =========================================================
    // ACCIONES SOBRE OUTBOX
    // =========================================================

    async callOutboxMethod(outboxId, methodName, successMessage) {
        if (!outboxId) {
            return;
        }

        try {
            await this.orm.call(
                "whatsapp.outbox",
                methodName,
                [[outboxId]]
            );

            this.notifySuccess(successMessage);

            await this.loadCounters();
        } catch (error) {
            console.error(`[WhatsappInboxApp] Error ${methodName}:`, error);
            this.notifyDanger("No se pudo ejecutar la acción sobre la cola.");
        }
    }

    async markOutboxSent(outboxId) {
        await this.callOutboxMethod(
            outboxId,
            "action_mark_sent",
            "Mensaje marcado como enviado."
        );
    }

    async markOutboxFailed(outboxId) {
        await this.callOutboxMethod(
            outboxId,
            "action_mark_failed",
            "Mensaje marcado como fallido."
        );
    }

    async cancelOutbox(outboxId) {
        await this.callOutboxMethod(
            outboxId,
            "action_cancel",
            "Mensaje cancelado."
        );
    }

    // =========================================================
    // UTILIDADES DE FORMATO
    // =========================================================

    getMany2oneId(value) {
        if (Array.isArray(value) && value.length) {
            return value[0];
        }

        if (typeof value === "number") {
            return value;
        }

        return false;
    }

    getMany2oneName(value) {
        if (Array.isArray(value) && value.length > 1) {
            return value[1];
        }

        return "";
    }

    getPartnerName(session) {
        if (!session) {
            return "Sin conversación";
        }

        const partnerName = this.getMany2oneName(session.partner_id);

        if (partnerName) {
            return partnerName;
        }

        return session.phone || session.name || "Cliente WhatsApp";
    }

    getCompanyName(session) {
        if (!session) {
            return "Sin empresa";
        }

        const companyName = this.getMany2oneName(session.active_company_id);

        if (companyName) {
            return companyName;
        }

        return "Sin empresa";
    }

    getSessionSubtitle(session) {
        if (!session) {
            return "";
        }

        const phone = session.phone || "";
        const company = this.getCompanyName(session);

        if (phone && company && company !== "Sin empresa") {
            return `${phone} · ${company}`;
        }

        return phone || company || "";
    }

    getInitials(session) {
        const name = this.getPartnerName(session);

        if (!name) {
            return "WA";
        }

        const parts = name.trim().split(/\s+/).filter(Boolean);

        if (parts.length >= 2) {
            return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
        }

        return name.substring(0, 2).toUpperCase();
    }

    getStateLabel(state) {
        const labels = {
            open: "Abierta",
            human: "Modo humano",
            closed: "Cerrada",
            expired: "Expirada",
            pending: "Pendiente",
            sent: "Enviado",
            failed: "Fallido",
            cancelled: "Cancelado",
            released: "Liberado",
        };

        return labels[state] || state || "";
    }

    getStateClass(state) {
        if (state === "open") {
            return "o_wia_badge_open";
        }

        if (state === "human") {
            return "o_wia_badge_human";
        }

        if (state === "closed") {
            return "o_wia_badge_closed";
        }

        if (state === "expired") {
            return "o_wia_badge_expired";
        }

        if (state === "pending") {
            return "o_wia_badge_pending";
        }

        if (state === "sent") {
            return "o_wia_badge_sent";
        }

        if (state === "failed") {
            return "o_wia_badge_failed";
        }

        if (state === "cancelled") {
            return "o_wia_badge_cancelled";
        }

        return "";
    }

    getDirectionLabel(direction) {
        const labels = {
            in: "Cliente",
            out: "Empresa",
        };

        return labels[direction] || direction || "";
    }

    getMessageTypeLabel(type) {
        const labels = {
            text: "Texto",
            image: "Imagen",
            audio: "Audio",
            document: "Documento",
            video: "Video",
            sticker: "Sticker",
            location: "Ubicación",
            contact: "Contacto",
        };

        return labels[type] || type || "Mensaje";
    }

    getShortText(text, maxLength = 90) {
        const value = text || "";

        if (value.length <= maxLength) {
            return value;
        }

        return `${value.substring(0, maxLength)}...`;
    }

    formatDate(value) {
        if (!value) {
            return "";
        }

        return value;
    }

    isIncoming(message) {
        return message && message.direction === "in";
    }

    isOutgoing(message) {
        return message && message.direction === "out";
    }

    hasSelectedSession() {
        return !!this.state.selectedSession;
    }

    isSelectedSession(session) {
        return (
            session &&
            this.state.selectedSession &&
            session.id === this.state.selectedSession.id
        );
    }

    canReopenSelectedSession() {
        const session = this.state.selectedSession;

        if (!session) {
            return false;
        }

        return !["open", "human"].includes(session.state);
    }

    canSetHumanSelectedSession() {
        const session = this.state.selectedSession;

        if (!session) {
            return false;
        }

        return session.state !== "human";
    }

    canCloseSelectedSession() {
        const session = this.state.selectedSession;

        if (!session) {
            return false;
        }

        return !["closed", "expired"].includes(session.state);
    }

    canExpireSelectedSession() {
        const session = this.state.selectedSession;

        if (!session) {
            return false;
        }

        return !["closed", "expired"].includes(session.state);
    }
}

registry.category("actions").add("sat_whatsapp_inbox_app", WhatsappInboxApp);