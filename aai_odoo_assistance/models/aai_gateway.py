"""Read-only data gateway.

The AAI Square backend holds all the assistant's logic. When it needs data from
this database it sends "data requests" (model, method, arguments); this gateway
runs them and returns the raw results.

Safety rules enforced HERE, in code the customer can audit, whatever the backend asks:
  1. read-only methods only (no create / write / unlink / actions / emails),
  2. always as the logged-in user (never sudo): Odoo access rights, record rules
     and multi-company restrictions apply,
  3. sensitive models and fields are never readable (system parameters, passwords,
     API keys, credentials...), even for administrators,
  4. size limits per request and per question,
  5. every request is logged in the conversation (AI Assistant Logs).
"""
import json
import logging
import re

from odoo import _, models
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError

_logger = logging.getLogger(__name__)

# 1. read-only ORM methods the backend may call
READ_METHODS = {'search_read', 'read', 'search_count', 'read_group', 'fields_get', 'name_search',
                'check_access_rights'}
# a few safe, read-only helpers on specific models
EXTRA_METHODS = {('ir.actions.report', 'get_wkhtmltopdf_state')}

# 3. never readable, whatever the user's rights
BLOCKED_MODELS = {
    'ir.config_parameter', 'res.users.apikeys', 'res.users.apikeys.description', 'res.users.log',
    'res.users.identitycheck', 'ir.mail_server', 'fetchmail.server', 'auth.totp.device',
    'payment.provider', 'payment.token', 'iap.account', 'ir.cron', 'ir.rule', 'ir.model.access',
    'ir.attachment',  # raw file contents; documents are offered as links instead
    'aai.assistant.conversation', 'aai.assistant.message',
}
BLOCKED_MODEL_PREFIXES = ('base.', 'bus.', 'ir.actions.server', 'ir.module.module.dependency')
BLOCKED_FIELD = re.compile(r'(password|passwd|secret|token|api_?key|private_key|signature|totp|_pin$|^pin$)', re.I)

# context keys the backend may set (e.g. warehouse for stock quantities)
ALLOWED_CONTEXT_KEYS = {'warehouse', 'location', 'lang', 'tz', 'active_test', 'to_date', 'from_date',
                        'bin_size', 'pricelist', 'quantity', 'partner_id'}

# 4. limits
MAX_RECORDS = 200
MAX_REQUESTS_PER_QUESTION = 40
MAX_RESULT_CHARS = 60000


