import os
import asyncio
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from dateutil import parser
import psycopg2
import discord

# --- Discord / DB setup ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")

EMOJI_REWARD = "🎁"
EMOJI_CODE = "🟩"
EMOJI_EXPIRES = "⏰"

SHIFT_URL = "https://mentalmars.com/game-news/borderlands-4-shift-codes/"

# --- Scraper ---
def scrape_shift_codes():
    resp = requests.get(SHIFT_URL)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.find_all("tr")
    codes = []

    for row in rows:
        tds = row.find_all("td")
        if len(tds) < 3:
            continue

        reward_td = tds[0]
        reward = " ".join(reward_td.get_text(separator=" ").split()) or "Shift Code"

        expires_raw = tds[1].get_text(strip=True)
        try:
            expires = parser.parse(expires_raw).date()
        except (ValueError, TypeError):
            expires = None

        code_elem = tds[2].find("code")
        if not code_elem:
            continue
        code = code_elem.get_text(strip=True)

        codes.append({
            "reward": reward,
            "code": code,
            "expires": expires,
            "expires_raw": expires_raw
        })
    return codes

# --- Database ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def load_posted_codes():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS posted_codes (
            code TEXT PRIMARY KEY,
            reward TEXT,
            expires DATE,
            expires_raw TEXT,
            discord_msg_id BIGINT
        )
    """)
    conn.commit()
    cur.execute("SELECT code, discord_msg_id, expires FROM posted_codes")
    rows = cur.fetchall()
    conn.close()
    return {row[0]: {"discord_msg_id": row[1], "expires": row[2]} for row in rows}

def save_posted_code(code, reward, expires, expires_raw, discord_msg_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO posted_codes (code, reward, expires, expires_raw, discord_msg_id)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (code) DO UPDATE SET discord_msg_id = EXCLUDED.discord_msg_id
    """, (code, reward, expires, expires_raw, discord_msg_id))
    conn.commit()
    conn.close()

def delete_posted_code(code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM posted_codes WHERE code = %s", (code,))
    conn.commit()
    conn.close()

# --- Discord posting logic ---
async def post_all_codes(channel):
    posted_codes = load_posted_codes()
    current_codes = scrape_shift_codes()
    today = datetime.utcnow().date()

    # Delete expired codes
    for code, info in posted_codes.items():
        if info["expires"] and info["expires"] < today:
            try:
                msg = await channel.fetch_message(info["discord_msg_id"])
                await msg.delete()
            except Exception:
                pass
            delete_posted_code(code)

    # Post new codes
    for code_entry in current_codes:
        if code_entry["code"] in posted_codes:
            continue
        if code_entry["expires"] and code_entry["expires"] < today:
            continue

        reward_text = " ".join(code_entry['reward'].split())
        message = (
            f"{EMOJI_REWARD} **{reward_text}**\n"
            f"{EMOJI_CODE} `{code_entry['code']}`\n"
            f"{EMOJI_EXPIRES} Expires: {code_entry['expires_raw']}\n"
            f"\u200b"  # extra spacing line
        )
        sent_msg = await channel.send(message)
        save_posted_code(
            code_entry["code"],
            code_entry["reward"],
            code_entry["expires"],
            code_entry["expires_raw"],
            sent_msg.id
        )

# --- Main (cron-friendly) ---
async def main():
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    await client.login(DISCORD_TOKEN)
    channel = await client.fetch_channel(CHANNEL_ID)
    await post_all_codes(channel)
    await client.close()  # clean exit

if __name__ == "__main__":
    asyncio.run(main())
