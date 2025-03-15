# consumers.py

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.auth import get_user
from urllib.parse import parse_qs
import json

# Ustal swój sekretny klucz do autoryzacji Orange Pi:
ALLOWED_TOKEN = "MOJ_SEKRETNY_TOKEN_123"

class MotorConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # 1) Rozpoznaj użytkownika z sesji (przeglądarka)
        self.user = await get_user(self.scope)

        # 2) Sprawdź token w query stringu (Orange Pi)
        query_params = parse_qs(self.scope["query_string"].decode())
        token = query_params.get("token", [None])[0]

        # WARUNEK MIESZANY: albo zalogowany (is_authenticated), albo poprawny token
        if (self.user and self.user.is_authenticated) or (token == ALLOWED_TOKEN):
            # Dodajemy do grupy i akceptujemy WebSocket
            await self.channel_layer.group_add("motor_control", self.channel_name)
            await self.accept()
        else:
            # Odrzucamy połączenie
            await self.close()

    async def receive(self, text_data):
        """
        Odbiera komendy od klienta i rozsyła do grupy "motor_control".
        Sprawdzamy, czy nadal mamy uprawnienia.
        """
        # Sprawdź ponownie uprawnienia (lub można założyć, że jak connect() przeszedł, to i tak jest ok)
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
        else:
            # Ignorujemy lub zamykamy
            pass

    async def motor_command(self, event):
        """
        Metoda wywoływana przez group_send("motor_command", {...}).
        Wysyłamy informację do WS wszystkich w grupie, ale możemy ponownie zweryfikować uprawnienia.
        """
        query_params = parse_qs(self.scope["query_string"].decode())
        token = query_params.get("token", [None])[0]

        if (self.user and self.user.is_authenticated) or (token == ALLOWED_TOKEN):
            command = event["command"]
            await self.send(text_data=json.dumps({"command": command}))
        else:
            pass
    
    async def settings_update(self, event):
        """
        Wywoływane, gdy serwer (widok) wyśle group_send z type='settings_update'.
        'event' zawiera 'settings_data' = nowe ustawienia
        """
        new_settings = event["settings_data"]
        # Wyślij do wszystkich klientów WebSocket (JSON z polem "type":"settings_update")
        await self.send(text_data=json.dumps({
            "type": "settings_update",
            "settings_data": new_settings
        }))
