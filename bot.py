import discord
from discord.ext import commands
import asyncio
import yt_dlp
import os
import edge_tts
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
FFMPEG_PATH = os.getenv('FFMPEG_PATH', 'ffmpeg')

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix='!',
    intents=intents,
    help_command=None,
    case_insensitive=True
)

# Anime OP/ED playlist codes
anime_playlist = {
    "naruto_op": "Naruto Opening 1",
    "bleach_op": "Bleach Opening 2",
    "yourname_ed": "Your Name Sparkle",
    "rezero_op": "Re:Zero Opening 2",
    "aot_op": "Attack on Titan Opening Guren no Yumiya",
    "tokyo_ed": "Tokyo Ghoul Unravel Ending"
    # Add more as needed!
}

ytdl_opts = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'extract_flat': False,
}
ytdl = yt_dlp.YoutubeDL(ytdl_opts)
queues = {}

# Utils
def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = asyncio.Queue()
    return queues[guild_id]

async def yt_audio_url(query):
    """Fetches a YouTube bestaudio stream URL and metadata for the queue."""
    loop = asyncio.get_event_loop()
    if not query.startswith("http"):
        query = f"ytsearch1:{query}"
    def fetch():
        info = ytdl.extract_info(query, download=False)
        if 'entries' in info:
            info = info['entries'][0]
        return {
            'title': info.get('title', 'Unknown'),
            'url': info.get('url'),
            'webpage_url': info.get('webpage_url', None)
        }
    return await loop.run_in_executor(None, fetch)

async def speak_anime_girl(vc, text):
    """Speaks a kawaii anime TTS intro in the VC."""
    if not vc or not vc.is_connected():
        return
    sentence = f"Uwu~ {text} ♪"
    voice = "en-US-JennyNeural"
    out_file = "anime_voice.mp3"
    pitched_file = "pitched_anime_voice.mp3"
    try:
        tts = edge_tts.Communicate(sentence, voice=voice)
        await tts.save(out_file)
        # Slight pitch up for anime vibe
        os.system(f'{FFMPEG_PATH} -y -i "{out_file}" -filter:a "rubberband=pitch=1.08" "{pitched_file}"')
        vc.play(discord.FFmpegPCMAudio(pitched_file, executable=FFMPEG_PATH),
                after=lambda e: os.remove(pitched_file) if os.path.exists(pitched_file) else None)
        while vc.is_playing():
            await asyncio.sleep(1)
        if os.path.exists(out_file): os.remove(out_file)
    except Exception as e:
        print(f"[TTS ERROR] {e}")

async def play_next(ctx):
    """Pops the next song off the queue and plays it, if one exists."""
    queue = get_queue(ctx.guild.id)
    if queue.empty():
        await asyncio.sleep(10)
        if ctx.voice_client and ctx.voice_client.is_connected():
            await ctx.voice_client.disconnect()
            await ctx.send("No more songs in the queue, see you next time! 🌸")
        return
    entry = await queue.get()
    url = entry['url']
    title = entry['title']
    vc = ctx.voice_client
    if not vc:
        await ctx.send("Oops! I'm not connected to voice anymore.")
        return
    await speak_anime_girl(vc, f"Now playing: {title}!")
    try:
        audio = discord.FFmpegPCMAudio(
            url, executable=FFMPEG_PATH,
            before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            options='-vn'
        )
        vc.play(audio, after=lambda e: None)
        await ctx.send(f"🎶 Now playing: **{title}**\n🔗 [Link]({entry.get('webpage_url', '')})")
    except Exception as e:
        await ctx.send(f"❌ Unable to play {title}.\nTry another song!")
        print(f"[STREAM ERROR] {e}")

# ==== MUSIC COMMANDS ====

@bot.command()
async def join(ctx):
    """Join the user's voice channel."""
    if ctx.author.voice:
        await ctx.author.voice.channel.connect()
        await ctx.send(f"Joined {ctx.author.voice.channel.name} 🎀")
    else:
        await ctx.send("Please join a voice channel first, senpai~.")

@bot.command()
async def leave(ctx):
    """Leave the voice channel."""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Bye bye~ I'll be waiting for you! 💖")
    else:
        await ctx.send("I'm not in a voice channel right now.")

