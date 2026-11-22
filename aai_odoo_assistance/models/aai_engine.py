"""Relay between the chat window and the AAI Square backend.

No AI logic lives here: the question goes to the backend, the backend replies
either with data requests (run by aai.gateway, read-only) or with the final
answer, which is stored and shown.
"""
import json
import re

from odoo import _, fields, models
from odoo.exceptions import UserError

MAX_ROUNDS = 15                       # backend <-> Odoo round trips for one question
SAFE_URL = re.compile(r'^(/(?!/)|https?://)', re.I)   # relative Odoo URL or http(s); never javascript:


class AaiAssistant(models.AbstractModel):
    _name = 'aai.assistant'
    _description = 'AI Assistant'

    def chat(self, user_message, conversation_id=None):
        user_message = (user_message or '').strip()
        if not user_message:
            raise UserError(_('Please type a question.'))

        Conversation = self.env['aai.assistant.conversation']
        conversation = Conversation.browse(conversation_id).exists() if conversation_id else Conversation
        if conversation:
            conversation.check_access_rule('write')
            history = conversation._history_for_backend()
        else:
            conversation = Conversation.create({'name': user_message[:60]})
            history = []
        self.env['aai.assistant.message'].create({
            'conversation_id': conversation.id, 'role': 'user', 'content': user_message})

        try:
            return self._relay(conversation, user_message, history)
        except UserError as e:
            # backend unreachable, licence problem...: keep the conversation, show the reason
            return {'conversation_id': conversation.id, 'error': str(e)}

    def _relay(self, conversation, user_message, history):
        client = self.env['aai.client']
        gateway = self.env['aai.gateway']
        budget = {'used': 0}
        response = client.chat({
            'conversation_id': str(conversation.id),
            'message': user_message,
            'history': history,
            'user': self._user_info(),
        })
        for _round in range(MAX_ROUNDS):
            kind = response.get('type')
            if kind == 'data_requests':
                results = gateway._run_requests(response.get('requests'), conversation, budget)
                response = client.chat_continue(response.get('session'), results)
                continue
            if kind == 'answer':
                return self._store_answer(conversation, response)
            # blocked (licence / limits) or error: show the backend's message
            return {'conversation_id': conversation.id,
                    'error': response.get('message') or _('The AI service could not answer.')}
        return {'conversation_id': conversation.id,
                'error': _('This question needed too many steps. Please ask something more specific.')}

    # ---------------------------------------------------------------- helpers

    def _user_info(self):
        user, company = self.env.user, self.env.company
        return {
            'id': user.id,
            'name': user.name,
            'lang': user.lang,
            'tz': user.tz or 'UTC',
            'company': company.name,
            'company_ids': self.env.companies.ids,
            'currency': company.currency_id.name,
            'today': fields.Date.to_string(fields.Date.context_today(self)),
            'installed_modules': self._installed_modules(),
        }

    def _installed_modules(self):
        return self.env['ir.module.module'].sudo().search([('state', '=', 'installed')]).mapped('name')

    def _store_answer(self, conversation, response):
        content = (response.get('content') or '').strip() or _('Sorry, I could not find an answer.')
        links = [
            {'label': str(link.get('label') or '')[:120], 'url': link['url'],
             'type': 'pdf' if link.get('type') == 'pdf' else 'record'}
            for link in (response.get('links') or [])
            if isinstance(link, dict) and isinstance(link.get('url'), str) and SAFE_URL.match(link['url'])
        ]
        message = self.env['aai.assistant.message'].create({
            'conversation_id': conversation.id,
            'role': 'assistant',
            'content': content,
            'links': json.dumps(links) if links else False,
        })
        return {'conversation_id': conversation.id, 'message': message._to_ui()}
