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
# EMOJI_CATEGORY = "📦" --Category coded in, not needed

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
    resp = requests.get(SHIFT_CODE_URL, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    codes = []
    tables = soup.find_all("figure", class_="wp-block-table")

    for table in tables:
        # Get section title (category) before the table
        #category_header = table.find_previous(["h2", "h3"]) --Category coded in, not needed
        #category = category_header.get_text(strip=True) if category_header else "Unknown" --Category coded in, not needed

        rows = table.find_all("tr")
        for row in rows:
            tds = row.find_all("td")
            if not tds or len(tds) < 3:
                continue

            # reward (now can be links <a> instead of <strong>)
            reward_td = tds[0]
            reward = " ".join(reward_td.stripped_strings) if reward_td else "Shift Code"

            # expiration
            date_td = tds[-1]
            expiration_text = date_td.get_text(strip=True) if date_td else "Unknown"

            # code (still inside <code>)
            code_elem = row.find("code")
            code_text = code_elem.text.strip() if code_elem else None

            if not code_text:
                continue

            # Parse expiration date safely
            try:
                expiration_date = parser.parse(expiration_text).date()
            except Exception:
                expiration_date = None

            codes.append({
                #"category": category, --Category coded in, not needed
                "code": code_text,
                "reward": reward,
                "expires": expiration_date,
                "expires_raw": expiration_text
            })

    return codes

# --- EXPIRATION CHECK ---
def is_code_expired(entry):
    if entry["expires"]:
        return entry["expires"] < datetime.today().date()
    else:
        try:
            parsed_date = parser.parse(entry["expires_raw"]).date()
            return parsed_date < datetime.today().date()
        except Exception:
            return False

# --- DISCORD POSTER ---
async def send_discord_messages(codes_to_post, codes_to_delete, posted_codes):
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        channel = client.get_channel(CHANNEL_ID)

        # Delete expired posts
        for code, info in codes_to_delete.items():
            try:
                msg = await channel.fetch_message(info["msg_id"])
                await msg.delete()
                delete_posted_code(code)
            except Exception:
                pass

        # Post new codes
        for code_entry in codes_to_post:
            #category = code_entry.get("category", "Unknown") --Category coded in, not needed
            message = (
                #f"{EMOJI_CATEGORY} **{category}**\n" --Category coded in, not needed
                f"{EMOJI_REWARD} **{code_entry['reward']}**\n"
                f"{EMOJI_CODE} `{code_entry['code']}`\n"
                f"{EMOJI_EXPIRES} Expires: {code_entry['expires_raw']}\n"
                f"\u200b"
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

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    posted_codes = load_posted_codes()
    current_codes = fetch_shift_codes()

    # Find expired codes to delete
    codes_to_delete = {
        code: info
        for code, info in posted_codes.items()
        if is_code_expired(info)
    }

    # Find new codes to post
    codes_to_post = [
        c for c in current_codes
        if not is_code_expired(c) and c["code"] not in posted_codes
    ]

    # Run Discord update
    asyncio.run(send_discord_messages(codes_to_post, codes_to_delete, posted_codes))