@bot.command()
async def sing(ctx, *, query: str):
    """Play a song by name, code, or YouTube link."""
    if not ctx.author.voice:
        await ctx.send("You're not in a voice channel~! 😭")
        return
    vc = ctx.voice_client
    if not vc or not vc.is_connected():
        vc = await ctx.author.voice.channel.connect()

    # Support anime code
    q = anime_playlist.get(query.lower(), query)
    await ctx.send(f"🔎 Finding your song: `{q}`")
    entry = await yt_audio_url(q)
    if not entry or not entry['url']:
        await ctx.send("❌ Couldn't find that song. Try using an actual YouTube title or a valid playlist code!")
        return
    queue = get_queue(ctx.guild.id)
    await queue.put(entry)
    # Queue management
    if vc.is_playing():
        await ctx.send(f"✅ Added to queue: **{entry['title']}**")
    else:
        await play_next(ctx)

@bot.command()
async def queue(ctx):
    """Show current music queue."""
    q = get_queue(ctx.guild.id)
    if q.empty():
        await ctx.send("The queue is empty~! Add something with `!sing`.")
    else:
        items = list(q._queue)
        queue_str = "\n".join([f"{i+1}. {x['title']}" for i, x in enumerate(items)])
        await ctx.send(f"📜 **Current Queue:**\n{queue_str}")

@bot.command()
async def skip(ctx):
    """Skip the current song."""
    vc = ctx.voice_client
    q = get_queue(ctx.guild.id)
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send("⏭️ Skipped!")
        if not q.empty():
            await play_next(ctx)
        else:
            await ctx.send("That's the last song, the queue is now empty.")
    else:
        await ctx.send("There's nothing playing right now.")

@bot.command()
async def pause(ctx):
    """Pause playback."""
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("⏸️ Paused. Say `!resume` to continue!")
    else:
        await ctx.send("I'm not playing anything to pause.")

@bot.command()
async def resume(ctx):
    """Resume playback."""
    vc = ctx.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send("▶️ Resumed~!")
    else:
        await ctx.send("Nothing is paused at the moment.")

@bot.command()
async def playlist(ctx):
    """Show all anime song codes you can use with !sing."""
    txt = "\n".join([f"`{c}` → {anime_playlist[c]}" for c in anime_playlist])
    await ctx.send(f"🎵 **Preloaded Anime Playlist:**\n{txt}")

@bot.command()
async def help(ctx):
    """Show all commands and descriptions."""
    embed = discord.Embed(title="✨ Anime Music Bot — Help", color=discord.Color.purple())
    embed.add_field(name="🟣 Connect / Leave", value="`!join`, `!leave`", inline=False)
    embed.add_field(
        name="🎶 Music",
        value="`!sing <song or anime-code>`\n`!queue` — show queue\n`!pause`/`!resume`\n`!skip` — next song",
        inline=False
    )
    embed.add_field(name="📼 Anime Playlist Codes", value="Use `!playlist` to see codes like `!sing naruto_op`, etc.", inline=False)
    embed.set_footer(text="Type 'kawaii', 'baka', or 'hi' in chat for bonus interactions! — Developed July 2025")
    await ctx.send(embed=embed)

# ==== Anime-style fun chat reactions ====
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    msg = message.content.lower().strip()
    if msg in ["!", "!help"]:
        await help(await bot.get_context(message))
    elif "kawaii" in msg:
        await message.channel.send("Hehe~ Thank you, senpai! 💗")
    elif "baka" in msg:
        await message.channel.send("Nyaa~ That's mean, baka! 😾")
    elif any(w in msg for w in ["hello", "hi", "hey", "ohayo", "konbanwa"]):
        await message.channel.send(f"Yaa~ hello {message.author.display_name}-san! 🌸")
    elif any(w in msg for w in ["sad", "depressed"]):
        await message.channel.send("Don't be sad, I'll sing for you! 🌈🦋")
    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f"✅ Anime Music Bot is ready as {bot.user}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Unknown command. Try `!help`! 💡")
    else:
        raise error

bot.run(TOKEN, reconnect=True)
