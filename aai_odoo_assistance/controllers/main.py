from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

GROUP = 'aai_odoo_assistance.group_aai_assistant_user'


class AiAssistantController(http.Controller):

    def _check_group(self):
        if not request.env.user.has_group(GROUP):
            raise AccessError('You are not allowed to use the AI Assistant.')

    def _apply_context(self, context):
        """The chat window sends the web client's context: answer for the companies selected in the
        company switcher. Only companies the user belongs to are kept (the rest is ignored)."""
        selected = (context or {}).get('allowed_company_ids') or []
        user_companies = request.env.user.company_ids.ids
        allowed = [cid for cid in selected if isinstance(cid, int) and cid in user_companies]
        if allowed:
            request.update_context(allowed_company_ids=allowed)

    @http.route('/aai_odoo_assistance/chat', type='jsonrpc', auth='user')
    def chat(self, message, conversation_id=None, context=None):
        self._check_group()
        self._apply_context(context)
        try:
            return request.env['aai.assistant'].chat(message, conversation_id)
        except (UserError, AccessError) as e:
            return {'error': str(e)}

    @http.route('/aai_odoo_assistance/history', type='jsonrpc', auth='user')
    def history(self, conversation_id=None, context=None):
        """Messages to show when the chat opens.

        - ``conversation_id`` given (e.g. "Open in new tab"): that conversation, if it is the user's own.
        - otherwise: the user's latest conversation, only when "Load Previous Conversation" is enabled
          in the settings; else nothing, so the chat starts fresh.
        """
        self._check_group()
        self._apply_context(context)
        Conversation = request.env['aai.assistant.conversation']
        domain = [('user_id', '=', request.env.uid)]
        conversation = Conversation
        if conversation_id:
            conversation = Conversation.search(domain + [('id', '=', int(conversation_id))], limit=1)
        elif request.env['ir.config_parameter'].sudo().get_param('aai_odoo_assistance.load_history'):
            conversation = Conversation.search(domain, order='id desc', limit=1)
        if not conversation:
            return {'conversation_id': False, 'messages': []}
        messages = conversation.message_ids.filtered(lambda m: m.role in ('user', 'assistant') and m.content)
        return {
            'conversation_id': conversation.id,
            'messages': [m._to_ui() for m in messages],
        }
