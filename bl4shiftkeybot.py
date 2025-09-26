import os
import requests
from bs4 import BeautifulSoup
import discord
import asyncio
import json
from datetime import datetime, timedelta

# ====== CONFIG ======
TOKEN = os.getenv("DISCORD_TOKEN")         # Set in Railway environment
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))  # Set in Railway environment
URL = "https://mentalmars.com/game-news/borderlands-4-shift-codes/"
DATA_FILE = "codes.json"

# ====== SCRAPER ======
def scrape_codes():
    try:
        response = requests.get(URL)
        soup = BeautifulSoup(response.text, "html.parser")
        codes = []

        rows = soup.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 3:
                description = cells[0].get_text(strip=True)
                expires = cells[1].get_text(strip=True)
                code_el = cells[2].find("code")
                if code_el:
                    codes.append({
                        "description": description,
                        "expires": expires,
                        "code": code_el.get_text(strip=True)
                    })
        return codes
    except Exception as e:
        print(f"[ERROR] Scraper failed: {e}")
        return []

# ====== EXPIRATION CHECK ======
def is_expired(expire_str: str) -> bool:
    if expire_str.lower() in ["unknown", "ongoing", "never"]:
        return False
    expire_str = expire_str.replace("Sept", "Sep")
    try:
        expire_date = datetime.strptime(expire_str, "%b %d, %Y")
        return expire_date < datetime.now()
    except Exception:
        return False

# ====== LOAD/SAVE JSON ======
def load_data():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ====== DISCORD BOT ======
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
client = discord.Client(intents=intents)

# ====== MAIN SYNC FUNCTION ======
async def run_shift_sync():
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print(f"[ERROR] Channel not found: {CHANNEL_ID}")
        return

    stored = load_data()
    stored_codes = {e["code"]: e for e in stored}

    # Delete expired messages
    for entry in stored:
        if is_expired(entry["expires"]):
            try:
                msg = await channel.fetch_message(entry["message_id"])
                await msg.delete()
                print(f"[INFO] Deleted expired code: {entry['code']}")
            except Exception as e:
                print(f"[WARN] Could not delete message {entry['code']}: {e}")

    stored = [e for e in stored if not is_expired(e["expires"])]

    # Scrape site
    codes = scrape_codes()
    for entry in codes:
        if is_expired(entry["expires"]):
            continue
        if entry["code"] not in stored_codes:
            msg_text = (
                f"**{entry['description']}**\n"
                f"🗓️ Expires: {entry['expires']}\n"
                f"🔑 Code: `{entry['code']}`"
            )
            try:
                msg = await channel.send(msg_text)
                print(f"[INFO] Posted new code: {entry['code']}")
                stored.append({
                    "code": entry["code"],
                    "expires": entry["expires"],
                    "message_id": msg.id
                })
            except Exception as e:
                print(f"[ERROR] Failed to post {entry['code']}: {e}")

    save_data(stored)
    print(f"[INFO] Sync complete at {datetime.now()}")

# ====== HOURLY SCHEDULER ======
async def hourly_scheduler():
    await client.wait_until_ready()
    while not client.is_closed():
        now = datetime.now()
        # Next run is at HH:01
        next_run = now.replace(minute=1, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(hours=1)
        wait_seconds = (next_run - now).total_seconds()
        print(f"[INFO] Waiting {wait_seconds:.0f}s until next check at {next_run}")
        await asyncio.sleep(wait_seconds)

        # Run main sync
        try:
            await run_shift_sync()
        except Exception as e:
            print(f"[ERROR] Exception during sync: {e}")

@client.event
async def on_ready():
    print(f"[INFO] Logged in as {client.user} (ID: {client.user.id})")
    client.loop.create_task(hourly_scheduler())

client.run(TOKEN)
