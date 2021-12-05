import os
import json
import logging
from typing import Union, Callable, Optional

from django.db import DatabaseError
from telebot import TeleBot, types, logger
from telebot.apihelper import ApiException, ApiTelegramException

from .utils import JSON_COMMON_DATA
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
        self.callback_query_handlers[handler_dict['filters']['func'].name] = handler_dict['function']

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

            args = ()
            kwargs = dict(user=User.create_from_tg(message.from_user)[0])
            if isinstance(callback_data, dict):
                kwargs.update(callback_data)
            else:
                args = callback_data

            try:
                self._exec_task(self.callback_query_handlers[_type], message, *args, **kwargs)
            except (ApiException, DatabaseError, AttributeError):  # try to send error to user
                logger.exception('1')
                try:
                    self.answer_callback_query(message.id, 'Помилка серверу')
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


bot = ExtraTeleBot(os.environ.get('BOT_TOKEN'), threaded=False)