class AaiGateway(models.AbstractModel):
    _name = 'aai.gateway'
    _description = 'AI Assistant Data Gateway'

    def _run_requests(self, requests_, conversation, budget):
        """Run a batch of data requests. Returns ``[{id, ok, result | error}]``.

        ``budget`` is a dict ``{'used': int}`` shared by all batches of one question.
        """
        results = []
        for req in requests_ or []:
            req_id = req.get('id')
            if budget['used'] >= MAX_REQUESTS_PER_QUESTION:
                results.append({'id': req_id, 'ok': False, 'error': 'Too many data requests for one question.'})
                continue
            budget['used'] += 1
            try:
                with self.env.cr.savepoint():
                    result = self._run_one(req)
                text = json.dumps(result, default=str)
                if len(text) > MAX_RESULT_CHARS:
                    raise UserError(_('Result too large, narrow the request.'))
                results.append({'id': req_id, 'ok': True, 'result': result})
                self._log(conversation, req, result)
            except AccessError:
                results.append({'id': req_id, 'ok': False, 'error': 'access_denied'})
                self._log(conversation, req, None, 'access denied')
            except (UserError, ValidationError, MissingError, ValueError, TypeError, KeyError) as e:
                results.append({'id': req_id, 'ok': False, 'error': str(e)[:500]})
                self._log(conversation, req, None, str(e)[:200])
            except Exception:
                _logger.exception('AAI gateway: request failed %s', req)
                results.append({'id': req_id, 'ok': False, 'error': 'internal_error'})
        return results

    # ------------------------------------------------------------------ checks

    def _check_model(self, model):
        if not isinstance(model, str) or model not in self.env:
            raise ValueError(f'Unknown model: {model}')
        if model in BLOCKED_MODELS or model.startswith(BLOCKED_MODEL_PREFIXES):
            raise AccessError(_('This data is not available to the AI Assistant.'))
        return self.env[model]

    def _check_fields(self, Model, field_names):
        if field_names is None:
            raise ValueError('An explicit list of fields is required.')
        allowed = []
        for name in field_names:
            field = Model._fields.get(name)
            if not field:
                raise ValueError(f'Unknown field {Model._name}.{name}')
            if BLOCKED_FIELD.search(name) or field.type == 'binary':
                continue  # silently dropped: never sent
            allowed.append(name)
        return allowed

    def _safe_context(self, ctx):
        ctx = ctx or {}
        return {k: v for k, v in ctx.items() if k in ALLOWED_CONTEXT_KEYS}

    @staticmethod
    def _limit(value):
        try:
            value = int(value or MAX_RECORDS)
        except (TypeError, ValueError):
            value = MAX_RECORDS
        return max(1, min(value, MAX_RECORDS))

    # --------------------------------------------------------------- execution

    def _run_one(self, req):
        model, method = req.get('model'), req.get('method')
        kw = req.get('kwargs') or {}
        if method not in READ_METHODS and (model, method) not in EXTRA_METHODS:
            raise AccessError(_('Only reading data is allowed.'))
        Model = self._check_model(model).with_context(**self._safe_context(kw.get('context')))

        if (model, method) == ('ir.actions.report', 'get_wkhtmltopdf_state'):
            return Model.get_pdf_engine_state(Model._get_pdf_engine())
        if method == 'check_access_rights':          # name kept for the backend; Odoo 18 API: has_access
            return Model.has_access(kw.get('operation', 'read'))
        if method == 'fields_get':
            names = kw.get('fields')
            info = Model.fields_get(names, attributes=['string', 'type', 'selection', 'relation'])
            return {k: v for k, v in info.items() if not BLOCKED_FIELD.search(k)}

        Model.check_access('read')
        domain = kw.get('domain') or []
        if method == 'search_count':
            return Model.search_count(domain)
        if method == 'name_search':
            return Model.name_search(kw.get('name', ''), domain, limit=self._limit(kw.get('limit')))
        if method == 'search_read':
            return Model.search_read(domain, self._check_fields(Model, kw.get('fields')),
                                     offset=int(kw.get('offset') or 0), limit=self._limit(kw.get('limit')),
                                     order=kw.get('order'))
        if method == 'read':
            ids = [int(i) for i in (kw.get('ids') or [])][:MAX_RECORDS]
            return Model.browse(ids).read(self._check_fields(Model, kw.get('fields')))
        if method == 'read_group':
            groupby = kw.get('groupby') or []
            aggregates = kw.get('fields') or []
            for spec in aggregates + groupby:
                if BLOCKED_FIELD.search(spec.split(':')[0]):
                    raise AccessError(_('This data is not available to the AI Assistant.'))
            return self._grouped(Model, domain, aggregates, groupby, offset=int(kw.get('offset') or 0),
                                 limit=self._limit(kw.get('limit')), orderby=kw.get('orderby') or '')
        raise AccessError(_('Only reading data is allowed.'))

    def _grouped(self, Model, domain, aggregates, groupby, offset, limit, orderby):
        """Totals per group, in the classic read_group format the AAI service expects:
        ``[{<groupby>: value, <field>: aggregate, '__count': n}, ...]``.

        Odoo 20: ``read_group`` is the raw tuple API, ``formatted_read_group`` returns dicts keyed by the
        aggregate spec ('amount_total:sum'): rename them to the field ('amount_total') and translate the
        order ('amount_total desc' -> 'amount_total:sum desc').
        """
        specs = {}  # result key -> aggregate spec
        for spec in aggregates:
            name, _sep, func = spec.partition(':')
            if name == '__count':
                continue
            if not func:
                field = Model._fields.get(name)
                if not field or not field.aggregator:
                    continue
                func = field.aggregator
            specs[name] = f'{name}:{func}'
        order_terms = []
        for term in (orderby or '').split(','):
            term = term.strip()
            if not term:
                continue
            key, _sep, direction = term.partition(' ')
            order_terms.append(f'{specs.get(key, key)} {direction}'.strip())
        rows = Model.formatted_read_group(domain, groupby, list(specs.values()) + ['__count'],
                                          offset=offset, limit=limit, order=', '.join(order_terms) or None)
        result = []
        for row in rows:
            group = {spec: row.get(spec) for spec in groupby}
            group.update({name: row.get(spec) for name, spec in specs.items()})
            group['__count'] = row.get('__count', 0)
            result.append(group)
        return result

    # ------------------------------------------------------------------ logging

    def _log(self, conversation, req, result, error=None):
        if not conversation:
            return
        count = len(result) if isinstance(result, list) else (1 if result not in (None, False) else 0)
        details = {k: v for k, v in (req.get('kwargs') or {}).items() if k != 'context'}
        self.env['aai.assistant.message'].create({
            'conversation_id': conversation.id,
            'role': 'data_request',
            'content': error or '',
            'request_model': req.get('model'),
            'request_method': req.get('method'),
            'request_details': json.dumps(details, default=str)[:4000],
            'result_count': count,
        })
