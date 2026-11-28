from odoo import SUPERUSER_ID, api

from . import controllers
from . import models

DEMO_LICENSE_KEY = 'AAI-DEMO-TRIAL-KEY'


def post_init_hook(cr, registry):
    """Fresh installation: pre-fill the shared demo key, so the assistant works right away
    (with the demo limits). Customers replace it with their own key in Settings."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    params = env['ir.config_parameter'].sudo()
    if not params.get_param('aai_odoo_assistance.license_key'):
        params.set_param('aai_odoo_assistance.license_key', DEMO_LICENSE_KEY)
