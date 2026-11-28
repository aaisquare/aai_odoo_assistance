/** @odoo-module **/
/**
 * After "Activate" / "Check Status" in Settings > AI Assistant the page must reload (the chat button and the
 * AI Assistant app only appear after a reload). A plain reload would land on the first settings tab and lose
 * the result message, so:
 *   1. the server returns the client action "aai_odoo_assistance.reload_settings" with the message,
 *   2. it remembers "open the AI Assistant tab + show this message" in sessionStorage and reloads,
 *   3. the settings page, once reloaded, opens the AI Assistant tab and shows the message.
 */
import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { onMounted } from "@odoo/owl";
import { SettingsFormController } from "@web/webclient/settings_form_view/settings_form_controller";

const STORAGE_KEY = "aai_odoo_assistance.after_reload";

registry.category("actions").add("aai_odoo_assistance.reload_settings", (env, action) => {
    try {
        browser.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(action.params || {}));
    } catch {
        // storage unavailable: the reload still happens, only the tab / message are lost
    }
    browser.location.reload();
});

patch(SettingsFormController.prototype, "aai_odoo_assistance.settings_reload", {
    setup() {
        this._super(...arguments);
        let pending = null;
        try {
            pending = JSON.parse(browser.sessionStorage.getItem(STORAGE_KEY) || "null");
            browser.sessionStorage.removeItem(STORAGE_KEY);
        } catch {
            pending = null;
        }
        if (!pending) {
            return;
        }
        this.initialApp = "aai_odoo_assistance";
        const notification = useService("notification");
        onMounted(() => {
            if (pending.message || pending.title) {
                notification.add(pending.message || "", {
                    title: pending.title || "",
                    type: pending.type || "info",
                });
            }
        });
    },
});
