import discord
import pandas as pd
import json

class DiscordCourseBot(discord.Client):
    def __init__(self, student_file, config_file, group_file):
        intents = discord.Intents.all()
        intents.members = True
        super().__init__(intents=intents)
        self.student_file = student_file
        self.config_file = config_file
        self.group_file = group_file
        self.students_df = pd.read_csv(student_file, index_col=0, dtype='str')
        self.groups_df = pd.read_csv(group_file, dtype='str',index_col= 0)
        self.groups_df.group_id = self.groups_df.group_id.astype(int)
        self.config = self.load_config()
        self.roles = self.config['roles']

    def store_students(self):
        self.students_df.to_csv(self.student_file)
    
    def store_group_data(self):
        self.groups_df.to_csv(self.group_file)

    def load_config(self):
        with open(self.config_file, 'r') as f:
            config_data = json.load(f)
        return config_data
    
    def store_config(self):
        with open(self.config_file, 'w') as config_file:
            json.dump(self.config, config_file, indent=4)

    async def on_ready(self):
        print(f'Logged in as {self.user.name} - {self.user.id}')

    async def check_student(self, message):
        content = message.content
        if content in self.students_df.index:
            student_member = message.author
            student_role = discord.utils.get(student_member.guild.roles, id=int(self.config['student_role']))
            if student_role:
                self.students_df.loc[content,'id'] = student_member.id
                self.store_students()
                await student_member.add_roles(student_role)
                await message.add_reaction('✅')
        else:
            if len(content)<=7:
                await message.add_reaction('👎')

    async def print_roles(self, message):
        # Get the guild where the message was sent
        guild = message.guild

        # Iterate over all roles in the guild
        for role in guild.roles:
            await message.channel.send(f"Role Name: {role.name}, Role ID: {role.id}")

    async def on_message(self, message):
        if message.author == self.user:
            return
        
        print(message.channel,message.channel.id)
        print(message.author)
        print(message.content)
        content = message.content
        author = message.author.name

        # Save message and author to a file
        with open('message_log.txt', 'a') as log_file:
            log_file.write(f"{author},{content}\n")
        

        if message.author.id == int(self.config['owner']) and message.channel.name == self.config["command_channel_name"]:
            if content.startswith('help'):
                await message.channel.send(f"delete_group")
                await message.channel.send(f"create_group")
                await message.channel.send(f"hello_world_314159265")
                await message.channel.send(f"create_channels")

            if content.startswith('initial_setup'):
                            await self.setup(message)

            if content.startswith('delete_group'):
                await self.delete_category_with_channels(message,content.split()[-1])
            
            if content.startswith('create_group'):
                words = content.split()
                audio= False
                if words[-1]=='audio':
                    audio= True
                    words= words[:-1]
                await self.create_category_with_channels(message,words[1], words[2:], is_audio=audio)

            if content == 'hello_world_314159265':
                author_name = message.author.name
                author_id = message.author.id
                await self.print_roles(message)
                await message.channel.send(f"Received hello world from {author_name}, ID: {author_id}, channel: {message.channel.id}")
            if content == 'create_channels':
                await self.create_group_channels(message)
            if content == 'get_messages':
                await self.get_old_messages(message)

        if str(message.channel.id) == self.config.get('register_channel',None):
            await self.process_group_registration(message)

        if str(message.channel.id) == self.config.get('dmz_channel',None):
            await self.check_student(message)

    async def clear_messages(self, channel):
        await channel.purge()

    def run(self):
        super().run(self.config['bot_token'])

    async def process_group_registration(self, message):
        content = message.content
        guild = message.guild

        if content.startswith("registrar_grupo"):
            data = content.split(',')[1:]
            if len(self.groups_df) == 0:
                group_id = 1
            else:
                group_id = self.groups_df.group_id.max() + 1

            is_valid = True
            student_not_valid = ''
            for student in data:
                student_ok = (student in self.students_df.index) and not (student in self.groups_df.student.values)
                is_valid = is_valid and student_ok
                if not student_ok:
                    student_not_valid = str(student)
            if is_valid:
                for student in data:
                    self.groups_df = self.groups_df.append({'group_id': group_id, 'student': student.strip()}, ignore_index=True)
                self.store_group_data()
                await message.add_reaction('✅')
            else:
                await message.add_reaction('👎')
                await message.channel.send(f"Grupo invalido, ver {student_not_valid}")

    
    async def setup(self, message):
        guild = message.guild

        # Delete all channels and categories
        for category in guild.categories:
            for channel in category.channels:
                await channel.delete()
            await category.delete()

        for channel in guild.channels:
            await channel.delete()

        # Delete all roles
        for role in guild.roles:
            if role.name != self.config['bot_name']:
                helper_role = role.id
            if role != guild.default_role and role.name != self.config['bot_name']:
                await role.delete()

        role_names = list(map(lambda x: x['name'],self.config['roles'][2:]))
        role_map = {}

        for role_name in role_names:
            role = await guild.create_role(name=role_name)
            role_map[role_name] = role.id

        self.config['roles'][0]['id'] = str(guild.default_role)

        self.config['roles'][1]['id'] = str(helper_role)

        for roles in self.config['roles'][2:]:
            roles['id'] = role_map[roles['name']]

        channel = await guild.create_text_channel(self.config['dmz_channel_name'])
        self.config['dmz_channel'] = str(channel.id)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False)
        }

        await guild.create_text_channel(self.config['command_channel_name'], overwrites=overwrites)

        self.store_config()
        print("All channels, categories, and roles have been deleted. Populate Student Role in config")
    
    async def create_group_channels(self, message):
        guild = message.guild
        category = discord.utils.get(guild.categories, name=self.config['group_category'])
        if not category:
            category = await guild.create_category(self.config['group_category'])

        guild = message.guild
        for group_id in self.groups_df.group_id.unique():
            print(group_id)
            channel_name = f"grupo-{group_id:02}"

            existing_channel = discord.utils.get(guild.channels, name=channel_name)
            if existing_channel:
                continue

            students = self.groups_df[self.groups_df['group_id'] == group_id].student.values
            print(students)
            member_overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
            }

            for student in students:
                print(student)
                discord_id = self.students_df.loc[student]['id']
                member = guild.get_member(discord_id)
                if member:
                    member_overwrites[member] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            for role in self.config['roles'][2:]:
                if str(role["id"]) == str(self.config['student_role']):
                    continue 
                role = discord.utils.get(guild.roles, id=role["id"])
                if not role:
                    continue
                else:
                    member_overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            category = discord.utils.get(guild.categories, name=self.config['group_category'])  # Change to the desired category name
            await guild.create_text_channel(channel_name, category=category, overwrites=member_overwrites)

            print(f"Created channel for group {group_id}")

    async def delete_category_with_channels(self, message, category_name):
        guild = message.guild 

        category = discord.utils.get(guild.categories, name=category_name)
        if category:
            for channel in category.channels:
                await channel.delete()
            await category.delete()
            print(f"Deleted category {category_name} and its channels")

    async def create_category_with_channels(self, message, name, channels, is_audio=False):
        roles=[]
        for role in self.config['roles'][2:]:
            roles.append(role['id']) 
        guild = message.guild

        category = discord.utils.get(guild.categories, name=name)
        if category:
            return
        category = await guild.create_category(name)

        for channel_name in channels:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False)
            }
            for role in roles:
                role = discord.utils.get(guild.roles, id=role)
                if not role:
                    continue
                else:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            if is_audio:
                channel = await guild.create_voice_channel(channel_name, category=category, overwrites=overwrites)
            else:
                channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
            
            await message.channel.send(f"Channel Name: {channel.name}, ID: {channel.id}")

            print(f"Created {'audio' if is_audio else 'text'} channel {channel_name} in category {name}")

    #todo remove message from parameters creating self.guild
    async def get_old_messages(self, message):
        guild = message.guild  # Replace with your guild's ID

        # Find the channel by name

        channel = guild.get_channel(int(self.config['dmz_channel']))

        messages = []
        async for message in channel.history(limit=300):
            if not message.reactions:
                messages.append(message)

        for message in messages:
            await self.check_student(message)

        
        channel = guild.get_channel(int(self.config['register_channel']))

        messages = []
        async for message in channel.history(limit=300):
            if not message.reactions:
                messages.append(message)

        for message in messages:
            await self.process_group_registration(message)

if __name__ == "__main__":
    student_file = './data/alumnos.csv'
    config_file = './data/config.json'
    group_file = './data/grupos.csv'
    
    bot = DiscordCourseBot(student_file, config_file, group_file)
    bot.run()
