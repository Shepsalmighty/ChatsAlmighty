import asyncio
import sqlite3
import asqlite
from contextlib import closing

class DataBaseInterface:

    def __init__(self, file_path, pool):
        # self.channel = target_channel
        self.db_path = file_path
        self.pool = pool

    async def command_exists(self, msg):
        async with self.pool.acquire() as con:
            command = await con.fetchone('''SELECT LOWER(name) FROM commands WHERE name = ?''', (msg,))
            return command is not None

    async def set_command(self, cmd_name, cmd_text):
        async with self.pool.acquire() as con:
            await con.execute('''
            INSERT OR REPLACE INTO commands (`name`, `cmdtext`)
            VALUES (?, ?)''',
            (cmd_name, cmd_text))

    async def get_link(self, cmd):
        async with self.pool.acquire() as con:
            text = await con.fetchone("""SELECT cmd_text FROM commands
                                      WHERE LOWER(name) = (?)""",
                                      (cmd,))
            return text


    async def leave_message(self, sender, reciever, msg):
        async with self.pool.acquire() as con:
            async with con.transaction():
                msg_sent = await con.fetchone('SELECT COUNT (*) FROM messages WHERE sender_id = ?', (sender,))
                msg_count = await con.fetchone('SELECT COUNT (*) FROM messages WHERE sender_id = ? AND receiver_id = ?',
                                               (sender, reciever))
                inbox_full = await con.fetchone('SELECT COUNT (*) FROM messages WHERE receiver_id = ?', (reciever,))
                #if await con.fetchone('SELECT COUNT (`sender_id`) FROM messages WHERE sender_id = ?', (sender,)) < 3:
                if msg_sent[0] >= 5 or msg_count[0] >= 3 or inbox_full[0] >= 69:
                    return
                else:
                    await con.execute(
                        'INSERT INTO messages (`sender_id`, `receiver_id`, `msg_text`) VALUES (?,?,?)',
                        (sender, reciever, " ".join(msg.split()[2:])))


    async def notify(self, chatter_id):
        async with self.pool.acquire() as con:
            user_msgs_count = await con.fetchall("""SELECT COUNT(sender_id), sender_id
                                          FROM messages 
                                          WHERE receiver_id = ? 
                                          GROUP BY sender_id """,
                                          (chatter_id,))
            return user_msgs_count


    async def get_message(self, sender, receiver):
        msg_list = []
        async with self.pool.acquire() as con:
            async with con.transaction():
                messages = await con.fetchall(
                    'SELECT msg_text, uid FROM messages WHERE receiver_id = ? AND sender_id = ? ORDER BY uid ASC',
                    (receiver.id, sender.id))

                if not messages:
                    return msg_list

                uids_to_delete = []
                for msg in messages:
                    msg_list.append(f"From {sender.name}: {msg[0]}")
                    uids_to_delete.append(msg[1])

                if uids_to_delete:
                    await con.execute(
                        f"DELETE FROM messages WHERE uid IN ({','.join(['?'] * len(uids_to_delete))})",
                        tuple(uids_to_delete)
                    )

        return msg_list

    async def clear_inbox(self, user_id):
        async with self.pool.acquire() as con:
            count = await con.fetchone("SELECT COUNT (*) FROM messages WHERE receiver_id = ?", user_id)
            await con.execute("DELETE FROM messages WHERE receiver_id = ?", user_id)

            return count[0]


    async def song_req(self, user:str, song:str) -> None:
        async with self.pool.acquire() as con:
            async with con.transaction():
                song_count = await con.fetchone('SELECT COUNT (*) FROM song_request WHERE user_id = ?', (user,))
                if song_count[0] < 9:
                    await con.execute(
                        'INSERT INTO song_request (`user_id`, `song_request`) VALUES (?,?)',
                        # (msg.chatter.id, msg.text))
                        (user, song))

#TODO finish once player is done
    async def get_song(self):
        async with self.pool.acquire() as con:
            pass

    async def clear_songs(self):
        async with self.pool.acquire() as con:
            await con.execute('DELETE FROM song_request')

    async def remove(self, user_id:str):
        async with self.pool.acquire() as con:
            con.execute('DELETE FROM song_request WHERE user_id = (?) ORDER BY row_id ASC LIMIT 1', (user_id,))