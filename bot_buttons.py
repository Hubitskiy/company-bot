import math

import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from playlist_manager import PlaylistManager, delay_thread_safe, Track


def get_buttons(keyboard, callback_data=None, pattern=None):
    assert callback_data or pattern
    buttons = []
    if isinstance(keyboard, list):
        for key in keyboard:
            buttons.extend(get_buttons(key, callback_data=callback_data, pattern=pattern))
        return buttons

    try:
        if keyboard.callback_data == callback_data or (pattern and keyboard.callback_data.startswith(pattern)):
            return [keyboard]
    except AttributeError:
        pass
    return []


def update_button(keyboard, callback_data=None, pattern=None, **kwargs):
    buttons = get_buttons(keyboard, callback_data=callback_data, pattern=pattern)

    for button in buttons:
        for k, v in kwargs.items():
            setattr(button, k, v)

    return buttons


def make_playlist_markup(sender_id: int, manager: PlaylistManager, page_num: int = 0, per_page: int = 15):
    page = []
    if page_num == 0 and manager.current_track:
        page.append(manager.current_track)

    total = math.ceil(len(manager.playlist) / per_page)

    page = page + manager.playlist[page_num * per_page:(page_num + 1) * per_page]

    buttons = []
    for idx, track in enumerate(page):
        buttons.append([
            TrackButton.make(track, is_current=page_num == 0 and idx == 0),
            TrackDislikeButton.make(track.id, disliked=sender_id in track.dislikes),
            TrackLikeButton.make(track.id, liked=sender_id in track.likes),
        ])

    pagination = []
    if page_num > 0:
        pagination.append(
            PlaylistPreviewPageButton.make(page_num)
        )

    if page_num + 1 < total:
        pagination.append(
            PlaylistNextPageButton.make(page_num)
        )

    if pagination:
        buttons.append(pagination)

    buttons.append([DeleteMessageButton.make(), PlaylistRefreshButton.make(page_num)])

    return InlineKeyboardMarkup(buttons)


class BaseButton:
    pattern = None

    @classmethod
    def click(cls, update: Update, context: CallbackContext, playlist_manager: PlaylistManager):
        pass


class TrackButton(BaseButton):
    pattern = 'track_'

    @classmethod
    def click(cls, update: Update, context: CallbackContext, playlist_manager: PlaylistManager):
        # query = update.callback_query

        # track_id = int(query.data.split('_')[2])
        pass

    @classmethod
    def make(cls, track: Track, is_current: bool = False, num: int = None):
        text = cls.make_text(track, is_current, num)
        return InlineKeyboardButton(text, url=f'https://music.yandex.by/track/{track.id}')

    @classmethod
    def make_text(cls, track: Track, is_current: bool = False, num: int = None):
        text = f'{track.name} [{track.id}]'
        if is_current:
            text = f'▶️ {text}'
        elif num is not None:
            text = f'{num}. {text}'

        return text


class TrackRemoveButton(BaseButton):
    pattern = 'remove_track_'

    @classmethod
    def click(cls, update: Update, context: CallbackContext, playlist_manager: PlaylistManager):
        query = update.callback_query

        track_id = int(query.data.split('_')[2])

        delay_thread_safe(
            playlist_manager.remove_track(track_id),
            playlist_manager.loop,
        )

        context.bot.delete_message(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
        )

    @classmethod
    def make(cls, track_id: int):
        return InlineKeyboardButton('❌ Удалить', callback_data=cls.pattern + str(track_id))


