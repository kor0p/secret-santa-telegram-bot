import json
import random
from enum import Enum
from typing import Union
import string
from functools import partial

from telebot import types
from django.utils.translation.trans_real import translation
from django.contrib.auth.base_user import AbstractBaseUser

JSON_COMMON_DATA = Union[list[...], dict[str, ...], int, str]


def get_trans(lang):
    return translation(lang).gettext


def multi_gettext(get_text_list, text, sep='\n'):
    return sep.join(get_text(text) for get_text in get_text_list)


def get_multi_trans(*langs, **kwargs):
    get_text_list = [get_trans(lang) for lang in langs]
    return partial(multi_gettext, get_text_list, **kwargs)


def get_lang(gettext):
    return gettext.__self__.language()


def random_str(n: int):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=n))


def safe_join(*items, default=''):
    """
    >>> safe_join(False, 'test ', 34, (', ', 10))
    ''
    >>> safe_join('test ', 34, (', ', False), (', ', 10))
    test 34, 10
    """
    result = ''
    for item in items:
        if not item:
            return default
        if isinstance(item, tuple):
            result += safe_join(*item, default=default)
        else:
            result += str(item)
    return result


def html_user_url(user: Union[AbstractBaseUser, types.User], *, mention=False) -> str:
    url = f'tg://user?id={user.id}'
    if not mention and (username := getattr(user, 'username', None)) and not username.startswith('__'):
        url = f'https://t.me/{username}'
    return f'<a href="{url}" target="_blank">{user.first_name}</a>'


def mention_user(user: AbstractBaseUser):
    return html_user_url(user, mention=True)


class callback(Enum):
    user_settings = ('us', str, JSON_COMMON_DATA)  # action, value (new_event_id, etc)
    events_main = ('em',)  # for back button in events_settings
    events_settings = ('es', int)  # event_id (to edit)
    event_admin = ('ea', int, str)  # event_id, action
    event_admin_edit = ('eae', int, str)  # event_id, edit_type
    event_admin_type = ('eat', int)  # event_id
    event_admin_type_edit = ('eate', int, str)  # event_id, type
    event_user_set_active = ('eusa', int)  # user event settings - set active -- event_id
    event_user_unsub = ('eus', int, int)  # user event settings - leave -- event_id, step

    def create(self, *data: JSON_COMMON_DATA) -> str:
        return json.dumps([self.value[0], data], separators=(',', ':'))
