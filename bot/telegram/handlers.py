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
from .const import LINK_BTN, DOWN_ARROW, ADMIN, STAR
from .utils import get_trans, get_lang, callback as cb, get_multi_trans
from ..models import Event, User, Participant, Message as DBMessage, ForwardMessage


admin_users = json.loads(os.environ.get('ADMIN_IDS'))


def get_event_lang(event: Event):
    users = User.objects.filter(participants__event_id=event.id)
    langs = [user.language_code for user in users]
    if not langs:  # wtf?)
        langs = ['en']
    _ = get_multi_trans(*langs)
    return _


def get_join_button_text(event):
    _ = get_event_lang(event)

    participants_text = ', '.join(pt.user.to_html() for pt in event.participants.all())
    if event.status == event.STATUS_REGISTER_OPEN:
        return (
            _('Welcome to') + f' <b>{event.name}</b>\n{event.description}\n\n' +
            _('Participants') + ':\n' + participants_text +
            _('Click here to join this event')
        )
    else:
        return (
            _('Registration for') + f' <b>{event.name}</b> ' + _('already closed!') +
            f'{event.description}\n\n' +
            _('Participants') + ':\n' + participants_text
        )


def get_join_button_inline_buttons(event):
    if event.status != event.STATUS_REGISTER_OPEN:
        return None

    return inline_buttons(
        (dict(text=LINK_BTN, url=f't.me/{bot_user.username}?start={event.id}'),),
    )


def sync_event(event: Event):
    text = get_join_button_text(event)
    buttons = get_join_button_inline_buttons(event)

    for message in event.messages.all():
        bot.edit_message_text(
            inline_message_id=message.data['inline_message_id'],
            text=text,
            reply_markup=buttons,
            disable_web_page_preview=True,
        )


def sub_user_for_event(user: User, event: Event, _):
    participant, created = Participant.objects.get_or_create(user=user, event=event)
    user.update(active_participant=participant)

    if created:
        sync_event(event)

    return created


@bot.message_handler(commands=['send_buddy', 'send_santa', 'send_nicholas'])
def send_your_buddy_or_santa_start(message: Message, user: User, _):
    send_santa = not message.text.startswith('/send_buddy')
    if not user.participants.count():
        return bot.send_message(user.id, _('Error: you have no events yet or you need to choose your active event!'))

    participant = user.active_participant
    event = participant.event
    receiver: Participant = getattr(participant, 'secret_santa' if send_santa else 'secret_good_buddy', None)
    if event.status != Event.STATUS_PARTICIPANTS_DISTRIBUTED or not receiver:
        return bot.send_message(user.id, _('Error: event does not start yet!'))

    if send_santa:
        text = event.get_type_text('to', _)
    else:
        text = _('to Secret Good Buddy')

    bot.send_message(
        user.id,
        _('Send any message') + ' ' + text + '\n' +
        _('Active event') + f': <b>{event.name}</b>\n' +
        _('Manage your active event: /events'),
    )
    bot.register_next(
        user.id,
        send_your_buddy_or_santa_message,
        user.id,
        get_lang(_),
        receiver_id=receiver.user.id,
        send_santa=send_santa,
    )


def send_your_buddy_or_santa_message(message: Message, user_id, lang, receiver_id: int, send_santa: bool):
    user: User = User.objects.get(user_id=user_id)
    receiver: User = User.objects.get(user_id=receiver_id)
    get_text_sender = get_trans(lang)
    get_text_receiver = get_trans(receiver.language_code)
    event: Event = user.active_participant.event

    _ = get_text_receiver

    if send_santa:
        bot.send_message(
            receiver.id,
            _('Event') + f' <b>{event.name}</b>\n' +
            _('You received message') + ' ' + _('from Secret Good Buddy') + ' ' + user.to_html() + DOWN_ARROW,
            disable_web_page_preview=True,
        )
    else:
        bot.send_message(
            receiver.id,
            _('Event') + f' <b>{event.name}</b>\n' +
            _('You received message') + f' {event.get_type_text("from", _)} {DOWN_ARROW}',
        )
    message_id = bot.copy_message(receiver.id, message.chat.id, message.id)
    ForwardMessage.objects.create(
        message_id=message_id,
        type=ForwardMessage.TYPE_SANTA if send_santa else ForwardMessage.TYPE_BUDDY,
        from_participant_id=user.active_participant_id,
        to_participant_id=receiver.active_participant_id,
    )

    _ = get_text_sender
    bot.send_message(user.id, _('Message successfully sent!'))


