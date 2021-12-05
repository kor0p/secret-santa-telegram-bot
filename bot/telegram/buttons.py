from typing import Union, Sequence

from telebot import types


def inline_buttons(
    *buttons: Union[bool, Sequence[Union[dict, Sequence[str], bool]]], width=3
) -> types.InlineKeyboardMarkup:
    result_buttons = types.InlineKeyboardMarkup(row_width=width)
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

        result_buttons.row(*row_buttons)
    return result_buttons
