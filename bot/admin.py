from django import forms
from django.contrib import admin

from .models import User, Message


class UserForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if kwargs.get('instance'):
            return  # edit form

        is_bot = self.fields['is_bot']
        username = self.fields['username']
        language_code = self.fields['language_code']
        bot_can_message = self.fields['bot_can_message']
        is_telegram_user = self.fields['is_telegram_user']
        user = self.fields['user']

        is_bot.widget = forms.HiddenInput()
        username.widget = forms.HiddenInput()
        language_code.widget = forms.HiddenInput()
        language_code.initial = '-'
        bot_can_message.widget = forms.HiddenInput()
        is_telegram_user.widget = forms.HiddenInput()
        is_telegram_user.initial = False
        user.widget = forms.HiddenInput()
        user.required = False
        user.choices = [('', '-')]
        user.initial = ''

    def save(self, commit=True):
        self.instance.user = User.create_new_auth_user(
            first_name=self.instance.full_name,
        )
        self.instance.save()

        user = super().save(commit=commit)
        return user


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    search_fields = ['full_name']
    form = UserForm


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    search_fields = ['data']
