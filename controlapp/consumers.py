# consumers.py

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.auth import get_user
from urllib.parse import parse_qs
import json

# Ustal swój sekretny klucz do autoryzacji Orange Pi:
ALLOWED_TOKEN = "MOJ_SEKRETNY_TOKEN_123"

class MotorConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = await get_user(self.scope)
        query_params = parse_qs(self.scope["query_string"].decode())
        token = query_params.get("token", [None])[0]

        # WARUNEK MIESZANY: albo zalogowany (user.is_authenticated), albo poprawny token
        if (self.user and self.user.is_authenticated) or (token == ALLOWED_TOKEN):
            await self.channel_layer.group_add("motor_control", self.channel_name)
            await self.accept()
        else:
            await self.close()

    async def receive(self, text_data):
        """
        Odbiera komendy z frontu (przeglądarka) ALBO z Orange Pi (również łączy się po WS).
        Rozsyła je do grupy "motor_control".
        """
        query_params = parse_qs(self.scope["query_string"].decode())
        token = query_params.get("token", [None])[0]

        # Jeśli użytkownik uprawniony:
        if (self.user and self.user.is_authenticated) or (token == ALLOWED_TOKEN):
            data = json.loads(text_data)
            # Może to być 'go', 'back', 'camera_on', 'camera_off' itp.
            command = data.get('command', None)

            if command:
                # Wysyłamy do grupy, gdzie wszyscy (w tym Orange Pi) dostaną event
                await self.channel_layer.group_send(
                    "motor_control",
                    {
                        "type": "motor_command",  # event
                        "command": command
                    }
                )

            # Dodatkowo, Orange Pi będzie wysyłał *ramki kamery* w osobnych eventach
            # (np. o typie 'camera_frame'), więc je też wychwytujemy tutaj.
            frame_data = data.get('frame', None)
            if frame_data:
                # Otrzymaliśmy klatkę base64 z Orange Pi.
                # Rozsyłamy do wszystkich w grupie.
                await self.channel_layer.group_send(
                    "motor_control",
                    {
                        "type": "camera_frame",
                        "frame": frame_data
                    }
                )

        else:
            # Brak uprawnień
            pass

    async def motor_command(self, event):
        """
        Wywoływane przez group_send("motor_command", {...}).
        Zawiera 'command'.
        """
        query_params = parse_qs(self.scope["query_string"].decode())
        token = query_params.get("token", [None])[0]

        if (self.user and self.user.is_authenticated) or (token == ALLOWED_TOKEN):
            command = event["command"]
            await self.send(text_data=json.dumps({"command": command}))

    async def camera_frame(self, event):
        """
        Wywoływane przez group_send("camera_frame", {...}).
        Zawiera 'frame' = base64 z Orange Pi.
        """
        query_params = parse_qs(self.scope["query_string"].decode())
        token = query_params.get("token", [None])[0]

        if (self.user and self.user.is_authenticated) or (token == ALLOWED_TOKEN):
            frame_data = event["frame"]  # base64
            # Wysyłamy do przeglądarek, by mogły wyświetlić w <img>
            await self.send(text_data=json.dumps({
                "type": "camera_frame",
                "frame": frame_data
            }))
        else:
            pass

    async def settings_update(self, event):
        """
        Ustawienia silników, jak poprzednio
        """
        new_settings = event["settings_data"]
        await self.send(text_data=json.dumps({
            "type": "settings_update",
            "settings_data": new_settings
        }))
