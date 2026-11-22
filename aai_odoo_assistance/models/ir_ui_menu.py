from odoo import models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _aai_hidden_root(self):
        """The "AI Assistant" app menu while the assistant is not activated, else an empty recordset.
        The menu cache is cleared on activation / key change, see aai.client.activate()."""
        if self.env['aai.client']._is_activated():
            return self.browse()
        return self.env.ref('aai_odoo_assistance.menu_aai_assistant_root', raise_if_not_found=False) or self.browse()

    def _load_menus_blacklist(self):
        """Odoo 19 builds the app list in ``load_menus`` from all visible menus minus this blacklist:
        hide the "AI Assistant" app (and so its sub-menus) until an administrator activates it in Settings.
        (Toggling the menu's ``active`` flag would not last: Odoo resets it on every module upgrade.)"""
        return list(super()._load_menus_blacklist()) + self._aai_hidden_root().ids

    def get_user_roots(self):
        """Same for the root menus list (``load_menus_root``)."""
        return super().get_user_roots() - self._aai_hidden_root()
