"""Plugin to remove deleted Accounts from a group"""
import asyncio
import logging
from typing import Optional, Dict

import logzero
from telethon.errors import FloodWaitError, UserAdminInvalidError, MessageIdInvalidError
from telethon.tl.custom import Message
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import (Channel, User, ChannelParticipantAdmin)

from utils.client import KantekClient
from utils.mdtex import Bold, KeyValueItem, MDTeXDocument, Section
from utils.pluginmgr import k, Command

tlog = logging.getLogger('kantek-channel-log')
logger: logging.Logger = logzero.logger


@k.command('cleanup', admins=True)
async def cleanup(client: KantekClient, chat: Channel, msg: Message,
                  kwargs: Dict, event: Command) -> None:
    """Command to remove Deleted Accounts from a group or network."""
    count_only = kwargs.get('count', False)
    silent = kwargs.get('silent', False)
    if not chat.creator and not chat.admin_rights:
        count_only = True
    waiting_message = None
    if silent:
        await msg.delete()
    else:
        waiting_message = await client.respond(event, 'Starting cleanup. This might take a while.')
    response = await _cleanup_chat(event, count=count_only, progress_message=waiting_message)
    if not silent:
        await client.respond(event, response, reply=False)
    if waiting_message:
        await waiting_message.delete()

async def _cleanup_chat(event, count: bool = False,
                        progress_message: Optional[Message] = None) -> MDTeXDocument:
    chat: Channel = await event.get_chat()
    client: KantekClient = event.client
    user: User
    deleted_users = 0
    deleted_admins = 0
    user_counter = 0
    deleted_accounts_label = Bold('Counted Deleted Accounts' if count else 'Removed Deleted Accounts')
    participant_count = (await client.get_participants(chat, limit=0)).total
    # the number will be 0 if the group has less than 25 participants
    modulus = (participant_count // 25) or 1
    async for user in client.iter_participants(chat):
        if progress_message is not None and user_counter % modulus == 0:
            progress = Section(Bold('Cleanup'),
                               KeyValueItem(Bold('Progress'),
                                            f'{user_counter}/{participant_count}'),
                               KeyValueItem(deleted_accounts_label, deleted_users))
            try:
                await progress_message.edit(str(progress))
            except MessageIdInvalidError:
                progress_message = None
        user_counter += 1
        if user.deleted:
            deleted_users += 1
            if not count:
                try:
                    await client.ban(chat, user)
                except UserAdminInvalidError:
                    deleted_admins += 1
                except FloodWaitError as error:
                    if progress_message is not None:
                        progress = Section(Bold('Cleanup | FloodWait'),
                                           Bold(f'Got FloodWait for {error.seconds}s. Sleeping.'),
                                           KeyValueItem(Bold('Progress'),
                                                        f'{user_counter}/{participant_count}'),
                                           KeyValueItem(deleted_accounts_label, deleted_users))
                        await progress_message.edit(str(progress))

                    tlog.error(error)
                    logger.error(error)
                    await asyncio.sleep(error.seconds)
                    await client.ban(chat, user)

    return MDTeXDocument(
        Section(Bold('Cleanup'),
                KeyValueItem(deleted_accounts_label, deleted_users),
                KeyValueItem(Bold('Deleted Admins'), deleted_admins) if deleted_admins else None))
