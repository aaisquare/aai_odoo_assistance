from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

GROUP = 'aai_odoo_assistance.group_aai_assistant_user'


class AiAssistantController(http.Controller):

    def _check_group(self):
        if not request.env.user.has_group(GROUP):
            raise AccessError('You are not allowed to use the AI Assistant.')

    @http.route('/aai_odoo_assistance/chat', type='json', auth='user')
    def chat(self, message, conversation_id=None):
        self._check_group()
        try:
            return request.env['aai.assistant'].chat(message, conversation_id)
        except (UserError, AccessError) as e:
            return {'error': str(e)}

    @http.route('/aai_odoo_assistance/history', type='json', auth='user')
    def history(self, conversation_id=None):
        """Messages to show when the chat opens.

        - ``conversation_id`` given (e.g. "Open in new tab"): that conversation, if it is the user's own.
        - otherwise: the user's latest conversation, only when "Load Previous Conversation" is enabled
          in the settings; else nothing, so the chat starts fresh.
        """
        self._check_group()
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
