import os
import asyncio
import discord
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from discord.ext import tasks

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))

intents = discord.Intents.default()
client = discord.Client(intents=intents)

# =============== SCRAPER =====================

def scrape_shift_codes():
    url = "https://mentalmars.com/game-news/borderlands-4-shift-codes/"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    codes = []
    tables = soup.find_all("figure", class_="wp-block-table")

    for table in tables:
        # Get category (header text before the table)
        category = "Unknown"
        prev = table.find_previous(["h2", "h3"])
        if prev and prev.get_text(strip=True):
            category = prev.get_text(strip=True)

        rows = table.find("tbody").find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4:
                continue

            reward = cols[0].get_text(strip=True)
            added = cols[1].get_text(strip=True)
            code = cols[2].find("code").get_text(strip=True) if cols[2].find("code") else cols[2].get_text(strip=True)
            expires_raw = cols[3].get_text(strip=True)

            # Normalize expiration date
            expires = None
            if expires_raw and expires_raw != "???":
                try:
                    expires = datetime.strptime(expires_raw, "%b %d, %Y").date().isoformat()
                except ValueError:
                    expires = None

            codes.append({
                "category": category,
                "reward": reward,
                "added": added,
                "code": code,
                "expires_raw": expires_raw,
                "expires": expires,
            })

    return codes

# =============== DISCORD POST LOGIC =====================

async def post_shift_codes():
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print("❌ Channel not found. Check DISCORD_CHANNEL_ID.")
        return

    codes = scrape_shift_codes()
    if not codes:
        await channel.send("⚠️ No SHiFT codes found on the site.")
        return

    # Group by category
    grouped = {}
    for c in codes:
        grouped.setdefault(c["category"], []).append(c)

    for category, items in grouped.items():
        message_lines = [f"**{category}**\n"]
        for item in items:
            reward_text = item["reward"]
            code_text = item["code"]
            expires_text = item["expires_raw"]

            # Message formatting
            message_lines.append(
                f"🎁 **Reward:** {reward_text}\n"
                f"🔑 **Code:** `{code_text}`\n"
                f"⏰ **Expires:** {expires_text}\n"
            )

        message_lines.append("\n—\n💡 Redeem at https://shift.gearboxsoftware.com/rewards\n")
        full_message = "\n".join(message_lines)

        # Discord message size limit safeguard
        if len(full_message) > 1900:
            chunks = [full_message[i:i+1900] for i in range(0, len(full_message), 1900)]
            for chunk in chunks:
                await channel.send(chunk)
        else:
            await channel.send(full_message)

# =============== CRON / BACKGROUND JOB =====================

@tasks.loop(hours=6)
async def scheduled_check():
    print("🔁 Running scheduled SHiFT code check...")
    await post_shift_codes()

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")
    if not scheduled_check.is_running():
        scheduled_check.start()

# =============== ENTRY POINT =====================

async def main():
    await client.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