@bot.message_handler(commands=['start', 'help'])
def start_command(message: Message, user: User, _):
    command, *text = message.text.split(' ', 1)
    if command == '/start' and text:  # ' ' is not absent in message.text -> register flow
        event_id = int(text[0])
        event = Event.objects.get(id=event_id)

        if sub_user_for_event(user, event, _):
            return bot.send_message(
                user.id,
                _('You are successfully registered for') + f' <b>{event.name}</b>!',
            )
        else:
            return bot.send_message(
                user.id,
                _('You are already registered for') + f' <b>{event.name}</b>!' +
                _('Status of this event:') + f' {event.get_status_text(_)}' +
                _('To leave event, use /events'),
            )

    # starting bot or help flow
    return bot.send_message(
        user.id,
        _('Hi User') + '\n\n' +
        _('/start /help - Show this message') + '\n\n' +
        _('/new_event - Create new Secret Santa event') + '\n\n' +
        _('/events - Settings for your events'),
    )


@bot.message_handler(commands=['new_event'])
def new_event_command_start(message: Message, user: User, _):
    bot.send_message(user.id, _('Please, send name for your event below'))

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
    if re.search('(nicholas)|(nicolaus)|(миколай)|(николай)', name + '\n' + description, re.IGNORECASE):
        type = Event.TYPE_SAINT_NICHOLAS

    event = Event.objects.create(
        admin=user,
        type=type,
        name=name,
        description=description,
    )
    sub_user_for_event(user, event, _)

    bot.send_message(
        user.id,
        _('Success! To manage your events, use /events'),
    )
    msg, db_msg = bot.send_message(user.id, '_')
    msg.from_user.is_bot = False

    event_selected(msg, user, _, event.id)


@bot.message_handler(commands=['events'])
@bot.callback_query_handler(cb.events_main)
def events_settings(msg_cbq: Union[Message, CallbackQuery], user: User, _, back=False):
    edit_id = False
    if isinstance(msg_cbq, CallbackQuery):
        message = msg_cbq.message
    else:
        message = msg_cbq
    if message.from_user.is_bot:
        edit_id = (message.message_id, message.chat.id)

    events = Event.objects.filter(participants__user_id=user.id)
    if not events.exists():
        return bot.send_message(
            user.id,
            _('''
You have no events created
Create one with /new_event
or join someone else's event
''')
        )

    if events.count() == 1 and not back:
        return event_selected(msg_cbq, user, _, events.first().id)

    active_event = user.active_participant and user.active_participant.event_id

    text = _('Your events:') + f'\n{STAR} - ' + _('your active event')
    if events.filter(admin_id=user.id).exists():
        text += f'\n{ADMIN} - ' + _('you are admin there')
    buttons = inline_buttons(
        (
            (
                (STAR if event.id == active_event else '') +
                (ADMIN if event.admin_id == user.id else '') +
                event.name,
                cb.events_settings.create(event.id),
            )
            for event in events.all()
        ),
        width=1,
    )

    if edit_id:
        bot.edit_message_text(message_id=edit_id[0], chat_id=edit_id[1], text=text, reply_markup=buttons)
    else:
        bot.send_message(user.id, text, reply_markup=buttons)


