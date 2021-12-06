import os
import re
import json
from typing import Union
from random import shuffle

from django.db.models import Q
from telebot.types import (
    Message, CallbackQuery, InlineQuery, ChosenInlineResult, InlineQueryResultArticle, InputTextMessageContent
)

from .bot import bot, bot_user
from .buttons import inline_buttons
from .const import LINK_BTN, DOWN_ARROW
from .utils import get_trans, get_lang, callback
from ..models import Event, User, Participant, Message as DBMessage


admin_users = json.loads(os.environ.get('ADMIN_IDS'))


def get_join_button_text(event, _):
    if event.status == event.STATUS_REGISTER_OPEN:
        return _('Click here to join the event "{event.name}"').format(event=event)
    else:
        return _('Registration for event "{event.name}" already closed!').format(event=event)


def get_join_button_inline_buttons(event, _):
    if event.status != event.STATUS_REGISTER_OPEN:
        return None

    return inline_buttons(
        (
            dict(
                text=f'{_("Join")} {LINK_BTN}',
                url=f't.me/{bot_user.username}?start={event.id}',
            ),
        ),
    )


def sync_event(event: Event, _):
    text = get_join_button_text(event, _)
    buttons = get_join_button_inline_buttons(event, _)
    for message in event.messages:
        bot.edit_message_text(
            chat_id=message.data['message']['chat']['id'],
            message_id=message.message_id,
            text=text,
            reply_markup=buttons,
            disable_web_page_preview=True,
        )


def toggle_user_for_event(user: User, event: Event, _):
    participant, created = Participant.objects.get_or_create(user=user, event=event)

    if created:
        user.update(active_participant=participant)
    else:
        participant.delete()

    sync_event(event, _)

    return created


@bot.message_handler(commands=['start', 'help'])
def start_command(message: Message, user: User, _):
    command, *text = message.text.split(' ', 1)
    if command == '/start' and text:  # ' ' is not absent in message.text -> register flow
        event_id = int(text[0])
        event = Event.objects.get(id=event_id)

        if toggle_user_for_event(user, event, _):
            return bot.send_message(
                user.id, _('You are successfully registered for {event.name}!').format(event=event)
            )
        else:
            return bot.send_message(
                user.id, _('You are successfully left "{event.name}" event').format(event=event)
            )

    # starting bot or help flow
    return bot.send_message(
        user.id,
        _('''
Hi User!

/send_buddy - Send a message to your Good buddy
/send_santa - Send a message to your Secret Santa

/start /help - Show this message
/new_event - Create new Secret Santa event
/events - Settings for your events
'''),  # /settings - Bot preferences
    )


@bot.message_handler(commands=['new_event'])
def new_event_command_start(message: Message, user: User, _):
    bot.send_message(
        user.id,
        _('Please, send name for your event below'),
    )

    bot.register_next(user.id, new_event_command_name, get_lang(_), user_id=user.id)


def new_event_command_name(message: Message, lang, user_id: int):
    _ = get_trans(lang)
    bot.send_message(
        user_id,
        _('''
Wow, very cool name!
Please, now send description for your event below
You may add here place and time of event, your contact, or other important info
'''),
    )

    bot.register_next(user_id, new_event_command_description, lang, user_id=user_id, name=message.text)


def new_event_command_description(message: Message, lang, user_id: int, name: str):
    _ = get_trans(lang)
    user = User.objects.get(user_id=user_id)
    description = message.text

    type = Event.TYPE_SANTA
    if re.match('(nicholas)|(nicolaus)|(миколай)', name + '\n' + description, re.IGNORECASE):
        type = Event.TYPE_SAINT_NICHOLAS

    event = Event.objects.create(
        admin=user,
        type=type,
        name=name,
        description=description,
    )
    Participant.objects.create(user=user, event=event)

    bot.send_message(
        user.id,
        _('Success! To manage your events, use /events'),
    )