class TrackDislikeButton(BaseButton):
    pattern = 'dislike_track_'

    @classmethod
    def click(cls, update: Update, context: CallbackContext, playlist_manager: PlaylistManager):
        query = update.callback_query

        track_id = int(query.data.split('_')[2])
        disliked = bool(int(query.data.split('_')[3]))

        delay_thread_safe(
            playlist_manager.dislike(sender_id=update.effective_user.id, track_id=track_id),
            playlist_manager.loop,
        )

        buttons = update_button(
            query.message.reply_markup.inline_keyboard, callback_data=query.data
        )

        text, data = cls.get_text_and_date(track_id, not disliked)
        for button in buttons:
            button.text = text
            button.callback_data = data

        context.bot.edit_message_reply_markup(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            reply_markup=query.message.reply_markup,
        )

        PlaylistRefreshButton.click(update, context, playlist_manager)

    @classmethod
    def make(cls, track_id: int, disliked: bool):
        text, data = cls.get_text_and_date(track_id, disliked)
        return InlineKeyboardButton(text, callback_data=data)

    @classmethod
    def get_text_and_date(cls, track_id: int, disliked: bool):
        text = '🚫 Отменить' if disliked else '👎 Дизлайк'
        data = cls.pattern + str(track_id) + '_' + str(int(disliked))
        return text, data


class TrackLikeButton(BaseButton):
    pattern = 'like_track_'

    @classmethod
    def click(cls, update: Update, context: CallbackContext, playlist_manager: PlaylistManager):
        query = update.callback_query

        track_id = int(query.data.split('_')[2])
        disliked = bool(int(query.data.split('_')[3]))

        delay_thread_safe(
            playlist_manager.like(sender_id=update.effective_user.id, track_id=track_id),
            playlist_manager.loop,
        )

        buttons = update_button(
            query.message.reply_markup.inline_keyboard, callback_data=query.data
        )

        text, data = cls.get_text_and_date(track_id, not disliked)
        for button in buttons:
            button.text = text
            button.callback_data = data

        context.bot.edit_message_reply_markup(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            reply_markup=query.message.reply_markup,
        )

        PlaylistRefreshButton.click(update, context, playlist_manager)

    @classmethod
    def make(cls, track_id: int, liked: bool):
        text, data = cls.get_text_and_date(track_id, liked)
        return InlineKeyboardButton(text, callback_data=data)

    @classmethod
    def get_text_and_date(cls, track_id: int, liked: bool):
        text = ' 🚫 Отменить' if liked else '👍 Лайк'
        data = cls.pattern + str(track_id) + '_' + str(int(liked))
        return text, data


class PlaylistPageButton(BaseButton):
    pattern = 'playlist_page_'

    @classmethod
    def click(cls, update: Update, context: CallbackContext, playlist_manager: PlaylistManager):
        query = update.callback_query
        sender_id = update.effective_user.id

        page_num = 0
        if query.data.startswith(cls.pattern):
            page_num = int(query.data.split('_')[2])
        else:
            buttons = get_buttons(query.message.reply_markup.inline_keyboard, pattern=cls.pattern)
            # get current page
            if buttons:
                print(buttons[0].callback_data)
                page_num = int(buttons[0].callback_data.split('_')[3])

        markup = make_playlist_markup(sender_id, playlist_manager, page_num=page_num)

        try:
            context.bot.edit_message_reply_markup(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                reply_markup=markup,
            )
        except telegram.error.BadRequest:
            pass


class PlaylistNextPageButton(PlaylistPageButton):
    @classmethod
    def make(cls, current: int):
        return InlineKeyboardButton('➡️', callback_data=cls.pattern + str(current + 1) + '_' + str(current))


class PlaylistPreviewPageButton(PlaylistPageButton):
    @classmethod
    def make(cls, current: int):
        return InlineKeyboardButton('⬅️', callback_data=cls.pattern + str(current + 1) + '_' + str(current))


class PlaylistRefreshButton(PlaylistPageButton):
    @classmethod
    def make(cls, current: int):
        return InlineKeyboardButton('🔄️ Обновить', callback_data=cls.pattern + str(current) + '_' + str(current))


class DeleteMessageButton(BaseButton):
    pattern = 'message_delete'

    @classmethod
    def click(cls, update: Update, context: CallbackContext, playlist_manager: PlaylistManager):
        query = update.callback_query

        context.bot.delete_message(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
        )

    @classmethod
    def make(cls, ):
        return InlineKeyboardButton('Удалить сообщение', callback_data=cls.pattern)
