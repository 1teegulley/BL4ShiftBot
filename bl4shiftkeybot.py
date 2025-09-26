import os
import json
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import discord
import asyncio
import subprocess
import shlex

# --- CONFIG ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
SHIFT_CODE_URL = "https://mentalmars.com/game-news/borderlands-4-shift-codes/"
KV_ENV_VAR = "POSTED_CODES"
RAILWAY_PROJECT_ID = os.getenv("RAILWAY_PROJECT_ID")  # Must be set in Railway env
RAILWAY_TOKEN = os.getenv("RAILWAY_TOKEN")            # Must be set in Railway env

# --- EMOJIS ---
EMOJI_REWARD = "🎁"
EMOJI_CODE = "🔑"
EMOJI_EXPIRES = "⏰"

# --- KV FUNCTIONS ---
def load_posted_codes():
    data = os.getenv(KV_ENV_VAR, "{}")
    try:
        return json.loads(data)
    except:
        return {}

def save_posted_codes(posted_codes):
    """Automatically update Railway environment variable"""
    json_data = json.dumps(posted_codes)
    cmd = f'railway env set {KV_ENV_VAR} "{json_data}" --project {RAILWAY_PROJECT_ID}'
    # Run Railway CLI with token from environment
    env = os.environ.copy()
    env["RAILWAY_TOKEN"] = RAILWAY_TOKEN
    subprocess.run(shlex.split(cmd), env=env)

# --- SCRAPER ---
def fetch_shift_codes():
    resp = requests.get(SHIFT_CODE_URL)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table_rows = soup.find_all("tr")
    codes = []
    for row in table_rows:
        code_elem = row.find("code")
        date_elem = row.find_all("td")[1] if len(row.find_all("td")) > 1 else None
        reward_elem = row.find("strong")

        if code_elem:
            code_text = code_elem.text.strip()
            expiration_text = date_elem.text.strip() if date_elem else "Unknown"
            reward = reward_elem.text.strip() if reward_elem else "Shift Code"

            # Parse expiration date
            try:
                expiration_date = datetime.strptime(expiration_text, "%b %d, %Y").date()
            except:
                expiration_date = None

            codes.append({
                "code": code_text,
                "reward": reward,
                "expires": expiration_date,
                "expires_raw": expiration_text
            })
    return codes

def is_code_expired(code_entry):
    if code_entry["expires"] is None:
        return False
    return code_entry["expires"] < datetime.today().date()

# --- DISCORD FUNCTIONS ---
async def send_discord_messages(codes_to_post, codes_to_delete, posted_codes):
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        channel = client.get_channel(CHANNEL_ID)

        # Delete expired messages
        for code, msg_id in codes_to_delete.items():
            try:
                msg = await channel.fetch_message(msg_id)
                await msg.delete()
                posted_codes.pop(code, None)
            except:
                pass

        # Post new codes
        for code_entry in codes_to_post:
            message = (
                f"{EMOJI_REWARD} **{code_entry['reward']}**\n"
                f"{EMOJI_CODE} `{code_entry['code']}`\n"
                f"{EMOJI_EXPIRES} Expires: {code_entry['expires_raw']}"
            )
            sent_msg = await channel.send(message)
            posted_codes[code_entry["code"]] = {
                "msg_id": sent_msg.id,
                "expires_raw": code_entry["expires_raw"],
                "expires": str(code_entry["expires"])
            }

        # Persist posted codes
        save_posted_codes(posted_codes)
        await client.close()

    await client.start(DISCORD_TOKEN)

# --- MAIN ---
if __name__ == "__main__":
    posted_codes = load_posted_codes()
    current_codes = fetch_shift_codes()

    # Determine expired codes to delete
    codes_to_delete = {
        code: info["msg_id"]
        for code, info in posted_codes.items()
        if info.get("expires") and datetime.strptime(info["expires"], "%Y-%m-%d").date() < datetime.today().date()
    }

    # Determine new codes to post
    codes_to_post = [
        c for c in current_codes
        if not is_code_expired(c) and c["code"] not in posted_codes
    ]

    # Run Discord posting
    asyncio.run(send_discord_messages(codes_to_post, codes_to_delete, posted_codes))
