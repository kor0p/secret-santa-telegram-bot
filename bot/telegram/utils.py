import json
import random
from enum import Enum
from typing import Union
import string

from telebot import types
from django.contrib.auth.base_user import AbstractBaseUser

JSON_COMMON_DATA = Union[list[...], dict[str, ...], int, str]


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
    TODO = dict[str, str]

    def create(self, **data: JSON_COMMON_DATA) -> str:
        return json.dumps([self.name, data], separators=(',', ':'))
