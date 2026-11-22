import json

from odoo import api, fields, models


class AaiAssistantConversation(models.Model):
    _name = 'aai.assistant.conversation'
    _description = 'AI Assistant Conversation'
    _order = 'id desc'

    name = fields.Char(required=True, default='New conversation')
    user_id = fields.Many2one(
        'res.users', required=True, default=lambda self: self.env.user,
        index=True, ondelete='cascade', readonly=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company, readonly=True)
    message_ids = fields.One2many('aai.assistant.message', 'conversation_id')
    message_count = fields.Integer(compute='_compute_message_count')

    @api.depends('message_ids')
    def _compute_message_count(self):
        for conv in self:
            conv.message_count = len(conv.message_ids)

    def _history_for_backend(self, limit=20):
        """Last questions / answers of this conversation, sent to the backend as context."""
        self.ensure_one()
        messages = self.message_ids.filtered(lambda m: m.role in ('user', 'assistant') and m.content)
        return [{'role': m.role, 'content': m.content} for m in messages[-limit:]]


class AaiAssistantMessage(models.Model):
    """One entry of a conversation, also the audit log.

    - user / assistant: the question and the answer shown in the chat,
    - data_request: every read the AAI Square backend asked this database to run
      (model, method, arguments and how many records were returned).
    """
    _name = 'aai.assistant.message'
    _description = 'AI Assistant Message'
    _order = 'id'

    conversation_id = fields.Many2one(
        'aai.assistant.conversation', required=True, index=True, ondelete='cascade')
    user_id = fields.Many2one(related='conversation_id.user_id', store=True)
    role = fields.Selection(
        [('user', 'User'), ('assistant', 'Assistant'), ('data_request', 'Data Request')],
        required=True)
    content = fields.Text()
    request_model = fields.Char(string='Model')
    request_method = fields.Char(string='Method')
    request_details = fields.Text(help='Arguments of the data request (JSON).')
    result_count = fields.Integer(help='Number of records returned by the data request.')
    links = fields.Text(help='Buttons attached to an assistant answer (JSON).')

    def _to_ui(self):
        return {
            'id': self.id,
            'role': self.role,
            'content': self.content or '',
            'links': json.loads(self.links) if self.links else [],
            'time': fields.Datetime.to_string(self.create_date),
        }
