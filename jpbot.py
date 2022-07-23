import os
import asyncio

import discord
import youtube_dl

from discord.ext import commands

import threading
import random
import json
from functools import partial
# from flask import Flask, request, jsonify


cringe_compilation = [
    'Usain looks like an older, plumper version of the starving African boy. The one on those commercials. - Logan Paul 2012',
    'Girls tweets always get more favorites and retweets. Only cause they have tits and ass. #Cheaters - Jake Paul 2013',
    "Like a blind man reading I'm feeling it - Jake Paul 2013",
    "Global warming my ass - Jake Paul 2013",
    'Instead of people saying "there are starving kids in Africa, now eat it"  they should say "there\'s starving wrestlers in America ..." - Jake Paul 2012',
    "It's everyday bro, with that disney channel flow - Jake paul 2017",
    "My teachers never taught me that! (My teachers never taught me that!)\nHow to deal with this or that!\nHow to make my papers stack!\nHow to get a DM back\nHow to buy a Lambo cash! - Jake Paul",
    "What are those! - Jake Paul",
    "My teachers never liked me one bit!\nThey said I would amount to be shit! - Jake Paul",
    "They thought I was just another misfit!\nI had to make like a banana and split! - Jake Paul",
    "Doin 60 in Calabasas\nI feel like Kim Kardashian! - Jake Paul",
    "Sorry Kendrick!! \n@kendricklamar\n\nI'll let you have your spot back when the Jake Paulers are done - Jake Paul",
    '"Got them hats" - Jake Paul'
]

script_loc = os.path.abspath(os.path.dirname(__file__))

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''


ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0'  # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn'
}

TOKEN = os.getenv("D_TOKEN")

def remove_file(fpath):
    while True:
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception as e:
                # print("Error while deleting file " + fpath + ": " + str(e))
                pass
        else:
            print("file no more: " + fpath)
            break
    return


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=1):
        super().__init__(source, volume)

        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')


