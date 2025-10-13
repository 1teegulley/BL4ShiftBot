async def send_discord_messages(codes_to_post, codes_to_delete, posted_codes):
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"✅ Logged in as {client.user} — connected to Discord")
        channel = client.get_channel(CHANNEL_ID)
        if not channel:
            print(f"❌ Channel not found for ID {CHANNEL_ID}")
            await client.close()
            return

        # Delete expired messages
        for code, info in codes_to_delete.items():
            try:
                msg = await channel.fetch_message(info["msg_id"])
                await msg.delete()
                delete_posted_code(code)
                print(f"🗑️ Deleted expired code {code}")
            except Exception as e:
                print(f"⚠️ Failed to delete message for {code}: {e}")

        # Post new codes
        for code_entry in codes_to_post:
            try:
                message = (
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
                print(f"📩 Posted new code: {code_entry['code']}")
            except Exception as e:
                print(f"⚠️ Failed to send message for {code_entry['code']}: {e}")

        await client.close()
        print("👋 Discord client closed cleanly")

    try:
        await client.start(DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ Discord client failed to start: {e}")
        await client.close()
