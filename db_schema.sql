CREATE TABLE IF NOT EXISTS commands(
            name TEXT PRIMARY KEY,
            cmd_text TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS messages(
            uid INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            msg_text TEXT NOT NULL,
            UNIQUE(sender_id, receiver_id));

CREATE TABLE IF NOT EXISTS user_perms(
            user_id TEXT PRIMARY KEY,
            has_perms INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS song_request(
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            song_request TEXT NOT NULL,
            UNIQUE(user_id, song_request),
            FOREIGN KEY (user_id) REFERENCES user_perms(user_id));


--create indexes for performance on often queried fields:
CREATE INDEX IF NOT EXISTS idx_user_id ON user_perms(user_id, has_perms);
CREATE INDEX IF NOT EXISTS idx_song_request ON song_request(user_id, song_request);

--------------------------------------------------------------------------------------------------

---------------------------------------------------------------------------------------------------



-- JUST TESTING DB WORKS


--INSERT INTO channels (name) VALUES ("test");
--INSERT INTO commands (channel_id, name) VALUES ((SELECT uid FROM channels WHERE name = "test"), "test command");
--INSERT INTO links (linktext, command_id) VALUES ("test link", (SELECT uid FROM commands WHERE name = "test command"));

-- get uid from channel
--SELECT uid FROM channels WHERE name = "test";

-- get uid from commmand_name // CHECK COMMAND EXISTS FOR CHANNEL
--SELECT uid FROM commands WHERE name = "test command" AND channel_id  = (SELECT uid FROM channels WHERE name = "test")

-- get link from links table where the command id/uid relates
--SELECT linktext FROM links WHERE command_id = (SELECT uid from commands WHERE name = "test command" AND channel_id  = (SELECT uid FROM channels WHERE name = "test"))

--RETRIEVES LINK
--SELECT l.linktext FROM links l JOIN commands c ON l.command_id = c.uid JOIN channels ch ON c.channel_id = ch.uid
--WHERE c.name = 'test command' AND ch.name = 'test';

--INSERT LINK INTO TABLE (FOR !SET)
--INSERT INTO links (linktext, command_id) VALUES ("test link", (SELECT uid FROM commands WHERE name = "test command"));

--INSERT INTO links VALUES "example link text"; INSERT INTO commands VALUES "command name"; SELECT