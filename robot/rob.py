import asyncio
import websockets
import json
import serial
import os

arduino_port = "/dev/ttyUSB0"
baud_rate = 9600
ser = serial.Serial(arduino_port, baud_rate)

# Ścieżka do lokalnego pliku z ustawieniami
LOCAL_SETTINGS_PATH = "settings.json"

# Zmienna globalna z ustawieniami
local_settings = {}

def load_local_settings():
    """
    Wczytuje plik settings.json z dysku Orange Pi
    i zwraca słownik. Jeśli nie istnieje, tworzy z domyślnymi wartościami.
    """
    if not os.path.exists(LOCAL_SETTINGS_PATH):
        default_data = {
            "step_time_go": 250,
            "step_time_back": 250,
            "step_time_turn": 250,
            "engine_left_calib": 1.0,
            "engine_right_calib": 1.0
        }
        with open(LOCAL_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=4)
        return default_data

    with open(LOCAL_SETTINGS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_local_settings(data):
    """
    Zapisuje słownik `data` do lokalnego pliku settings.json
    """
    with open(LOCAL_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

async def listen():
    global local_settings
    local_settings = load_local_settings()

    # Dodaj token, jeśli wymagany
    uri = "ws://57.128.201.199:8005/ws/control/?token=MOJ_SEKRETNY_TOKEN_123"

    async with websockets.connect(uri) as websocket:
        print("Połączono z serwerem WebSocket (Orange Pi)")

        try:
            while True:
                message = await websocket.recv()
                print(f"Otrzymano wiadomość: {message}")

                data = json.loads(message)
                msg_type = data.get("type")

                # 1) Jeśli to jest event 'settings_update' -> zapisz w pliku
                if msg_type == "settings_update":
                    new_settings = data.get("settings_data", {})
                    print("Aktualizacja ustawień lokalnych z serwera:", new_settings)

                    # Nadpisz nasz plik settings.json i pamięć
                    save_local_settings(new_settings)
                    local_settings = new_settings

                # 2) Jeśli to jest event 'motor_command' (jak w Twoim kacie),
                #    albo "command" wysłane przez panel:
                else:
                    command = data.get("command", "")
                    handle_motor_command(command)
        except websockets.exceptions.ConnectionClosed as e:
            print(f"WebSocket zamknięty: {e}")

def handle_motor_command(command):
    """
    Obsługa komendy i wysyłanie do Arduino
    """
    # Odczyt z globalnych ustawień:
    st_go = local_settings.get("step_time_go", 250)
    st_back = local_settings.get("step_time_back", 250)
    st_turn = local_settings.get("step_time_turn", 250)
    calib_left = local_settings.get("engine_left_calib", 1.0)
    calib_right = local_settings.get("engine_right_calib", 1.0)

    direction1 = 0
    speed1 = 0
    direction2 = 0
    speed2 = 0

    if command == "go":
        # direction1 = 1 -> wprzód, direction2 = 0 -> wprzód
        direction1 = 1
        direction2 = 0
        # prędkość = step_time_go * kalibracja
        speed1 = st_go * calib_left
        speed2 = st_go * calib_right

    elif command == "back":
        direction1 = 0
        direction2 = 1
        speed1 = st_back * calib_left
        speed2 = st_back * calib_right

    elif command == "left":
        # skręt w lewo -> silnik lewy wolniej, silnik prawy szybciej
        # (ale w zależności od Twojej fizycznej konfiguracji)
        direction1 = 0
        direction2 = 0
        speed1 = st_turn * calib_left
        speed2 = st_turn * calib_right

    elif command == "right":
        direction1 = 1
        direction2 = 1
        speed1 = st_turn * calib_left
        speed2 = st_turn * calib_right

    elif command == "stop":
        direction1 = 0
        speed1 = 0
        direction2 = 0
        speed2 = 0

    else:
        print(f"Nieznana komenda: {command}")
        return

    # Wyślij do Arduino
    to_send = f"{direction1},{int(speed1)},{direction2},{int(speed2)}\n"
    ser.write(to_send.encode('utf-8'))
    print(f"Wysłano do Arduino: {to_send}")

if __name__ == "__main__":
    asyncio.run(listen())
