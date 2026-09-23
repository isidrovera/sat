# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SatAutomationDeduplication(models.AbstractModel):
    _name = "sat.automation.deduplication"
    _description = "Motor de deduplicación SAT"

    @api.model
    def find_related_events(self, event, hours=24, event_types=None, states=None):
        if not event:
            return self.env["sat.automation.event"]

        base_dt = event.event_datetime or fields.Datetime.now()
        dt_from = fields.Datetime.subtract(base_dt, hours=int(hours or 24))
        dt_to = fields.Datetime.add(base_dt, hours=int(hours or 24))

        domain = [
            ("id", "!=", event.id),
            ("event_datetime", ">=", dt_from),
            ("event_datetime", "<=", dt_to),
        ]

        if event.equipment_id:
            domain.append(("equipment_id", "=", event.equipment_id.id))
        elif event.serial_number:
            domain.append(("serial_number", "=ilike", event.serial_number.strip()))
        else:
            return self.env["sat.automation.event"]

        if event_types:
            domain.append(("event_type", "in", event_types))
        if states:
            domain.append(("state", "in", states))

        records = self.env["sat.automation.event"].search(
            domain, order="event_datetime desc, id desc"
        )

        _logger.info(
            "[SAT AUTOMATION][DEDUP] event_id=%s related_ids=%s",
            event.id, records.ids,
        )
        return records

    @api.model
    def find_event_with_action(self, event, hours=24, event_types=None):
        related = self.find_related_events(
            event,
            hours=hours,
            event_types=event_types,
            states=["new", "classified", "processing", "review", "done"],
        )
        for rec in related:
            if rec.action_model and rec.action_record_id:
                return rec
        return self.env["sat.automation.event"]
