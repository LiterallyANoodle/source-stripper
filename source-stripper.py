import discord
import json
import re

class StripperConfiguration:

    configuration = {}

    def __init__(self) -> None:
        try: 
            config_file = open("configuration.json")
            self.configuration = json.loads(config_file.read())
        except:
            print("Error: Unable to load bot configuration.")
            exit()

class Stripper(discord.Client):
    # Suppress error on the User attribute being None since it fills up later
    user: discord.ClientUser
    domain_matchers = []
    link_re = re.compile("^(?:http(s){0,1}://)(.)+\\.(.)+")

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

    async def on_message(self, message):
        # we do not want the bot to reply to itself
        if message.author.id == self.user.id:
            return

        links = self.find_links(message.content)
        stripped_links = self.strip_source_indicators(links)
        stripped_links = [ str(l[0]) for l in stripped_links if (l != None and l[1] > 0) ]
        if len(stripped_links) < 1:
            return
        response = ""
        for l in stripped_links:
            response += (l + "\n")
        await message.edit(suppress=True)
        await message.reply(response, mention_author=False)

    def find_links(self, message):
        links = []
        sliced = str(message).strip()
        splits = []
        while True:
            index = sliced.find("http")
            if index == -1:
                break
            sliced = sliced[index:] # very rarely I've seen links inside links as redirects, so we want to be careful about link identification
            splits = sliced.split(None, 1) # split exactly once at the next whitespace 
            links.append(splits[0])
            if len(splits) > 1:
                sliced = splits[1]
            else: 
                # no more message to read, done
                break
        
        # Verify links since someone could just be having a conversation about http
        return [ l for l in links if self.link_re.match(l) != None ]
    
    def strip_source_indicators(self, links): 
        stripped = []
        for dm in self.domain_matchers: 
            for l in links:
                for d in dm["domains"]:
                    if d in l:
                        stripped.append(re.subn("[?&]" + str(dm["parameter"]["keyword"]) + "=(.){" + str(dm["parameter"]["length"]) + "}", "", l))
        return stripped

if __name__ == "__main__":
    stripper_config = StripperConfiguration().configuration
    intents = discord.Intents.default()
    intents.message_content = True

    client = Stripper(intents=intents)
    client.domain_matchers = stripper_config["domain_matchers"]
    client.run(str(stripper_config["bot_token"]))