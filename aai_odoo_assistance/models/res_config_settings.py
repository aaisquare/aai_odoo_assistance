import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .aai_client import PARAM_KEY, PARAM_SECRET, PARAM_STATUS

STATUS_LABELS = {
    'active': 'Active',
    'expired': 'Expired',
    'inactive': 'Inactive',
    'invalid': 'Invalid key',
    'bound_elsewhere': 'Key already used by another database',
    'limit_reached': 'Usage limit reached',
}


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    aai_license_key = fields.Char(string='Licence Key', config_parameter=PARAM_KEY)
    aai_backend_url = fields.Char(string='AI Service URL', config_parameter='aai_odoo_assistance.backend_url',
                                  help='Leave empty to use the AAI Square service.')
    aai_load_history = fields.Boolean(
        string='Load Previous Conversation', config_parameter='aai_odoo_assistance.load_history',
        help="When opening the chat, show the user's last conversation instead of starting a new one.")

    aai_status = fields.Char(string='Licence Status', compute='_compute_aai_status')
    aai_status_message = fields.Char(compute='_compute_aai_status')
    aai_plan = fields.Char(string='Plan', compute='_compute_aai_status')
    aai_valid_until = fields.Char(string='Valid Until', compute='_compute_aai_status')
    aai_questions_left = fields.Char(string='Questions Left', compute='_compute_aai_status')
    aai_is_active = fields.Boolean(compute='_compute_aai_status')
    aai_is_activated = fields.Boolean(compute='_compute_aai_status',
                                      help='An administrator activated the assistant: the chat is visible.')
    aai_key_changed = fields.Boolean(compute='_compute_aai_key_changed',
                                     help='The key in the form differs from the saved one: it must be activated.')

    @api.depends('aai_license_key')
    def _compute_aai_status(self):
        raw = self.env['ir.config_parameter'].sudo().get_str(PARAM_STATUS)
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            data = {}
        activated = self.env['aai.client']._is_activated()
        for settings in self:
            settings.aai_is_activated = activated
            status = data.get('status')
            settings.aai_is_active = status == 'active'
            settings.aai_status = STATUS_LABELS.get(status, status or _('Not activated'))
            settings.aai_status_message = data.get('message') or False
            settings.aai_plan = data.get('plan') or False
            settings.aai_valid_until = data.get('valid_until') or False
            left = data.get('questions_left')
            if left is not None:
                settings.aai_questions_left = str(left)
            else:
                # active plan without a question limit (Starter / Pro)
                settings.aai_questions_left = _('Unlimited') if status == 'active' else False

    @api.depends('aai_license_key')
    def _compute_aai_key_changed(self):
        saved = (self.env['ir.config_parameter'].sudo().get_str(PARAM_KEY) or '').strip()
        for settings in self:
            settings.aai_key_changed = (settings.aai_license_key or '').strip() != saved

    def set_values(self):
        params = self.env['ir.config_parameter'].sudo()
        old_key = (params.get_str(PARAM_KEY) or '').strip()
        super().set_values()
        if (self.aai_license_key or '').strip() != old_key:
            # a new key must be activated again: forget the old secret and status (hides the chat until then)
            params.set_str(PARAM_SECRET, False)
            params.set_str(PARAM_STATUS, False)
            self.env.transaction.invalidate_ormcache('default')   # app menu visibility

    def action_aai_activate(self):
        self.set_values()
        if not (self.aai_license_key or '').strip():
            raise UserError(_('Enter the licence key first.'))
        data = self.env['aai.client'].activate()
        return self._aai_notify(data)

    def action_aai_check_status(self):
        self.set_values()
        data = self.env['aai.client'].status()
        return self._aai_notify(data)

    def _aai_notify(self, data):
        """Reload the page (the chat button / app appear after a reload), come back to the AI Assistant
        settings tab and show the result there (see static/src/settings/settings_reload.js)."""
        ok = data.get('status') == 'active'
        return {
            'type': 'ir.actions.client',
            'tag': 'aai_odoo_assistance.reload_settings',
            'params': {
                'title': _('AI Assistant activated') if ok else _('AI Assistant not active'),
                'message': data.get('message') or STATUS_LABELS.get(data.get('status'), ''),
                'type': 'success' if ok else 'warning',
            },
        }