@bot.message_handler(commands=['events'])
@bot.callback_query_handler(callback.events_main)
def events_settings(msg_cbq: Union[Message, CallbackQuery], user: User, _, edit_id=False):
    if isinstance(msg_cbq, CallbackQuery):
        if msg_cbq.inline_message_id:
            edit_id = msg_cbq.inline_message_id
        elif not edit_id:
            edit_id = (msg_cbq.message.message_id, user.id)

    events = user.admin_events
    if not events:
        bot.send_message(user.id, _('You have no events created, create one with /new_event'))

    if events.count() == 1:
        return event_selected(msg_cbq, user, events.first().id)

    text = _('Choose event to edit:')
    buttons = inline_buttons(
        (
            (event.name, callback.events_settings.create(event.id, edit_id))
            for event in events.all()
        ),
        width=1,
    )

    if edit_id and isinstance(edit_id, tuple):
        bot.edit_message_text(message_id=edit_id[0], chat_id=edit_id[1], text=text, reply_markup=buttons)
    elif edit_id:
        bot.edit_message_text(inline_message_id=edit_id, text=text, reply_markup=buttons)
    else:
        bot.send_message(user.id, text, reply_markup=buttons)


@bot.callback_query_handler(callback.events_settings)
def event_selected(msg_cbq: Union[Message, CallbackQuery], user: User, _, event_id: int, edit_id=False):
    if isinstance(msg_cbq, CallbackQuery):
        message = msg_cbq.message
        if msg_cbq.inline_message_id:
            edit_id = msg_cbq.inline_message_id
        elif not edit_id:
            edit_id = (message.message_id, user.id)
    else:
        message = msg_cbq

    event = Event.objects.get(id=event_id)
    if event.status == Event.STATUS_REGISTER_OPEN:
        register_buttons = (
            (_('Close registration'), callback.event_admin.create(event_id, 'register_close')),
            dict(text=_('Share event to join'), another_chat_url=event.name),
        )
    elif event.status == Event.STATUS_REGISTER_CLOSED:
        register_buttons = (
            (_('Open registration'), callback.event_admin.create(event_id, 'register_open')),
            (_('Distribute participants'), callback.event_admin.create(event_id, 'distribute_users')),
        )
    else:
        register_buttons = ()

    text = _('''
Event "{event.name}"
Description:
{event.description}

Type: {type}
Status: {status}

Participants:
{participants}
''').format(
        event=event,
        type=event.get_type_display(),
        status=event.get_status_display(),
        participants=', '.join(pt.user.to_html() for pt in event.participants.all()),
    )
    buttons = inline_buttons(
        (
            (_('Edit name'), callback.event_admin_edit.create(event_id, 'name')),
            (_('Edit description'), callback.event_admin_edit.create(event_id, 'description')),
            (_('Edit type'), callback.event_admin_type.create(event_id, message.id)),
            *register_buttons,
        ),
        width=1,
        back=callback.events_main.create(),
    )

    if edit_id and isinstance(edit_id, tuple):
        bot.edit_message_text(
            message_id=edit_id[0], chat_id=edit_id[1], text=text, reply_markup=buttons, disable_web_page_preview=True
        )
    elif edit_id:
        bot.edit_message_text(inline_message_id=edit_id, text=text, reply_markup=buttons, disable_web_page_preview=True)
    else:
        bot.send_message(user.id, text, reply_markup=buttons, disable_web_page_preview=True)


@bot.callback_query_handler(callback.event_admin_edit)
def event_admin_edit_start(message: Message, user: User, _, event_id: int, edit_type: str):
    bot.send_message(user.id, _('Send new {type} below').format(type=edit_type))
    bot.register_next(user.id, event_admin_edit, get_lang(_), user.id, event_id, edit_type)


def event_admin_edit(message: Message, lang, user_id: int, event_id: int, edit_type: str):
    _ = get_trans(lang)
    event = Event.objects.get(id=event_id)
    event.update(**{edit_type: message.text})
    bot.send_message(user_id, _('You successfully updated {type}').format(type=edit_type))
    sync_event(event, _)


