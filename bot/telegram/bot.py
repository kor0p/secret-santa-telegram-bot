import os
import json
import logging
from typing import Union, Callable, Optional

from django.db import DatabaseError
from telebot import TeleBot, types, logger
from telebot.apihelper import ApiException, ApiTelegramException

from .handler_backends import DjangoHandlerBackend
from .utils import JSON_COMMON_DATA, get_trans
from ..models import Message, User

logger.setLevel(logging.DEBUG)


CallbackDataType = Union[str, dict[str, JSON_COMMON_DATA]]  # parsed json data


class ExtraTeleBot(TeleBot):
    callback_query_handlers: dict[str, CallbackDataType]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.callback_query_handlers = {}
        self.pending_callback_ids = set()

    def callback_query_handler(self, func: Callable[[types.CallbackQuery, Optional[CallbackDataType]], None], **kwargs):
        return super().callback_query_handler(func, **kwargs)

    def add_callback_query_handler(self, handler_dict: dict):
        self.callback_query_handlers[handler_dict['filters']['func'].value[0]] = handler_dict['function']

    def process_new_callback_query(self, messages: list[types.CallbackQuery, ...]):
        for message in messages:
            Message.add_tg_message(message)
            self.pending_callback_ids.add(message.id)
            try:
                _type, *callback_data = json.loads(message.data)
                if _type not in self.callback_query_handlers:
                    continue
                if callback_data:
                    callback_data = callback_data[0]
            except json.JSONDecodeError:
                continue

            user = User.create_from_tg(message.from_user)[0]
            _ = get_trans(user.language_code)
            args = [user, _]
            kwargs = {}
            if isinstance(callback_data, dict):
                kwargs.update(callback_data)
            else:
                args.extend(callback_data)

            try:
                self._exec_task(self.callback_query_handlers[_type], message, *args, **kwargs)
            except (ApiException, DatabaseError, AttributeError):  # try to send error to user
                logger.exception('1')
                try:
                    self.answer_callback_query(message.id, _('Server Error'))
                except ApiTelegramException:
                    logger.exception('2')
            finally:  # if there was error, just answer callback to remove it from queue
                try:
                    self.answer_callback_query(message.id)
                except ApiTelegramException:  # if callback is too old
                    logger.exception('3')

    def answer_callback_query(
        self,
        callback_query_id: Union[str, int],
        text: Optional[str] = None,
        show_alert: Optional[bool] = None,
        url: Optional[str] = None,
        cache_time: Optional[int] = None,
    ) -> bool:
        if callback_query_id not in self.pending_callback_ids:
            return True

        success = super().answer_callback_query(callback_query_id, text, show_alert, url, cache_time)
        if success:
            self.pending_callback_ids.remove(callback_query_id)

        return success

    def process_new_messages(self, new_messages: list[types.Message, ...]):
        for message in new_messages:
            Message.add_tg_message(message)
        super().process_new_messages(new_messages)

    def send_message(self, chat_id, *args, **kwargs) -> tuple[types.Message, Message]:
        message = None
        db_message = None
        try:
            message = super().send_message(chat_id, *args, **kwargs)
            db_message = Message.add_tg_message(message)
        except ApiTelegramException as e:
            print(e)
            pass

        if isinstance(chat_id, int):
            # message.id is None - unsuccessful message - bot is blocked by user
            User.objects.get(user_id=chat_id).update(bot_can_message=message is not None and message.id is not None)

        return message, db_message

    def send_photo(self, chat_id, *args, **kwargs) -> tuple[types.Message, Message]:
        message = None
        db_message = None
        try:
            message = super().send_photo(chat_id, *args, **kwargs)
            db_message = Message.add_tg_message(message)
        except ApiTelegramException as e:
            print(e)
            pass

        if isinstance(chat_id, int):
            # message.id is None - unsuccessful message - bot is blocked by user
            User.objects.get(user_id=chat_id).update(bot_can_message=message is not None and message.id is not None)

        return message, db_message

    def edit_message_text(self, *args, **kwargs) -> Union[types.Message, bool]:
        try:
            message = super().edit_message_text(*args, **kwargs)
            if not isinstance(message, bool):
                Message.add_tg_message(message)
            return message
        except ApiTelegramException:
            return False

    def edit_message_media(self, *args, **kwargs) -> Union[types.Message, bool]:
        try:
            return super().edit_message_media(*args, **kwargs)
        except ApiTelegramException:
            return False

    def copy_message(self, *args, **kwargs):
        message: types.MessageID = super().copy_message(*args, **kwargs)
        return message.message_id

    def _notify_next_handlers(self, new_messages):
        for i, message in enumerate(new_messages):
            if getattr(message, 'text', '').startswith('/'):
                continue

            need_pop = False
            handlers = self.next_step_backend.get_handlers(message.chat.id)
            if handlers:
                for handler in handlers:
                    need_pop = True
                    self._exec_task(handler["callback"], message, *handler["args"], **handler["kwargs"])
            if need_pop:
                new_messages.pop(i)  # removing message that was detected with next_step_handler

    def _notify_command_handlers(self, handlers, new_messages):
        if len(handlers) == 0:
            return
        for message in new_messages:
            Message.add_tg_message(message)
            if hasattr(message, 'chat'):
                self.clear_step_handler_by_chat_id(message.chat.id)
            for message_handler in handlers:
                if self._test_message_handler(message_handler, message):
                    user = User.create_from_tg(message.from_user)[0]
                    self._exec_task(message_handler['function'], message, user, get_trans(user.language_code))
                    break

    def register_next(self, chat_id: Union[int, str], callback: Callable, *args, **kwargs):
        return self.register_next_step_handler_by_chat_id(chat_id, callback, *args, **kwargs)

    def register_reply(self, message_id: int, callback: Callable, *args, **kwargs):
        return self.register_for_reply_by_message_id(message_id, callback, *args, **kwargs)


bot = ExtraTeleBot(
    os.environ.get('BOT_TOKEN'),
    parse_mode='HTML',
    num_threads=10,
    next_step_backend=DjangoHandlerBackend(id=0),
    reply_backend=DjangoHandlerBackend(id=1),
)
bot_user = bot.get_me()
