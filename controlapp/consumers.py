# consumers.py

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.auth import get_user
from urllib.parse import parse_qs
import json
import base64

ALLOWED_TOKEN = "MOJ_SEKRETNY_TOKEN_123"

class MotorConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = await get_user(self.scope)
        query_params = parse_qs(self.scope["query_string"].decode())
        token = query_params.get("token", [None])[0]
        
        if (self.user and self.user.is_authenticated) or (token == ALLOWED_TOKEN):
            await self.channel_layer.group_add("motor_control", self.channel_name)
            await self.accept()
        else:
            await self.close()

    async def receive(self, text_data):
        query_params = parse_qs(self.scope["query_string"].decode())
        token = query_params.get("token", [None])[0]
        
        if (self.user and self.user.is_authenticated) or (token == ALLOWED_TOKEN):
            data = json.loads(text_data)
            command = data.get('command', None)
            
            if command:
                await self.channel_layer.group_send(
                    "motor_control",
                    {
                        "type": "motor_command",
                        "command": command
                    }
                )
            
            if "image_front" in data and "image_turret" in data:
                await self.channel_layer.group_send(
                    "motor_control",
                    {
                        "type": "camera_frame",
                        "image_front": data["image_front"],
                        "image_turret": data["image_turret"]
                    }
                )
    
    async def motor_command(self, event):
        query_params = parse_qs(self.scope["query_string"].decode())
        token = query_params.get("token", [None])[0]
        
        if (self.user and self.user.is_authenticated) or (token == ALLOWED_TOKEN):
            command = event["command"]
            await self.send(text_data=json.dumps({"command": command}))
    
    async def camera_frame(self, event):
        """
        Rozsyła do klienta/klientów oba obrazy jednocześnie.
        """
        image_front = event["image_front"]
        image_turret = event["image_turret"]
        await self.send(text_data=json.dumps({
            "image_front": image_front,
            "image_turret": image_turret
        }))
    
    async def settings_update(self, event):
        new_settings = event["settings_data"]
        await self.send(text_data=json.dumps({
            "type": "settings_update",
            "settings_data": new_settings
        }))
