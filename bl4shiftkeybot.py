import json
import os
import requests
from datetime import datetime
from bs4 import BeautifulSoup
import discord

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

        if code_elem:
            code_text = code_elem.text.strip()
            expiration_text = date_elem.text.strip() if date_elem else "Unknown"
            # Parse expiration date
            try:
                expiration_date = datetime.strptime(expiration_text, "%b %d, %Y").date()
            except:
                expiration_date = None
            codes.append({
                "code": code_text,
                "expires": expiration_date,
                "expires_raw": expiration_text
            })
    return codes

def is_code_expired(code_entry):
    if code_entry["expires"] is None:
        return False
    return code_entry["expires"] < datetime.today().date()

async def send_discord_messages(codes_to_post, codes_to_delete):
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
            message = (
                f"**{code_entry.get('reward','Shift Code')}**\n"
                f"`{code_entry['code']}`\n"
                f"Expires: {code_entry['expires_raw']}"
            )
            sent_msg = await channel.send(message)
            code_entry["msg_id"] = sent_msg.id

        # Save updated posted codes
        save_posted_codes(posted_codes)
        await client.close()

    await client.start(DISCORD_TOKEN)

# --- MAIN LOGIC ---

if __name__ == "__main__":
    posted_codes = load_posted_codes()
    current_codes = fetch_shift_codes()

    # Determine expired codes (to delete from Discord)
    codes_to_delete = {}
    for code, entry in posted_codes.items():
        if is_code_expired(entry):
            codes_to_delete[code] = entry.get("msg_id")
    
    # Filter out expired codes and already posted codes
    codes_to_post = []
    for code_entry in current_codes:
        code_text = code_entry["code"]
        if code_text not in posted_codes and not is_code_expired(code_entry):
            codes_to_post.append(code_entry)
            posted_codes[code_text] = code_entry  # Add to JSON record

    import asyncio
    asyncio.run(send_discord_messages(codes_to_post, codes_to_delete))
