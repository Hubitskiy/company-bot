import math

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from playlist_manager import PlaylistManager, delay_thread_safe, Track


def get_buttons(keyboard, callback_data):
    buttons = []
    if isinstance(keyboard, list):
        for key in keyboard:
            buttons.extend(get_buttons(key, callback_data))
        return buttons

    try:
        if keyboard.callback_data == callback_data:
            return [keyboard]
    except AttributeError:
        pass
    return []


def update_button(keyboard, callback_data, **kwargs):
    buttons = get_buttons(keyboard, callback_data)

    for button in buttons:
        for k, v in kwargs.items():
            setattr(button, k, v)

    return buttons


def make_playlist_markup(sender_id: int, manager: PlaylistManager, page_num: int = 0, per_page: int = 15):
    buttons = []
    if page_num == 0 and manager.current_track:
        like = sender_id in manager.current_track.dislikes
        buttons.append([
            TrackButton.make(manager.current_track, is_current=True),
            TrackLikeButton.make(manager.current_track.id, like=like)
        ])

    total = math.ceil(len(manager.playlist) / per_page)

    page = manager.playlist[page_num * per_page:(page_num + 1) * per_page]

    for track in page:
        like = sender_id in track.dislikes
        buttons.append([
            TrackButton.make(track, is_current=False),
            TrackLikeButton.make(track.id, like=like)
        ])

    pagination = []
    if page_num > 0:
        pagination.append(
            PlaylistPreviewPageButton.make(page_num - 1)
        )

    if page_num + 1 < total:
        pagination.append(
            PlaylistNextPageButton.make(page_num + 1)
        )

    if pagination:
        buttons.append(pagination)

    buttons.append([DeleteMessageButton.make()])

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


class TrackLikeButton(BaseButton):
    pattern = 'like_track_'

    yes_suffix = '_yes'
    no_suffix = '_no'

    @classmethod
    def click(cls, update: Update, context: CallbackContext, playlist_manager: PlaylistManager):
        query = update.callback_query

        buttons = update_button(
            query.message.reply_markup.inline_keyboard, callback_data=query.data
        )

        track_id = int(query.data.split('_')[2])
        is_like = query.data.split('_')[3] == cls.yes_suffix[1:]

        for button in buttons:
            text, data = cls.get_text_and_data(track_id, like=not is_like)
            delay_thread_safe(
                playlist_manager.like(sender_id=update.effective_user.id, track_id=track_id),
                playlist_manager.loop,
            )
            button.text = text
            button.callback_data = data

        context.bot.edit_message_reply_markup(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            reply_markup=query.message.reply_markup,
        )

    @classmethod
    def get_text_and_data(cls, track_id: int, like: bool = False):
        callback_data = cls.pattern + str(track_id) + (cls.yes_suffix if like else cls.no_suffix)
        text = '🚫 Отменить' if like else '👎 Дизлайк'
        return text, callback_data

    @classmethod
    def make(cls, track_id: int, like: bool = False):
        text, data = cls.get_text_and_data(track_id, like=like)
        return InlineKeyboardButton(text, callback_data=data)


class PlaylistPageButton(BaseButton):
    pattern = 'playlist_page_'

    @classmethod
    def click(cls, update: Update, context: CallbackContext, playlist_manager: PlaylistManager):
        query = update.callback_query
        sender_id = update.effective_user.id

        page_num = int(query.data.split('_')[2])

        markup = make_playlist_markup(sender_id, playlist_manager, page_num=page_num)

        context.bot.edit_message_reply_markup(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            reply_markup=markup,
        )


class PlaylistNextPageButton(PlaylistPageButton):
    @classmethod
    def make(cls, page_num: int):
        return InlineKeyboardButton('➡️', callback_data=cls.pattern + str(page_num))


class PlaylistPreviewPageButton(PlaylistPageButton):
    @classmethod
    def make(cls, page_num: int):
        return InlineKeyboardButton('⬅️', callback_data=cls.pattern + str(page_num))


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
