import json
import os
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import discord
import asyncio

# --- CONFIG ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
CODE_JSON_FILE = "posted_codes.json"
SHIFT_CODE_URL = "https://mentalmars.com/game-news/borderlands-4-shift-codes/"

# --- FUNCTIONS ---

def load_posted_codes():
    if os.path.exists(CODE_JSON_FILE):
        with open(CODE_JSON_FILE, "r") as f:
            return json.load(f)
    return {}

def save_posted_codes(posted_codes):
    with open(CODE_JSON_FILE, "w") as f:
        json.dump(posted_codes, f, indent=2)

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
        return False  # Treat "Unknown" as valid
    return code_entry["expires"] < datetime.today().date()

async def send_discord_messages(codes_to_post, codes_to_delete, posted_codes):
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        channel = client.get_channel(CHANNEL_ID)

        # Delete expired messages
        for msg_id in codes_to_delete.values():
            try:
                msg = await channel.fetch_message(msg_id)
                await msg.delete()
            except:
                pass

        # Post new codes
        for code_entry in codes_to_post:
            message = f"🎁 **{code_entry['reward']}**\n`{code_entry['code']}`\nExpires: {code_entry['expires_raw']}"
            sent_msg = await channel.send(message)
            # Save message ID in JSON
            posted_codes[code_entry["code"]]["msg_id"] = sent_msg.id

        save_posted_codes(posted_codes)
        await client.close()

    await client.start(DISCORD_TOKEN)

# --- MAIN LOGIC ---

if __name__ == "__main__":
    posted_codes = load_posted_codes()
    current_codes = fetch_shift_codes()

    # Determine expired codes to delete from Discord
    codes_to_delete = {}
    for code, entry in posted_codes.items():
        if is_code_expired(entry) and entry.get("msg_id"):
            codes_to_delete[code] = entry.get("msg_id")
            del posted_codes[code]  # Remove expired from JSON

    # Filter out already posted codes and expired codes
    codes_to_post = []
    for code_entry in current_codes:
        code_text = code_entry["code"]
        if code_text not in posted_codes and not is_code_expired(code_entry):
            codes_to_post.append(code_entry)
            posted_codes[code_text] = code_entry  # Add to JSON

    # Run Discord posting
    asyncio.run(send_discord_messages(codes_to_post, codes_to_delete, posted_codes))
