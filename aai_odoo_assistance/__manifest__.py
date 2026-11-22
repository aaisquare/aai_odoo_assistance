{
    'name': 'AI Assistant by AAI Square',
    'version': '18.0.1.0.0',
    'summary': 'Ask questions about your Odoo data in plain language',
    'description': """
AI Assistant by AAI Square
==========================
A chat assistant inside Odoo: ask about sales, purchases, invoices, stock,
customers and more in plain language, and get answers from your live data.

Getting started
---------------
After installing, go to **Settings > AI Assistant** and click **Activate**.
The chat window and the AI Assistant app stay hidden until the assistant is activated.
A free demo key is pre-filled; replace it with your subscription key from AAI Square
(https://aaisquare.com/) to keep using the assistant after the demo.

When you click Activate, your company name, Odoo URL, Odoo version and server name are
sent to AAI Square to register this database for the licence.
* Read-only: the assistant can only read data, always with the rights of the
  user asking, and never sees passwords, API keys or system settings.
* Every data request is recorded in Settings > AI Assistant Logs.
""",
    'category': 'Productivity',
    'author': 'AAI Square',
    'website': 'https://aaisquare.com/',
    'maintainer': 'AAI Square',
    'support': 'odoo@aaisquare.com',
    'license': 'OPL-1',
    'images': ['static/description/banner.png'],
    'depends': ['base_setup', 'web'],
    'data': [
        'security/aai_assistant_security.xml',
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/aai_assistant_conversation_views.xml',
        'views/aai_assistant_chat_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'aai_odoo_assistance/static/src/chat_widget/*',
            'aai_odoo_assistance/static/src/settings/*',
        ],
    },
    'external_dependencies': {'python': ['requests']},
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
}
