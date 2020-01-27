#!/usr/bin/env python
import asyncio
import re
import logging
from functools import wraps, partial

import telegram

from auth import AuthManager
from bot_buttons import TrackButton, TrackDislikeButton, TrackRemoveButton, make_playlist_markup, PlaylistPageButton, \
    DeleteMessageButton, PlaylistRefreshButton, TrackLikeButton
from playlist_manager import PlaylistManager, get_track, delay_thread_safe

from telegram.ext import Updater, MessageHandler, Filters, CommandHandler, CallbackContext, CallbackQueryHandler
from telegram import Update, ChatAction, MessageEntity, InlineKeyboardMarkup

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)

updater = Updater(token='1048865331:AAE6W4TfVoG54GMtbsP6hoQWX1C7dle6KUc', use_context=True)

BUTTON_PLAY_PAUSE = '⏯️ Играть'
BUTTON_DISLIKE = '👎 Дизлайк'
BUTTON_PLAYLIST = '🗒️ Плейлист'
BUTTON_VOLUME = '🔊 Громкость'

loop = asyncio.get_event_loop()

delay = partial(delay_thread_safe, loop=loop)

manager = PlaylistManager(loop=loop, max_dislikes=2)
auth_manager = AuthManager(password='1appservice$')


def restricted(func):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        sender_id = update.effective_user.id
        if not auth_manager.is_authorized(sender_id):
            update.message.reply_text(
                'Требуется пароль! Просто введи его строкой ниже. Используя /auth <password>'
            )
            return
        return func(update, context, *args, **kwargs)

    return wrapped


def extract_track_ids(message):
    track_ids = []

    split = message.text.split(' ')
    try:
        track_ids = [int(track_id) for track_id in split if not track_id.startswith('/')]
    except ValueError:
        pass

    for url in message.parse_entities(MessageEntity.URL).values():
        match = re.search(r'/track/([0-9]+)/?', url)
        track_ids.append(match.group(1))

    return track_ids


def _start(update: Update, context: CallbackContext):
    """Send a message when the command /start is issued."""

    custom_keyboard = [
        [BUTTON_PLAY_PAUSE, BUTTON_PLAYLIST, BUTTON_DISLIKE],
        [BUTTON_VOLUME + ' 50', BUTTON_VOLUME + ' 75', BUTTON_VOLUME + ' 100']
    ]

    reply_markup = telegram.ReplyKeyboardMarkup(custom_keyboard, resize_keyboard=True)
    update.message.reply_text(
        'Йоу!\n'
        'Просто отправь мне ссылку на трек с music.yandex.by\n'
        'Например `https://music.yandex.by/album/68299/track/583725`\n'
        'или только `583725`\n'
        f'Если у трека {manager.max_dislikes} дизлайка, то он удаляется.\n',
        reply_markup=reply_markup,
        parse_mode='Markdown',
    )


def _auth(update: Update, context: CallbackContext):
    try:
        password = context.args[0]
    except IndexError:
        return

    sender_id = update.effective_user.id
    if auth_manager.is_authorized(sender_id):
        return

    is_ok = auth_manager.authorize(sender_id, password=password)
    text = "Все ок!" if is_ok else "Неверный пароль!"
    update.message.reply_text(text)


@restricted
def _say(update: Update, context: CallbackContext):
    text = ' '.join(context.args)

    decrease = 1 if text.startswith('!') else 0.7

    delay(manager.say(text, decrease=decrease))


@restricted
def _set(update: Update, context: CallbackContext):
    try:
        attr, value = context.args
    except ValueError:
        return

    if value in ['+', '-']:
        value = value == '+'

    setattr(manager, attr, value)

    update.message.reply_text(f'{attr}={value}')


@restricted
def _play_pause(update: Update, context: CallbackContext):
    if manager.player.is_playing:
        manager.player.pause()
    else:
        manager.player.play()


@restricted
def _volume(update: Update, context: CallbackContext):
    volume = None
    try:
        volume = int(update.message.text.split(' ')[-1])
    except (ValueError, IndexError):
        pass

    manager.player.volume = volume


@restricted
def _playlist(update: Update, context: CallbackContext):
    print('sender_id', update, context)
    sender_id = update.effective_user.id

    string = f'В очереди: {len(manager.playlist)}\n\n'

    markup = make_playlist_markup(sender_id=sender_id, manager=manager, page_num=0)

    update.message.reply_text(string, reply_markup=markup)


@restricted
def _dislike(update: Update, context: CallbackContext):
    sender_id = update.effective_user.id

    update.message.text = update.message.text.replace(BUTTON_DISLIKE, '')

    ids = extract_track_ids(update.message)
    for track_id in ids:
        delay(manager.dislike(sender_id, track_id))

    # dislike current track if ids is not set
    if not ids:
        delay(manager.dislike(sender_id))


@restricted
def _unknown(update: Update, context: CallbackContext):
    """Echo the user message."""
    context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action=ChatAction.TYPING)

    tracks = []
    for track_id in extract_track_ids(update.message):
        track = get_track(track_id)
        num = delay(manager.add_track(track))
        tracks.append((num, track))

    # for sync purpose
    delay(asyncio.sleep(1))

    for num, track in tracks:
        is_current = manager.current_track == track

        text = TrackButton.make_text(track, is_current=is_current, num=num)

        context.bot.send_message(
            text=text,
            chat_id=update.effective_chat.id,
            reply_markup=InlineKeyboardMarkup([[TrackRemoveButton.make(track.id)]])
        )


button_handlers = [
    TrackButton,
    TrackLikeButton,
    TrackRemoveButton,
    TrackDislikeButton,
    PlaylistPageButton,
    DeleteMessageButton,
    PlaylistRefreshButton,
]


def _callback_query(update: Update, context: CallbackContext):
    query = update.callback_query

    for button in button_handlers:
        if query.data.startswith(button.pattern):
            button.click(update=update, context=context, playlist_manager=manager)


updater.dispatcher.add_handler(CommandHandler('start', _start))
updater.dispatcher.add_handler(CommandHandler('auth', _auth))

updater.dispatcher.add_handler(CommandHandler('say', _say))
updater.dispatcher.add_handler(CommandHandler('set', _set))

updater.dispatcher.add_handler(MessageHandler(Filters.regex(BUTTON_PLAY_PAUSE), _play_pause))
updater.dispatcher.add_handler(CommandHandler('play', _play_pause))

updater.dispatcher.add_handler(MessageHandler(Filters.regex(BUTTON_DISLIKE), _dislike))
updater.dispatcher.add_handler(CommandHandler('dislike', _dislike))

updater.dispatcher.add_handler(MessageHandler(Filters.regex(BUTTON_VOLUME), _volume))
updater.dispatcher.add_handler(CommandHandler('volume', _volume))

updater.dispatcher.add_handler(MessageHandler(Filters.regex(BUTTON_PLAYLIST), _playlist))
updater.dispatcher.add_handler(CommandHandler('playlist', _playlist))

updater.dispatcher.add_handler(MessageHandler(Filters.text, _unknown))

updater.dispatcher.add_handler(CallbackQueryHandler(_callback_query))

if __name__ == '__main__':
    updater.start_polling()
    loop.run_until_complete(manager.rotate_tracks())
