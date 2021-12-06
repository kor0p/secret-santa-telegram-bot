from __future__ import annotations

import json
from typing import Union, Optional

from django.db.models import (
    Manager,
    Model,
    DO_NOTHING,
    SET_NULL,
    QuerySet,
    Min,
    ForeignKey,
    OneToOneField,
    BigIntegerField,
    PositiveSmallIntegerField as TinyInt,
    BooleanField,
    CharField,
    TextField,
    JSONField,
)
from django.contrib.auth.models import AbstractUser
from django.utils.safestring import mark_safe
from picklefield.fields import PickledObjectField

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

NOT_REQUIRED = dict(null=True, blank=True)


class ReverseRelationQuerySet(QuerySet):
    def add(self, *objs: Base, bulk: bool = False):
        ...


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


class AuthUser(AbstractUser):
    id = BigIntegerField(primary_key=True)


class User(Base):
    is_bot = BooleanField(default=False)
    full_name = CharField(**NOT_REQUIRED, max_length=256)
    username = CharField(**NOT_REQUIRED, max_length=256)
    language_code = CharField(**NOT_REQUIRED, max_length=10)
    bot_can_message = BooleanField(default=True)
    is_telegram_user = BooleanField(default=True)

    active_participant = OneToOneField('Participant', **NOT_REQUIRED, on_delete=SET_NULL, related_name='_active_user')

    user = OneToOneField(AuthUser, on_delete=DO_NOTHING, related_name='tg_user', primary_key=True)
    messages: ReverseRelationQuerySet[Message]
    participants: ReverseRelationQuerySet[Participant]
    admin_events: ReverseRelationQuerySet[Event]

    @property
    def id(self):
        return self.user_id

    def __str__(self):
        return mark_safe(self.full_name + (f'<i> (tg: {self.to_html()})</i>' if self.is_telegram_user else ''))

    def to_html(self):
        return html_user_url(self.user)

    @classmethod
    def create_from_tg(cls, user: types.User):
        username = user.username or f'__{user.id}'

        return cls.objects.update_or_create(
            is_bot=user.is_bot,
            user=AuthUser.objects.update_or_create(
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
        min_id = AuthUser.objects.annotate(min_id=Min('id')).values()[0]['min_id']
        # custom users will have negative ids :)

        return AuthUser.objects.create(
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

    event = ForeignKey('Event', on_delete=DO_NOTHING, related_name='messages', **NOT_REQUIRED)

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


class ForwardMessage(Base):
    from_participant = ForeignKey('Participant', on_delete=DO_NOTHING, related_name='sent_messages')
    to_participant = ForeignKey('Participant', on_delete=DO_NOTHING, related_name='received_messages')

    data = JSONField(encoder=JSONEncoder)


class Event(Base):
    TYPE_SANTA = 'santa'
    TYPE_SAINT_NICHOLAS = 'saint_nicholas'
    TYPES = (
        (TYPE_SANTA, 'Santa'),
        (TYPE_SAINT_NICHOLAS, 'Saint Nicholas'),
    )

    STATUS_REGISTER_OPEN = 0
    STATUS_REGISTER_CLOSED = 1
    STATUS_PARTICIPANTS_DISTRIBUTED = 2
    STATUSES = (
        (STATUS_REGISTER_OPEN, 'Register opened'),
        (STATUS_REGISTER_CLOSED, 'Register closed'),
        (STATUS_PARTICIPANTS_DISTRIBUTED, 'Participants are already distributed'),
    )

    admin = ForeignKey(User, on_delete=DO_NOTHING, related_name='admin_events')

    type = CharField(choices=TYPES, default=TYPE_SANTA, max_length=256)
    status = TinyInt(choices=STATUSES, default=STATUS_REGISTER_OPEN)
    name = CharField(max_length=256)
    description = TextField(max_length=2048)

    participants: ReverseRelationQuerySet[Participant]
    messages: ReverseRelationQuerySet[Message]

    def __str__(self):
        return f'Event({self.name}, {self.description[:100]}, by {self.admin})'


class Participant(Base):
    user = ForeignKey(User, on_delete=DO_NOTHING, related_name='participants')
    event = ForeignKey(Event, on_delete=DO_NOTHING, related_name='participants')
    secret_good_buddy = OneToOneField('Participant', **NOT_REQUIRED, on_delete=SET_NULL, related_name='secret_santa')

    wishes = TextField(**NOT_REQUIRED)
    messages_as_santa = JSONField(default=list)
    messages_as_buddy: JSONField(default=list)

    def __str__(self):
        return f'Participant({self.user}, {self.event})'


class CallbackMessage(Base):
    handler_id = TinyInt()
    group_id = BigIntegerField()
    fn = PickledObjectField()
    args = PickledObjectField()
    kwargs = PickledObjectField()
