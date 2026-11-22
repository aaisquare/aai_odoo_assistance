from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """Tell the web client whether the AI Assistant is activated: the chat popup is only shown once it is."""
        info = super().session_info()
        if self.env.user._is_internal():
            info['aai_assistant_active'] = self.env['aai.client']._is_activated()
        return info
