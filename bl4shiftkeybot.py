import os
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import discord
import asyncio

# --- CONFIG ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
SHIFT_CODE_URL = "https://mentalmars.com/game-news/borderlands-4-shift-codes/"

# --- EMOJIS ---
EMOJI_REWARD = "🎁"
EMOJI_CODE = "🔑"
EMOJI_EXPIRES = "⏰"

# --- RAILWAY KV SETUP ---
import requests as kv_requests

KV_API_URL = "https://kv.railway.app/api/v1/key"
KV_PROJECT = os.getenv("RAILWAY_PROJECT_ID")  # your Railway project ID
KV_TOKEN = os.getenv("RAILWAY_TOKEN")        # Railway token with KV access
KV_KEY = "posted_codes"                      # single key to store all posted codes

def get_posted_codes():
    headers = {"Authorization": f"Bearer {KV_TOKEN}"}
    resp = kv_requests.get(f"{KV_API_URL}/{KV_PROJECT}/{KV_KEY}", headers=headers)
    if resp.status_code == 200:
        return resp.json()
    return {}

def save_posted_codes(data):
    headers = {"Authorization": f"Bearer {KV_TOKEN}", "Content-Type": "application/json"}
    kv_requests.put(f"{KV_API_URL}/{KV_PROJECT}/{KV_KEY}", headers=headers, json=data)

# --- FUNCTIONS ---

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
            posted_codes[code_entry["code"]] = {"msg_id": sent_msg.id, "expires_raw": code_entry["expires_raw"], "expires": str(code_entry["expires"])}

        # Save updated codes to KV
        save_posted_codes(posted_codes)

        await client.close()

    await client.start(DISCORD_TOKEN)

# --- MAIN LOGIC ---

if __name__ == "__main__":
    posted_codes = get_posted_codes()
    current_codes = fetch_shift_codes()

    # Expired codes to delete
    codes_to_delete = {code: entry["msg_id"] for code, entry in posted_codes.items() if entry.get("expires") and datetime.strptime(entry["expires"], "%Y-%m-%d").date() < datetime.today().date()}

    # Determine new codes to post
    codes_to_post = []
    for code_entry in current_codes:
        code_text = code_entry["code"]
        if not is_code_expired(code_entry) and code_text not in posted_codes:
            codes_to_post.append(code_entry)

    # Run Discord posting
    asyncio.run(send_discord_messages(codes_to_post, codes_to_delete, posted_codes))