@bot.callback_query_handler(cb.events_settings)
def event_selected(msg_cbq: Union[Message, CallbackQuery], user: User, _, event_id: int, back=False):
    edit_id = False
    if isinstance(msg_cbq, CallbackQuery):
        message = msg_cbq.message
    else:
        message = msg_cbq
    if message.from_user.is_bot:
        edit_id = (message.message_id, message.chat.id)

    event: Event = Event.objects.get(id=event_id)
    is_admin = event.admin_id == user.id
    is_active_event = user.active_participant and user.active_participant.event_id == event_id

    text = (
        ((STAR + _('This is your active event') + f'{STAR}\n\n') if is_active_event else '') +
        (
            _('You are editing event')
            if is_admin else
            _('You are viewing event')
        ) + f' <b>{event.name}</b>\n' +
        _('Description') + f':\n{event.description}\n\n' +
        _('Type Of Event') + ': ' + event.get_type_text('', _) + '\n' +
        _('Status Of Event') + ': ' + event.get_status_text(_) + '\n\n' +
        _('Participants') + ':\n' + ', '.join(pt.user.to_html() for pt in event.participants.all())
    )

    buttons = (
        ()
        if is_active_event else
        (_('Set this event as Active'), cb.event_user_set_active.create(event_id)),

        (_('Leave'), cb.event_user_unsub.create(event_id, 0))
        if event.status == event.STATUS_REGISTER_OPEN and event.participants.count() > 1 else
        (),
    )

    if is_admin:
        if event.status == Event.STATUS_REGISTER_OPEN:
            register_buttons = (
                (_('Close registration'), cb.event_admin.create(event_id, 'register_close')),
                dict(text=_('Share event to join'), another_chat_url=event.name),
            )
        elif event.status == Event.STATUS_REGISTER_CLOSED:
            register_buttons = (
                (_('Open registration'), cb.event_admin.create(event_id, 'register_open')),
                (
                    (_('Distribute participants'), cb.event_admin.create(event_id, 'distribute_users'))
                    if event.participants.count() > 1
                    else ()
                ),
            )
        else:
            register_buttons = ()

        buttons = (
            *buttons,
            (_('Edit name'), cb.event_admin_edit.create(event_id, 'name')),
            (_('Edit description'), cb.event_admin_edit.create(event_id, 'description')),
            (_('Edit type'), cb.event_admin_type.create(event_id)),
            *register_buttons,
        )

    buttons = inline_buttons(buttons, width=1, back=cb.events_main.create(True))

    if edit_id:
        bot.edit_message_text(
            message_id=edit_id[0], chat_id=edit_id[1], text=text, reply_markup=buttons, disable_web_page_preview=True
        )
    else:
        bot.send_message(user.id, text, reply_markup=buttons, disable_web_page_preview=True)


@bot.callback_query_handler(cb.event_user_set_active)
def event_user_set_active(cbq: CallbackQuery, user: User, _, event_id: int):
    active_participant = Participant.objects.get(event_id=event_id, user_id=user.id)
    if active_participant:
        user.active_participant = active_participant
    event_selected(cbq, user, _, event_id)


@bot.callback_query_handler(cb.event_user_unsub)
def event_user_unsub(cbq: CallbackQuery, user: User, _, event_id: int, step: int):
    event: Event = Event.objects.get(id=event_id)

    if step < 2:
        buttons = [
            (_('No'), cb.events_settings.create(event_id, True)),
            (_('Nope, nevermind'), cb.events_settings.create(event_id, True)),
            (_('Yes, I want to leave'), cb.event_user_unsub.create(event_id, step + 1)),
        ]
        shuffle(buttons)
        bot.edit_message_text(
            message_id=cbq.message.message_id,
            chat_id=cbq.message.chat.id,
            text=_('You want to leave') + f' <b>{event.name}</b>\n' + _('Are you sure?'),
            reply_markup=inline_buttons(buttons, width=1, back=cb.events_settings.create(event_id, True)),
        )
        return

    participant = Participant.objects.get(user_id=user.id, event_id=event_id)
    if participant:
        participant.delete()
        other_participants = Participant.objects.filter(user_id=user.id, event_id=event_id).order_by('-created_at')
        if other_participants.exists():
            user.active_participant = other_participants.first()
        sync_event(event)
    event_selected(cbq, user, _, event_id)


@bot.callback_query_handler(cb.event_admin_edit)
def event_admin_edit_start(message: Message, user: User, _, event_id: int, edit_type: str):
    if edit_type == 'name':
        text = _('Send new name below')
    else:
        text = _('Send new description below')
    bot.send_message(user.id, text)
    bot.register_next(user.id, event_admin_edit, get_lang(_), user.id, event_id, edit_type)


