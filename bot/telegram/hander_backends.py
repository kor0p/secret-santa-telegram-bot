from telebot import Handler
from telebot.handler_backends import HandlerBackend

from ..models import CallbackMessage


class DjangoHandlerBackend(HandlerBackend):
    def __init__(self, *, id, handlers=None):
        super().__init__(handlers)
        self.handler_id = id

    def register_handler(self, handler_group_id, handler: Handler):
        CallbackMessage.objects.create(
            handler_id=self.handler_id,
            group_id=handler_group_id,
            fn=handler.callback,
            args=handler.args,
            kwargs=handler.kwargs,
        )

    def clear_handlers(self, handler_group_id):
        CallbackMessage.objects.filter(handler_id=self.handler_id, group_id=handler_group_id).delete()

    def get_handlers(self, handler_group_id):
        callback_messages = CallbackMessage.objects.filter(
            handler_id=self.handler_id, group_id=handler_group_id
        )
        handlers = [Handler(msg.fn, msg.args, msg.kwargs) for msg in callback_messages]
        callback_messages.delete()

        return handlers