@bot.callback_query_handler(callback.event_admin_type)
def event_admin_type(cbq: CallbackQuery, user: User, _, event_id: int):
    bot.edit_message_text(
        inline_message_id=cbq.inline_message_id,
        text=_('Select new type here'),
        reply_markup=inline_buttons(
            (
                (value, callback.event_admin_type_edit.create(event_id, name))
                for name, value in Event.TYPES
            ),
            width=1,
            back=callback.events_settings.create(event_id)
        )
    )


@bot.callback_query_handler(callback.event_admin_type_edit)
def event_admin_type_edit(cbq: CallbackQuery, user: User, _, event_id, event_type):
    event = Event.objects.get(id=event_id)
    event.update(type=event_type)
    sync_event(event, _)


def distribute_participants(event: Event):
    participants: list[Participant] = list(event.participants.all())

    participants_receivers = participants.copy()
    shuffle(participants_receivers)
    participants_senders = participants.copy()
    shuffle(participants_senders)

    for receiver in participants_receivers:
        index_check = 0
        if participants_senders[index_check].id == receiver.id:
            index_check += 1

        sender = participants_senders[index_check]
        sender.update(secret_good_buddy=receiver)
        receiver.update(secret_santa=sender)

        participants_senders.pop(0)


@bot.callback_query_handler(callback.event_admin)
def event_admin(cbq: CallbackQuery, user: User, _, event_id: int, type: str):
    event = Event.objects.get(id=event_id)

    if type == 'register_close':
        event.update(status=Event.STATUS_REGISTER_CLOSED)

    if type == 'register_open':
        event.update(status=Event.STATUS_REGISTER_OPEN)

    if type == 'distribute_users':
        distribute_participants(event)
        event.update(status=Event.STATUS_PARTICIPANTS_DISTRIBUTED)

    sync_event(event, _)


@bot.inline_handler(lambda q: True)
def inline_query_handler(inline_query: InlineQuery, user: User, _):
    query = inline_query.query

    q = Q(status=Event.STATUS_REGISTER_OPEN, admin=user)
    if query:
        q &= Q(name__icontains=query)
    events = Event.objects.filter(q)

    return bot.answer_inline_query(
        inline_query.id,
        (
            InlineQueryResultArticle(
                f'{event.id}|{event.name[:10]}',
                event.name,
                InputTextMessageContent(get_join_button_text(event, _)),
                get_join_button_inline_buttons(event, _),
            )
            for event in events
        ),
    )


@bot.chosen_inline_handler(func=lambda cr: cr)
def chosen_inline_query(inline_request: ChosenInlineResult):
    if not inline_request.inline_message_id:
        return  # future message

    event: Event = Event.objects.get(id=int(inline_request.result_id.split('|')[0]))
    event.messages.add(DBMessage.objects.filter(data__inline_message_id=inline_request.inline_message_id))


@bot.message_handler(commands=['send_buddy', 'send_santa'])
def send_your_buddy_or_santa_start(message: Message, user: User, _):
    send_santa = message.text.startswith('/send_santa')
    event = user.active_participant.event
    receiver: Participant = getattr(user, 'secret_santa' if send_santa else 'secret_good_buddy', None)
    if event.status != Event.STATUS_REGISTER_OPEN or not receiver:
        return bot.send_message(user.id, _('Error: event does not start yet!'))

    bot.register_next(
        user.id, send_your_buddy_or_santa_message, get_lang(_), receiver_id=receiver.user.id, send_santa=send_santa
    )


def send_your_buddy_or_santa_message(message: Message, user: User, _, receiver_id: int, send_santa: bool):
    bot.send_message(
        receiver_id,
        f'''
{_('You received message from your')} {_('Secret Good Buddy' if send_santa else 'Secret Santa')} {DOWN_ARROW}
''',
    )
    message_id = bot.copy_message(receiver_id, message.chat.id, message.id)
    participant = user.active_participant
    if send_santa:
        participant.messages_as_buddy.append(message_id)
    else:
        participant.messages_as_santa.append(message_id)
    participant.save()

    bot.send_message(user.id, _('Message successfully sent!'))
