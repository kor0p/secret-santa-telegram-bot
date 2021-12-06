from typing import Union, Iterable

from telebot import types

from .const import BACK_BTN


def inline_buttons(
    *buttons: Union[bool, Iterable[Union[dict, Iterable[str], bool]]], width=3, back=False
) -> types.InlineKeyboardMarkup:
    result_buttons = types.InlineKeyboardMarkup(row_width=width)

    buttons = list(buttons)

    if back:
        buttons.append(((BACK_BTN, back),))

    for row in buttons:
        if not row:
            continue
        row_buttons = []
        for button in row:
            if not button:
                continue
            if isinstance(button, dict):
                options = {**button}
                options['switch_inline_query'] = options.pop('another_chat_url', None)
                options['switch_inline_query_current_chat'] = options.pop('current_chat_url', None)

            else:
                options = dict(
                    text=button[0],
                    callback_data=button[1],
                )

            row_buttons.append(types.InlineKeyboardButton(**options))

        result_buttons.add(*row_buttons)
    return result_buttons
