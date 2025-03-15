import asyncio
import threading
import websockets
import json
import serial
import os
import av
import io
import base64
from PIL import Image

# WebSocket do Django
SERVER_WS_URL = "ws://57.128.201.199:8005/ws/control/?token=MOJ_SEKRETNY_TOKEN_123"

# Kamera
VIDEO_DEVICE = "/dev/video1"

# Flagi dla sterowania strumieniowaniem obrazu
streaming_active = False
streaming_thread = None

# Ustawienia lokalne
LOCAL_SETTINGS_PATH = "settings.json"

# Port szeregowy do Arduino
arduino_port = "/dev/ttyUSB0"
baud_rate = 9600
ser = serial.Serial(arduino_port, baud_rate)

def load_local_settings():
    """Wczytuje ustawienia lokalne z pliku settings.json"""
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
    """Zapisuje ustawienia lokalne do pliku settings.json"""
    with open(LOCAL_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def stream_camera():
    """Funkcja do strumieniowania obrazu w osobnym wątku"""
    global streaming_active
    container = av.open(VIDEO_DEVICE, format="v4l2")
    frame_counter = 0

    while streaming_active:
        for frame in container.decode(video=0):
            if not streaming_active:
                break

            frame_counter += 1
            if frame_counter % 6 != 0:  # Wysyłaj co 6 klatkę (5 FPS)
                continue

            img = frame.to_image()
            img_io = io.BytesIO()
            img.save(img_io, format="JPEG", quality=75)
            img_bytes = img_io.getvalue()

            # Konwersja do base64
            img_b64 = base64.b64encode(img_bytes).decode()

            asyncio.run(send_frame(img_b64))

    container.close()

async def send_frame(img_b64):
    """Wysyła obraz do serwera Django"""
    try:
        async with websockets.connect(SERVER_WS_URL) as websocket:
            await websocket.send(json.dumps({"image": img_b64}))
    except Exception as e:
        print(f"Błąd podczas wysyłania obrazu: {e}")

async def listen():
    """Nasłuchuje komend z WebSocket serwera Django"""
    global local_settings, streaming_active, streaming_thread
    local_settings = load_local_settings()

    async with websockets.connect(SERVER_WS_URL) as websocket:
        print("Połączono z serwerem WebSocket (Orange Pi)")

        while True:
            message = await websocket.recv()
            print(f"Otrzymano wiadomość: {message}")

            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "settings_update":
                new_settings = data.get("settings_data", {})
                print("Aktualizacja ustawień lokalnych z serwera:", new_settings)
                save_local_settings(new_settings)
                local_settings = new_settings

            elif msg_type == "motor_command":
                command = data.get("command", "")
                handle_motor_command(command)

            elif msg_type == "command":
                command = data.get("command", "")
                if command == "camera_on":
                    if not streaming_active:
                        streaming_active = True
                        streaming_thread = threading.Thread(target=stream_camera, daemon=True)
                        streaming_thread.start()
                elif command == "camera_off":
                    streaming_active = False
                    if streaming_thread:
                        streaming_thread.join()
                        streaming_thread = None
                else:
                    handle_motor_command(command)

def handle_motor_command(command):
    """Obsługuje komendy sterowania pojazdem i wysyła do Arduino"""
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
        direction1 = 1
        direction2 = 0
        speed1 = st_go * calib_left
        speed2 = st_go * calib_right
    elif command == "back":
        direction1 = 0
        direction2 = 1
        speed1 = st_back * calib_left
        speed2 = st_back * calib_right
    elif command == "left":
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

    to_send = f"{direction1},{int(speed1)},{direction2},{int(speed2)}\n"
    ser.write(to_send.encode('utf-8'))
    print(f"Wysłano do Arduino: {to_send}")

if __name__ == "__main__":
    asyncio.run(listen())
