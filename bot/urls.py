from django.contrib import admin
from django.urls import path

from .views import BotAPIView
from .telegram.bot import bot

urlpatterns = [
    path('admin/', admin.site.urls),
    path(bot.token, BotAPIView.as_view()),
]
