from odoo import models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def get_user_roots(self):
        """Hide the "AI Assistant" app (a top-level menu) until an administrator has activated it in Settings.

        Notes: ``_load_menus_blacklist`` only filters sub-menus (top-level apps are always re-added), and
        toggling the menu's ``active`` flag would not last (Odoo resets it on every module upgrade).
        The menu cache is cleared on activation / key change, see aai.client.activate().
        """
        roots = super().get_user_roots()
        if not self.env['aai.client']._is_activated():
            menu = self.env.ref('aai_odoo_assistance.menu_aai_assistant_root', raise_if_not_found=False)
            if menu:
                roots -= menu
        return roots
