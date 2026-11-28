/** @odoo-module **/

import { Component, markup, onWillStart, useEffect, useExternalListener, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { session } from "@web/session";
import { escape } from "@web/core/utils/strings";
import { linkify, renderMarkdown } from "./markdown";

const GROUP = "aai_odoo_assistance.group_aai_assistant_user";
const PAGE_ACTION = "aai_odoo_assistance.action_aai_assistant_chat";
const URL_PARAM = "ai_conversation";
const { DateTime } = luxon;

const SUGGESTION_GROUPS = [
    {
        title: _t("Sales"),
        icon: "fa-shopping-cart",
        items: [_t("Show me all pending quotations"), _t("Top 5 customers this month")],
    },
    {
        title: _t("Purchases"),
        icon: "fa-truck",
        items: [_t("Which purchase orders are waiting for vendor bills?")],
    },
    {
        title: _t("Accounting"),
        icon: "fa-money",
        items: [_t("Which customers have overdue payments?")],
    },
    {
        title: _t("Inventory"),
        icon: "fa-cubes",
        items: [_t("Which deliveries are late?"), _t("How much stock do we have of product…")],
    },
    {
        title: _t("Customers"),
        icon: "fa-users",
        items: [_t("Show me the profile of customer…")],
    },
];

let nextLocalId = 1;

/**
 * The AI Assistant chat.
 *
 * Used in two places:
 *  - as a floating popup (bottom-right launcher) on every backend screen,
 *  - as a full page (client action), opened in a new browser tab from the popup.
 */
export class AiAssistantChat extends Component {
    static template = "aai_odoo_assistance.ChatWidget";
    static props = {
        fullPage: { type: Boolean, optional: true },
    };

    setup() {
        this.rpc = useService("rpc");
        this.user = useService("user");
        this.notification = useService("notification");
        this.suggestionGroups = SUGGESTION_GROUPS;
        this.state = useState({
            allowed: false,
            open: Boolean(this.props.fullPage),
            expanded: false,
            loaded: false,
            loading: false,
            input: "",
            conversationId: false,
            messages: [],
        });
        this.listRef = useRef("list");
        this.inputRef = useRef("input");

        onWillStart(async () => {
            // hidden until an administrator activates the assistant in Settings (see ir_http.session_info)
            this.activated = Boolean(session.aai_assistant_active);
            this.state.allowed = this.activated && (await this.user.hasGroup(GROUP));
            if (this.props.fullPage && this.state.allowed) {
                const fromUrl = parseInt(new URLSearchParams(window.location.search).get(URL_PARAM));
                await this._loadHistory(fromUrl || false);
            }
        });

        // welcome screen: start at the top; conversation: follow the latest message
        useEffect(
            () => {
                const el = this.listRef.el;
                if (el) {
                    const empty = !this.state.messages.length && !this.state.loading;
                    el.scrollTo({ top: empty ? 0 : el.scrollHeight, behavior: "smooth" });
                }
            },
            () => [this.state.open, this.state.messages.length, this.state.loading]
        );

        useEffect(
            () => {
                if (this.props.fullPage && this.state.allowed) {
                    this._focusInput();
                }
            },
            () => []
        );

        useExternalListener(window, "keydown", (ev) => {
            if (ev.key === "Escape" && this.state.open && !this.props.fullPage) {
                this.state.open = false;
            }
        });
    }

    // ----------------------------------------------------------- getters

    get userAvatar() {
        return `/web/image/res.users/${this.user.userId}/avatar_128`;
    }

    get firstName() {
        return (this.user.name || "").split(" ")[0];
    }

    get canSend() {
        return !this.state.loading && this.state.input.trim().length > 0;
    }

    renderContent(msg) {
        if (msg.role === "assistant") {
            return renderMarkdown(msg.content);
        }
        if (msg.role === "error") {
            // service messages (demo used up, licence expired...) may contain a link: make it clickable
            return markup(linkify(escape(msg.content || "")));
        }
        return msg.content;
    }

    formatTime(msg) {
        if (!msg.time) {
            return "";
        }
        const dt = msg.time;
        return dt.hasSame(DateTime.local(), "day")
            ? dt.toLocaleString(DateTime.TIME_SIMPLE)
            : dt.toLocaleString({ month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
    }

    pdfLinks(msg) {
        return (msg.links || []).filter((l) => l.type !== "record");
    }

    recordLinks(msg) {
        return (msg.links || []).filter((l) => l.type === "record");
    }

    // ----------------------------------------------------------- network

    async _call(route, params = {}) {
        // pass the user context so the active companies are honoured
        // silent: the chat shows its own "typing" dots; without it Odoo greys out the whole screen
        // ("Loading...") when an answer takes more than 3 seconds
        return this.rpc(route, { ...params, context: this.user.context }, { silent: true });
    }

    async _loadHistory(conversationId = false) {
        this.state.loaded = true;
        try {
            const res = await this._call("/aai_odoo_assistance/history", { conversation_id: conversationId });
            this.state.conversationId = res.conversation_id;
            this.state.messages = res.messages.map((m) => this._makeMessage(m));
        } catch {
            // history is a convenience, the chat still works without it
        }
    }

    _makeMessage(values) {
        return {
            id: `local_${nextLocalId++}`,
            links: [],
            ...values,
            time: values.time ? deserializeDateTime(values.time) : DateTime.local(),
        };
    }

    // ----------------------------------------------------------- actions

    async toggle() {
        if (this.props.fullPage) {
            return;
        }
        this.state.open = !this.state.open;
        if (this.state.open && !this.state.loaded) {
            await this._loadHistory();
        }
        if (this.state.open) {
            this._focusInput();
        }
    }

    toggleExpand() {
        this.state.expanded = !this.state.expanded;
    }

    openInNewTab() {
        const query = this.state.conversationId ? `?${URL_PARAM}=${this.state.conversationId}` : "";
        window.open(`/web${query}#action=${PAGE_ACTION}`, "_blank", "noopener");
        this.state.open = false;
    }

    newChat() {
        if (this.state.loading) {
            return;
        }
        this.state.conversationId = false;
        this.state.messages = [];
        this.state.input = "";
        if (this.props.fullPage) {
            this._setUrlConversation(false);
        }
        this._focusInput();
    }

    async copy(msg) {
        try {
            await navigator.clipboard.writeText(msg.content);
            this.notification.add(_t("Answer copied to clipboard"), { type: "success" });
        } catch {
            this.notification.add(_t("Could not copy the answer"), { type: "warning" });
        }
    }

    onInput() {
        this._autoResize();
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) {
            ev.preventDefault();
            this.send();
        }
    }

    useSuggestion(text) {
        if (text.endsWith("…")) {
            // template question: let the user finish it
            this.state.input = text.slice(0, -1);
            this._focusInput();
            return;
        }
        this.state.input = text;
        this.send();
    }

    async send() {
        const text = this.state.input.trim();
        if (!text || this.state.loading) {
            return;
        }
        this.state.input = "";
        this._autoResize();
        this.state.messages.push(this._makeMessage({ role: "user", content: text }));
        this.state.loading = true;
        try {
            const res = await this._call("/aai_odoo_assistance/chat", {
                message: text,
                conversation_id: this.state.conversationId,
            });
            if (res.error) {
                this._pushError(res.error);
            } else {
                this.state.conversationId = res.conversation_id;
                this.state.messages.push(this._makeMessage(res.message));
                if (this.props.fullPage) {
                    this._setUrlConversation(res.conversation_id);
                }
            }
        } catch (e) {
            this._pushError(e.data?.message || e.message || _t("Something went wrong. Please try again."));
        } finally {
            this.state.loading = false;
            this._focusInput();
        }
    }

    // ----------------------------------------------------------- helpers

    _pushError(message) {
        this.state.messages.push(this._makeMessage({ role: "error", content: message }));
    }

    _focusInput() {
        setTimeout(() => this.inputRef.el?.focus());
    }

    _autoResize() {
        const el = this.inputRef.el;
        if (el) {
            setTimeout(() => {
                el.style.height = "auto";
                el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
            });
        }
    }

    /** Keep the full-page URL pointing at the current conversation (reload / bookmark). */
    _setUrlConversation(conversationId) {
        const url = new URL(window.location.href);
        if (conversationId) {
            url.searchParams.set(URL_PARAM, conversationId);
        } else {
            url.searchParams.delete(URL_PARAM);
        }
        window.history.replaceState(window.history.state, "", url);
    }
}

/** Full-page version, opened as a client action (e.g. in a new browser tab). */
export class AiAssistantChatPage extends Component {
    static template = "aai_odoo_assistance.ChatPage";
    static components = { AiAssistantChat };
    static props = ["*"];
}

registry.category("main_components").add("aai_odoo_assistance.ChatWidget", { Component: AiAssistantChat });
registry.category("actions").add("aai_odoo_assistance.chat_page", AiAssistantChatPage);
