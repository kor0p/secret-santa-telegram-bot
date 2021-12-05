from __future__ import annotations

import json
from typing import Union, Optional

from django.db.models import (
    Manager,
    Model,
    DO_NOTHING,
    QuerySet,
    Min,
    ForeignKey,
    OneToOneField,
    BigIntegerField,
    BooleanField,
    CharField,
    JSONField,
)
from django.contrib.auth import get_user_model
from django.utils.safestring import mark_safe

from telebot import types

from .telegram.utils import html_user_url, random_str


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        try:
            return super().default(obj)
        except TypeError:
            if hasattr(obj, 'to_dict'):
                dct = obj.to_dict()
            else:
                dct = obj.__dict__
            dct.pop('json', 0)
            return dct


BaseUser = get_user_model()

NOT_REQUIRED = dict(null=True, blank=True)


class BaseManager(Manager):
    def get(self, **kwargs) -> Optional[Base]:
        try:
            return super().get(**kwargs)
        except self.model.DoesNotExist:
            return None


class Base(Model):
    objects = BaseManager()

    class Meta:
        abstract = True

    def update(self, **kwargs) -> Base:
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.save(update_fields=tuple(kwargs.keys()))
        return self


class NonTgOrderedUserManager(BaseManager):
    def get_queryset(self):
        qs = super().get_queryset()
        return qs.order_by('is_telegram_user', 'full_name')


class User(Base):
    objects = NonTgOrderedUserManager()

    is_bot = BooleanField(default=False)
    full_name = CharField(**NOT_REQUIRED, max_length=256)
    username = CharField(**NOT_REQUIRED, max_length=256)
    language_code = CharField(**NOT_REQUIRED, max_length=10)
    bot_can_message = BooleanField(default=True)
    is_telegram_user = BooleanField(default=True)

    user = OneToOneField(BaseUser, on_delete=DO_NOTHING, related_name='tg_user', primary_key=True)
    messages: QuerySet[Message]

    def __str__(self):
        return mark_safe(self.full_name + (f'<i> (з телеграму: {self.to_html()})</i>' if self.is_telegram_user else ''))

    def to_html(self):
        return html_user_url(self.user)

    @classmethod
    def create_from_tg(cls, user: types.User):
        username = user.username or f'__{user.id}'

        return cls.objects.update_or_create(
            is_bot=user.is_bot,
            user=BaseUser.objects.update_or_create(
                id=user.id,
                defaults=dict(
                    first_name=user.first_name,
                    last_name=user.last_name or '',
                    username=username,
                ),
            )[0],
            defaults=dict(
                username=username,
                full_name=user.full_name,
                language_code=user.language_code if not user.is_bot else 'BOT',
            ),
        )

    @classmethod
    def create_new_auth_user(cls, **kwargs):
        min_id = BaseUser.objects.annotate(min_id=Min('id')).values()[0]['min_id']
        # custom users will have negative ids :)

        return BaseUser.objects.create(
            id=min(0, min_id) - 1,
            username='__' + random_str(50),
            **kwargs,
        )

    class Meta:
        ordering = ['full_name']


class Message(Base):
    message_id = BigIntegerField()
    date = BigIntegerField()
    user = ForeignKey(User, on_delete=DO_NOTHING, related_name='messages')
    content_type = CharField(max_length=64)
    data = JSONField(encoder=JSONEncoder)

    def __str__(self):
        return mark_safe(f'{self.message_id} - {self.content_type} by {self.user.to_html()}')

    class Meta:
        ordering = ['message_id']
        unique_together = ['message_id', 'user']

    @classmethod
    def add_tg_message(cls, message: Union[types.Message, types.CallbackQuery]) -> Message:
        _date = getattr(message, 'message', message).date
        return cls.objects.update_or_create(
            message_id=message.id,
            date=_date,
            user=User.create_from_tg(message.from_user)[0],
            defaults=dict(
                content_type=getattr(message, 'content_type', 'callback_query'),
                data=getattr(message, 'json', message.__dict__),
            ),
        )[0]
