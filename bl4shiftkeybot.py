import os
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import discord
import asyncio
import psycopg2
import psycopg2.extras
from dateutil import parser

# --- CONFIG ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
SHIFT_CODE_URL = "https://mentalmars.com/game-news/borderlands-4-shift-codes/"

# --- EMOJIS ---
EMOJI_REWARD = "🎁"
EMOJI_CODE = "🔑"
EMOJI_EXPIRES = "⏰"

# --- DATABASE FUNCTIONS ---
def get_db_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise Exception("DATABASE_URL not set in environment")
    return psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)

def load_posted_codes():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS posted_codes (
            code TEXT PRIMARY KEY,
            reward TEXT,
            expires DATE,
            expires_raw TEXT,
            msg_id BIGINT
        )
    """)
    conn.commit()

    cur.execute("SELECT code, reward, expires, expires_raw, msg_id FROM posted_codes")
    rows = cur.fetchall()
    posted = {}
    for row in rows:
        posted[row["code"]] = row
    cur.close()
    conn.close()
    return posted

def save_posted_code(code, reward, expires, expires_raw, msg_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO posted_codes (code, reward, expires, expires_raw, msg_id)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (code) DO UPDATE SET
            reward = EXCLUDED.reward,
            expires = EXCLUDED.expires,
            expires_raw = EXCLUDED.expires_raw,
            msg_id = EXCLUDED.msg_id
    """, (code, reward, expires, expires_raw, msg_id))
    conn.commit()
    cur.close()
    conn.close()

def delete_posted_code(code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM posted_codes WHERE code = %s", (code,))
    conn.commit()
    cur.close()
    conn.close()

# --- SCRAPER ---
def fetch_shift_codes():
    resp = requests.get(SHIFT_CODE_URL)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table_rows = soup.find_all("tr")
    codes = []
    for row in table_rows:
        code_elem = row.find("code")
        tds = row.find_all("td")
        reward_elem = row.find("strong")
        date_elem = tds[1] if len(tds) > 1 else None

        if code_elem:
            code_text = code_elem.text.strip()
            expiration_text = date_elem.text.strip() if date_elem else "Unknown"
            reward = reward_elem.text.strip() if reward_elem else "Shift Code"

            # Parse expiration date
            try:
                expiration_date = parser.parse(expiration_text).date()
            except:
                expiration_date = None

            codes.append({
                "code": code_text,
                "reward": reward,
                "expires": expiration_date,
                "expires_raw": expiration_text
            })
    return codes

def is_code_expired(entry):
    if entry["expires"]:
        return entry["expires"] < datetime.today().date()
    else:
        try:
            parsed_date = parser.parse(entry["expires_raw"]).date()
            return parsed_date < datetime.today().date()
        except:
            return False

# --- DISCORD FUNCTIONS ---
async def send_discord_messages(codes_to_post, codes_to_delete, posted_codes):
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        channel = client.get_channel(CHANNEL_ID)

        # Delete expired messages
        for code, info in codes_to_delete.items():
            try:
                msg = await channel.fetch_message(info["msg_id"])
                await msg.delete()
                delete_posted_code(code)
            except:
                pass

        # Post new codes
        for code_entry in codes_to_post:
            message = (
                f"{EMOJI_REWARD} **{code_entry['reward']}**\n"
                f"{EMOJI_CODE} `{code_entry['code']}`\n"
                f"{EMOJI_EXPIRES} Expires: {code_entry['expires_raw']}"
                f"\u200b"  # extra line at the end for spacing
            )
            sent_msg = await channel.send(message)
            save_posted_code(
                code_entry["code"],
                code_entry["reward"],
                code_entry["expires"],
                code_entry["expires_raw"],
                sent_msg.id
            )

        await client.close()

    await client.start(DISCORD_TOKEN)

# --- MAIN ---
if __name__ == "__main__":
    posted_codes = load_posted_codes()
    current_codes = fetch_shift_codes()

    # Determine expired codes to delete
    codes_to_delete = {
        code: info
        for code, info in posted_codes.items()
        if is_code_expired(info)
    }

    # Determine new codes to post
    codes_to_post = [
        c for c in current_codes
        if not is_code_expired(c) and c["code"] not in posted_codes
    ]

    # Run Discord posting
    asyncio.run(send_discord_messages(codes_to_post, codes_to_delete, posted_codes))
