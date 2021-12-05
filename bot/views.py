import os
from time import sleep

from django.http import HttpResponse
from django.views.generic import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from telebot import types

from .telegram.handlers import bot  # make sure handlers is registered


@method_decorator(csrf_exempt, name='dispatch')
class BotAPIView(View):
    def head(self, request, *args, **kwargs):
        return HttpResponse()

    def get(self, request, *args, **kwargs):
        bot.remove_webhook()
        sleep(2)  # wait for telegram can get new request
        bot.set_webhook(
            url=os.environ.get('HOSTNAME') + bot.token,
            drop_pending_updates=request.GET.get('drop_pending_updates', False),
        )

        return HttpResponse('Webhook set')

    def delete(self, request, *args, **kwargs):
        bot.remove_webhook()

        return HttpResponse('Webhook deleted')

    def post(self, request, *args, **kwargs):
        bot.process_new_updates([types.Update.de_json(request.body.decode())])

        return HttpResponse('', status=204)
