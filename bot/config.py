import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN: str = os.environ["DISCORD_TOKEN"]
DB_ENCRYPTION_KEY: str = os.environ["DB_ENCRYPTION_KEY"]
DB_PATH: str = os.getenv("DB_PATH", "data/voxify.db")
