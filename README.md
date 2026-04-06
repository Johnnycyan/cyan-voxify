# Voxify

A Discord bot that reads configured users' messages aloud in voice channels using Mistral's Voxtral TTS.

## Quick Start

1. **Clone & configure**
   ```bash
   cp .env.example .env
   # Fill in DISCORD_TOKEN and DB_ENCRYPTION_KEY
   ```

   Generate an encryption key:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. **Run with Docker**
   ```bash
   docker compose up -d
   ```

3. **First-time setup** (in Discord)
   ```
   /config global admin user:@YourUser
   /config global apikey key:sk-...
   /config guild add-speaker user:@Speaker voice_id:your-voxtral-voice-id
   ```

4. **Use it**
   - Speaker joins a voice channel
   - Speaker (or admin) runs `/tts`
   - Messages from the speaker in that text channel are read aloud
   - `/stop` to end the session

## Commands

### `/tts [user]`
Start TTS. Speakers target themselves automatically. Admins can specify a user.

### `/stop`
Stop the session. Speakers remove only themselves; admin stops the whole session.

### `/config global admin <user>`
Set the bot admin. First caller bootstraps if no admin exists.

### `/config global apikey <key>`
Set the Mistral API key (stored encrypted, never displayed).

### `/config global idle-timeout <seconds>`
Max idle timeout across all guilds. `0` to clear.

### `/config global report <enabled> [guild_id] [channel_id]`
Toggle end-of-session reports.

### `/config global show`
View current global settings.

### `/config guild add-speaker <user> <voice_id>`
Map a Discord user to a Voxtral voice ID.

### `/config guild remove-speaker <user>`
Remove a speaker mapping.

### `/config guild list-speakers`
List all configured speakers.

### `/config guild whitelist-add <channel>`
Add a channel to the response whitelist.

### `/config guild whitelist-remove <channel>`
Remove a channel from the whitelist.

### `/config guild whitelist-clear`
Clear the whitelist (allow all channels).

### `/config guild whitelist-show`
Show whitelisted channels.

### `/config guild idle-timeout <seconds>`
Guild-specific idle timeout. Capped by the global maximum. `0` to clear.

## Requirements

- Python 3.11+
- FFmpeg (included in Docker image)
- A Mistral API key with Voxtral TTS access
- A Discord bot token with Message Content, Voice States, and Server Members intents enabled

## Running Without Docker

```bash
python -m venv .venv
.venv/Scripts/activate   # Windows
pip install -r requirements.txt
python -m bot.main
```
