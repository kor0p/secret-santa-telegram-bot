import os
import json

from .bot import bot


admin_users = json.loads(os.environ.get('ADMIN_IDS'))


bot.enable_save_next_step_handlers(delay=2)
bot.load_next_step_handlers()