class Music:
    def __init__(self):
        self.audio_list = []
        self.vc = None
        self.loop = asyncio.get_event_loop()
        self.volume = 1
        self.requested_channel = None
        self.norecentcall = True
        self.music_exts = ['mp3', 'm4a', 'aac', 'webm']
        self.downloading = 0
        self.lock = threading.Lock()

    async def join_vc(self, channel):
        """Actually join channel"""
        if self.vc is not None:
            if self.vc.is_connected():
                await self.vc.disconnect()
                self.vc = None

        if channel is not None:
            try:
                self.vc = await channel.connect(timeout=10)
                self.requested_channel = channel
            except Exception as ce:
                return str(ce)
            return None
        return 'Unkonwn Error'

    async def ensure_voice(self, message=None):
        if self.vc is None or not self.vc.is_connected():
            if self.requested_channel is not None:
                if await self.join_vc(self.requested_channel) is None:
                    return None
            if message is not None and message.author.voice:
                err = await self.join_vc(message.author.voice.channel)
                if err is not None:
                    await message.channel.send("Error ensuring voice connection: " + str(err))
                return err
            else:
                await message.channel.send("No cached previous voice channel present")
                return "No cached previous voice channel present"
        return None

    async def reconnect(self, message):
        if self.vc is not None:
            if self.vc.is_connected():
                await self.vc.disconnect()
            self.vc = None
        return await self.ensure_voice(message=message)

    async def join(self, message):
        """Joins a voice channel"""
        if message.author.voice:
            err = await self.join_vc(message.author.voice.channel)
            if err is not None:
                await message.channel.send("Error while joining: " + str(err))
            return err
        else:
            await message.channel.send("User not in a Voice channel")
            return "User not in a Voice channel"

    async def auto_disconnect(self):
        if self.norecentcall:
            await self.stop(None)

    async def playnext(self, text="cmd"):
        # Skip song if already playing
        if self.vc is not None and self.vc.is_playing():
            self.vc.stop()
            return
        # Check if playlist is empty
        if len(self.audio_list) == 0:
            return
        prev_audio_data = self.audio_list[0]
        remove_file(prev_audio_data['ytdata']['jpfilename'])
        self.audio_list = self.audio_list[1:]
        # List is empty
        if len(self.audio_list) == 0:
            if self.downloading == 0:
                if prev_audio_data['message'].channel is not None:
                    await prev_audio_data['message'].channel.send("End of search list")
                self.norecentcall = True
                self.loop.call_later(300, self.loop.create_task, self.auto_disconnect())
            return
        # Ensure voice
        if await self.ensure_voice(message=self.audio_list[0]['message']) is not None:
            return
        title = self.actually_play()
        if self.audio_list[0]['message'].channel is not None and title is not None:
            await self.audio_list[0]['message'].channel.send("Now Playing: {}".format(title))

    def actually_play(self):
        player = YTDLSource(discord.FFmpegPCMAudio(self.audio_list[0]['ytdata']['jpfilename'], **ffmpeg_options),
                            data=self.audio_list[0]['ytdata'],
                            volume=self.volume)
        if self.vc.is_playing():
            self.vc.stop()
            return None
        try:
            self.vc.play(player,
                         after=lambda er: print("Error: " + str(er)) if er else self.loop.create_task(self.playnext()))
        except discord.errors.ClientException as e:
            print("Error in actually play: " + str(e))
        return player.title

    async def skip(self, message):
        """skip"""
        if await self.ensure_voice(message=message) is not None:
            return
        if self.vc.is_playing():
            self.vc.stop()

    async def pause(self, message):
        """pause"""
        if await self.ensure_voice(message=message) is not None:
            return
        if self.vc.is_playing():
            self.vc.pause()
            await message.channel.send("Paused audio")
            return
        if self.vc.is_paused():
            await message.channel.send("Already paused")
            return

    async def resume(self, message):
        """resume lol"""
        if await self.ensure_voice(message=message) is not None:
            return
        if self.vc.is_paused():
            self.vc.resume()
            if message is not None:
                await message.channel.send("Resuming Audio")
            return
        if self.vc.is_playing():
            if message is not None:
                await message.channel.send("Already playing")
            return
        title = self.actually_play()
        if message is not None:
            await message.channel.send('Now playing: {}'.format(title))

    async def queue(self, message):
        """queue print"""
        outslist = ["Queue: "]
        sindex = 1
        for x in self.audio_list:
            outslist.append(str(sindex) + ": " + x['ytdata']['title'])
            sindex += 1
        outslist.append("Downloading: " + str(self.downloading))
        output = '\n'.join(outslist)
        await message.channel.send(output)

    def download_file_yt(self, url="bruh sound effect 2", message=None):
        with self.lock:
            self.downloading += 1
        try:
            print("dl thread start for " + url)
            ytdl = youtube_dl.YoutubeDL(ytdl_format_options)
            data = ytdl.extract_info(url, download=True)
            if 'entries' in data:
                data = data['entries'][0]
            filename = ytdl.prepare_filename(data)
            print("dl thread end for " + url)
        except youtube_dl.utils.DownloadError as e:
            print(str(e))
            print("dl thread end for " + url)
            with self.lock:
                self.loop.create_task(message.channel.send("Error while downloading audio: " + str(e)))
                if self.downloading > 0:
                    self.downloading -= 1
            return False

        data['jpfilename'] = filename
        with self.lock:
            self.loop.create_task(message.channel.send('Downloaded ' + data['title']))
            is_firstaudio = len(self.audio_list) == 0
            self.audio_list += [{'search': url, 'ytdata': data, 'message': message}]
            if data['jpfilename'].split('.')[-1] not in self.music_exts:
                self.music_exts.append(data['jpfilename'].split('.')[-1])
            if is_firstaudio:
                self.loop.create_task(self.resume(message))
            if self.downloading > 0:
                self.downloading -= 1
        return True

    async def play(self, message):
        """Plays from a url (almost anything youtube_dl supports)"""
        self.norecentcall = False
        inp = message.content
        inp = inp.replace(']play', "")
        inp = inp.replace(']p', "")
        # self.loop.create_task(self.download_file_yt(url=inp, message=message))
        pt = threading.Thread(target=self.download_file_yt,
                              kwargs={'url':inp,'message':message},
                              daemon=True)
        pt.start()

    async def stop(self, message):
        """Stops and disconnects the bot from voice"""
        self.requested_channel = None
        if self.vc is not None:
            if self.vc.is_connected():
                await self.vc.disconnect()
            self.vc = None
        for adata in self.audio_list:
            remove_file(adata['ytdata']['jpfilename'])
        for fname in os.listdir():
            if os.path.isfile(fname) and fname.split('.')[-1] in self.music_exts:
                remove_file(fname)
        self.audio_list = []
        self.downloading = 0
        self.norecentcall = True


out_loop = asyncio.get_event_loop()

client = discord.Client()
mplayer = Music()


@client.event
async def on_ready():
    print('Logged in as {0} ({0.id})'.format(client.user))
    print('------')

@client.event
async def on_message(message):
    # print(message.content)
    if message.author == client.user:
        return
    if message.content.startswith(']pause'):
        await mplayer.pause(message)
        return
    if message.content.startswith(']play') or message.content.startswith(']p'):
        await mplayer.play(message)
        return
    if message.content.startswith(']resume'):
        await mplayer.resume(message)
        return
    if message.content.startswith(']stop'):
        await mplayer.stop(message)
        return
    if message.content.startswith(']join'):
        await mplayer.join(message)
        return
    if message.content.startswith(']reconnect'):
        await mplayer.reconnect(message)
        return
    if message.content.startswith(']skip'):
        await mplayer.skip(message)
        return
    if message.content.startswith(']queue'):
        await mplayer.queue(message)
        return
    if message.content.startswith(']cringe'):
        await message.channel.send(cringe_compilation[random.randint(0, len(cringe_compilation) - 1)])
        return


if TOKEN is None:
    print("No Token given... Quitting")
    exit()
# out_loop.create_task(client.run(TOKEN))
client.run(TOKEN)
# flask_app = Flask("app_server")

# @flask_app.route('/add_audio_file', methods=["POST"])
# def add_audio_file():
#     pass

# @flask_app.route('/add_search_term', methods=["POST", "GET"])
# async def add_search_term():
#     await mplayer.search_from_app(request.json()['inp'])
#     return jsonify({})

# flask_app.run(host="0.0.0.0", port=4278)
