"""HTTP client for the AAI Square backend.

Every request carries the licence key and this database's UUID. Once the
licence is activated, requests are also signed (HMAC-SHA256 with the secret
returned by the activation) and timestamped, so they cannot be forged or replayed.
"""
import hashlib
import hmac
import json
import logging
import platform
import secrets
import time

import requests

from odoo import _, api, models, release
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DEFAULT_BACKEND_URL = 'https://api.aaisquare.com'
TIMEOUT = 90
MODULE_VERSION = '17.0.1.0.0'

PARAM_KEY = 'aai_odoo_assistance.license_key'
PARAM_SECRET = 'aai_odoo_assistance.client_secret'
PARAM_URL = 'aai_odoo_assistance.backend_url'
PARAM_STATUS = 'aai_odoo_assistance.license_status'


class AaiClient(models.AbstractModel):
    _name = 'aai.client'
    _description = 'AAI Square Backend Client'

    # ---------------------------------------------------------------- settings

    def _params(self):
        return self.env['ir.config_parameter'].sudo()

    def _backend_url(self):
        return (self._params().get_param(PARAM_URL) or DEFAULT_BACKEND_URL).rstrip('/')

    def _license_key(self):
        return (self._params().get_param(PARAM_KEY) or '').strip()

    @api.model
    def _is_activated(self):
        """Activated = an administrator clicked "Activate" and the backend accepted the key
        (it returned a signing secret). Until then the chat window and the app menu are hidden."""
        return bool(self._params().get_param(PARAM_SECRET))

    def _odoo_info(self):
        params = self._params()
        return {
            'db_uuid': params.get_param('database.uuid'),
            'base_url': params.get_param('web.base.url'),
            'odoo_version': release.version,
            'module_version': MODULE_VERSION,
            'hostname': platform.node(),
        }

    # ------------------------------------------------------------------- http

    def _post(self, path, payload, signed=True):
        key = self._license_key()
        if not key:
            raise UserError(_('The AI Assistant is not activated. An administrator must enter the licence key '
                              'in Settings > AI Assistant.'))
        # random nonce: every request (and so its signature) is unique, even two identical requests in the
        # same second, so the backend's replay protection never refuses a legitimate repeat
        body = json.dumps(dict(payload, nonce=secrets.token_hex(8)), default=str, separators=(',', ':'))
        timestamp = str(int(time.time()))
        headers = {
            'Content-Type': 'application/json',
            'X-AAI-License': key,
            'X-AAI-Database': self._params().get_param('database.uuid') or '',
            'X-AAI-Timestamp': timestamp,
            # server name: lets the backend notice one licensed database running on two servers
            'X-AAI-Instance': platform.node()[:100],
        }
        if signed:
            # no automatic activation: an administrator activates explicitly in Settings (that is also
            # when the installation is registered on the AAI Square side)
            secret = self._params().get_param(PARAM_SECRET)
            if not secret:
                raise UserError(_('The AI Assistant is not activated. An administrator must click "Activate" '
                                  'in Settings > AI Assistant.'))
            headers['X-AAI-Signature'] = hmac.new(
                secret.encode(), f'{timestamp}.{body}'.encode(), hashlib.sha256).hexdigest()
        url = self._backend_url() + path
        try:
            response = requests.post(url, data=body.encode(), headers=headers, timeout=TIMEOUT)
        except requests.RequestException as e:
            _logger.warning('AAI backend unreachable (%s): %s', url, e)
            raise UserError(_('The AI service cannot be reached right now. Please try again in a moment.'))
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code >= 400:
            message = data.get('message') or data.get('detail') or _('AI service error (%s).', response.status_code)
            raise UserError(message if isinstance(message, str) else json.dumps(message))
        return data

    # -------------------------------------------------------------- licence

    def activate(self):
        """Register this database with the licence key. Returns the backend's status dict."""
        payload = dict(self._odoo_info(), company_name=self.env.company.name)
        data = self._post('/v1/activate', payload, signed=False)
        params = self._params()
        if data.get('client_secret'):
            params.set_param(PARAM_SECRET, data['client_secret'])
        self._store_status(data)
        # the app menu is shown / hidden depending on the activation: rebuild the cached menus
        self.env.registry.clear_cache()
        return data

    def status(self):
        data = self._post('/v1/status', self._odoo_info())
        self._store_status(data)
        return data

    def _store_status(self, data):
        status = {k: data.get(k) for k in ('status', 'message', 'plan', 'valid_until', 'questions_left', 'company')}
        status['checked_at'] = int(time.time())
        self._params().set_param(PARAM_STATUS, json.dumps(status))

    # ------------------------------------------------------------------- chat

    def chat(self, payload):
        return self._post('/v1/chat', dict(payload, odoo=self._odoo_info()))

    def chat_continue(self, session, results):
        return self._post('/v1/chat/continue', {'session': session, 'results': results})
