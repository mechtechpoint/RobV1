import asyncio
import websockets
import json
import serial
import os
import threading
import av
import base64
import numpy as np
import io
from PIL import Image

arduino_port = "/dev/ttyUSB0"
baud_rate = 9600
ser = serial.Serial(arduino_port, baud_rate)

LOCAL_SETTINGS_PATH = "settings.json"
local_settings = {}

camera_thread = None
camera_running = False
loop = None  # Przechowuje event loop dla WebSocket

def load_local_settings():
    """ Wczytuje plik settings.json za każdym razem, gdy jest potrzebny """
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
    """ Zapisuje dane do settings.json """
    with open(LOCAL_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def send_camera_frames(websocket):
    global camera_running, loop
    container = av.open("/dev/video1", format="v4l2")
    frame_counter = 0
    
    for frame in container.decode(video=0):
        if not camera_running:
            break
        
        if frame_counter % 3 == 0:
            frame_counter = 0
            img_rgb = frame.to_rgb().to_ndarray()
            pil_image = Image.fromarray(img_rgb)
            img_io = io.BytesIO()
            pil_image.save(img_io, format="JPEG", quality=50)
            img_bytes = base64.b64encode(img_io.getvalue()).decode('utf-8')
            
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(websocket.send(json.dumps({"image": img_bytes})), loop)
        
        frame_counter += 1
        

    
    container.close()

def start_camera_thread(websocket):
    global camera_thread, camera_running
    if camera_thread is None or not camera_thread.is_alive():
        camera_running = True
        camera_thread = threading.Thread(target=send_camera_frames, args=(websocket,))
        camera_thread.start()

def stop_camera_thread(websocket):
    global camera_running
    camera_running = False
    if camera_thread:
        camera_thread.join()
    
    # Wysłanie pustego obrazu po wyłączeniu kamery
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(websocket.send(json.dumps({"image": ""})), loop)

async def listen():
    global local_settings, loop
    local_settings = load_local_settings()  # Pierwsze wczytanie ustawień

    uri = "ws://57.128.201.199:8005/ws/control/?token=MOJ_SEKRETNY_TOKEN_123"

    async with websockets.connect(uri) as websocket:
        print("Połączono z serwerem WebSocket (Orange Pi)")
        loop = asyncio.get_running_loop()

        try:
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                
                # Jeśli serwer wysłał aktualizację ustawień
                if data.get("type") == "settings_update":
                    print("Otrzymano aktualizację ustawień, ponowne wczytanie...")
                    local_settings = load_local_settings()
                    continue

                command = data.get("command", "")
                
                if command == "camera_on":
                    print("Uruchamiam kamerę...")
                    start_camera_thread(websocket)
                elif command == "camera_off":
                    print("Wyłączam kamerę...")
                    stop_camera_thread(websocket)
                elif command in ["go", "back", "left", "right", "stop"]:
                    handle_motor_command(command)
                else:
                    # Ignorujemy nieznane komendy zamiast ich wypisywać
                    continue
        except websockets.exceptions.ConnectionClosed as e:
            print(f"WebSocket zamknięty: {e}")

def handle_motor_command(command):
    """ Pobiera NAJNOWSZE ustawienia przed wysłaniem do Arduino """
    global local_settings
    local_settings = load_local_settings()  # Dynamicznie wczytujemy ustawienia

    st_go = local_settings.get("step_time_go", 250)
    st_back = local_settings.get("step_time_back", 250)
    st_turn = local_settings.get("step_time_turn", 250)
    calib_left = local_settings.get("engine_left_calib", 1.0)
    calib_right = local_settings.get("engine_right_calib", 1.0)
    
    direction1, speed1, direction2, speed2 = 0, 0, 0, 0
    
    if command == "go":
        direction1, direction2 = 1, 0
        speed1, speed2 = st_go * calib_left, st_go * calib_right
    elif command == "back":
        direction1, direction2 = 0, 1
        speed1, speed2 = st_back * calib_left, st_back * calib_right
    elif command == "left":
        direction1, direction2 = 0, 0
        speed1, speed2 = st_turn * calib_left, st_turn * calib_right
    elif command == "right":
        direction1, direction2 = 1, 1
        speed1, speed2 = st_turn * calib_left, st_turn * calib_right
    elif command == "stop":
        direction1, speed1, direction2, speed2 = 0, 0, 0, 0
    
    to_send = f"{direction1},{int(speed1)},{direction2},{int(speed2)}\n"
    ser.write(to_send.encode('utf-8'))
    print(f"Wysłano do Arduino: {to_send}")

if __name__ == "__main__":
    asyncio.run(listen())