def event_admin_edit(message: Message, lang, user_id: int, event_id: int, edit_type: str):
    _ = get_trans(lang)
    event = Event.objects.get(id=event_id)
    event.update(**{edit_type: message.text})
    bot.send_message(user_id, _('Event was successfully updated'))
    sync_event(event)


@bot.callback_query_handler(cb.event_admin_type)
def event_admin_type(cbq: CallbackQuery, user: User, _, event_id: int):
    bot.edit_message_text(
        message_id=cbq.message.message_id,
        chat_id=cbq.message.chat.id,
        text=_('Select new type here'),
        reply_markup=inline_buttons(
            (
                (_(value), cb.event_admin_type_edit.create(event_id, name))
                for name, value in Event.TYPES
            ),
            width=1,
            back=cb.events_settings.create(event_id, True),
        ),
    )


@bot.callback_query_handler(cb.event_admin_type_edit)
def event_admin_type_edit(cbq: CallbackQuery, user: User, _, event_id, event_type):
    event = Event.objects.get(id=event_id)
    event.update(type=event_type)
    event_selected(cbq, user, _, event_id)
    sync_event(event)


def distribute_participants(event: Event):
    participants: list[Participant] = list(event.participants.all())

    participants_receivers = participants.copy()
    shuffle(participants_receivers)
    participants_senders = participants.copy()

    while participants_senders[-1].id == participants_receivers[-1].id:
        shuffle(participants_senders)

    for receiver in participants_receivers:
        index_check = 0
        if participants_senders[index_check].id == receiver.id:
            index_check += 1

        sender = participants_senders[index_check]
        sender.update(secret_good_buddy=receiver)

        participants_senders.pop(0)

    for receiver in participants_receivers:
        if receiver.secret_good_buddy:
            continue

        # someone haven't Secret Santa...
        for _receiver in participants_receivers:
            _receiver.update(secret_good_buddy=None)
        # try again
        return distribute_participants(event)

    # send all participants message with info

    for participant in participants_receivers:
        _ = get_trans(participant.user.language_code)

        msg, db_msg = bot.send_message(
            participant.user_id,
            (
                _('Hey! Event') + f' "{event.name}" ' + _('started!') + '\n' +
                _('Your secret good buddy, whom you need to send a gift is:') + '\n' +
                participant.secret_good_buddy.user.to_html() + '\n' +
                _('To send them a message, use /send_buddy') + '\n\n' +
                _('To send message') + f' {event.get_type_text("to", _)}, ' + _('use') + f' {event.get_type_command(_)}\n' +
                _('Provide here your wishes and address to collect your present!')
            ),
            disable_web_page_preview=True,
        )
        bot.pin_chat_message(participant.user_id, msg.message_id, True)


@bot.callback_query_handler(cb.event_admin)
def event_admin(cbq: CallbackQuery, user: User, _, event_id: int, type: str):
    event = Event.objects.get(id=event_id)

    if type == 'register_close':
        event.update(status=Event.STATUS_REGISTER_CLOSED)

    if type == 'register_open':
        event.update(status=Event.STATUS_REGISTER_OPEN)

    if type == 'distribute_users':
        distribute_participants(event)
        event.update(status=Event.STATUS_PARTICIPANTS_DISTRIBUTED)

    sync_event(event)
    event_selected(cbq, user, _, event_id)


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
                InputTextMessageContent(
                    get_join_button_text(event), parse_mode='HTML', disable_web_page_preview=True
                ),
                get_join_button_inline_buttons(event),
            )
            for event in events
        ),
    )


@bot.chosen_inline_handler(func=lambda cr: cr)
def chosen_inline_query(inline_request: ChosenInlineResult, user: User, _):
    if not inline_request.inline_message_id:
        return  # future message

    event: Event = Event.objects.get(id=int(inline_request.result_id.split('|')[0]))
    event.messages.add(*DBMessage.objects.filter(data__inline_message_id=inline_request.inline_message_id))


@bot.message_handler(func=lambda msg: msg.content_type not in ('pinned_message',))
def any_message(message: Message, user: User, _):
    bot.send_message(message.chat.id, _('Unrecognized command, see /help'))
