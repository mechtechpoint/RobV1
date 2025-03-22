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

def send_two_camera_frames(websocket):
    """
    Funkcja, która jednocześnie pobiera klatki z dwóch urządzeń (/dev/video1 i /dev/video3)
    i wysyła je w jednym komunikacie JSON.
    """
    global camera_running, loop
    try:
        container_front = av.open("/dev/video1", format="v4l2")
        container_turret = av.open("/dev/video3", format="v4l2")

        front_frames = container_front.decode(video=0)
        turret_frames = container_turret.decode(video=0)

        frame_counter = 0

        # Używamy zip, żeby jednocześnie czytać kolejne klatki z obu kamer.
        for front_frame, turret_frame in zip(front_frames, turret_frames):
            if not camera_running:
                break

            # Co ileś klatek wysyłamy, żeby nie przeciążać łącza (tak jak poprzednio co 6)
            if frame_counter % 6 == 0:
                # FRONT
                img_rgb_front = front_frame.to_rgb().to_ndarray()
                pil_front = Image.fromarray(img_rgb_front)
                img_io_front = io.BytesIO()
                pil_front.save(img_io_front, format="JPEG", quality=50)
                img_bytes_front = base64.b64encode(img_io_front.getvalue()).decode('utf-8')

                # TURRET
                img_rgb_turret = turret_frame.to_rgb().to_ndarray()
                pil_turret = Image.fromarray(img_rgb_turret)
                img_io_turret = io.BytesIO()
                pil_turret.save(img_io_turret, format="JPEG", quality=50)
                img_bytes_turret = base64.b64encode(img_io_turret.getvalue()).decode('utf-8')

                # Wysyłamy 2 obrazy w JEDNYM komunikacie
                data_to_send = {
                    "image_front": img_bytes_front,
                    "image_turret": img_bytes_turret
                }

                if loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        websocket.send(json.dumps(data_to_send)),
                        loop
                    )

            frame_counter += 1

        container_front.close()
        container_turret.close()
    except Exception as e:
        print(f"Błąd w send_two_camera_frames: {e}")


def start_camera_thread(websocket):
    global camera_thread, camera_running
    if camera_thread is None or not camera_thread.is_alive():
        camera_running = True
        camera_thread = threading.Thread(target=send_two_camera_frames, args=(websocket,))
        camera_thread.start()

def stop_camera_thread(websocket):
    global camera_running
    camera_running = False
    if camera_thread and camera_thread.is_alive():
        camera_thread.join()

    # Wysłanie pustych obrazów po wyłączeniu kamer (żeby w Django wyczyścić <img>)
    if loop and loop.is_running():
        empty_msg = {"image_front": "", "image_turret": ""}
        asyncio.run_coroutine_threadsafe(
            websocket.send(json.dumps(empty_msg)),
            loop
        )


async def listen():
    global local_settings, loop
    local_settings = load_local_settings()

    uri = "ws://57.128.201.199:8005/ws/control/?token=MOJ_SEKRETNY_TOKEN_123"

    async with websockets.connect(uri) as websocket:
        print("Połączono z serwerem WebSocket (Orange Pi)")
        loop = asyncio.get_running_loop()

        try:
            while True:
                message = await websocket.recv()
                data = json.loads(message)

                if data.get("type") == "settings_update":
                    print("Otrzymano nowe ustawienia, zapisuję i ładuję...")
                    update_local_settings(data["settings_data"])
                    print(f"Nowe ustawienia: {local_settings}")
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
                elif command == "turret_left":
                    print("Turret LEFT – odebrano komendę turret_left (Orange Pi)")
                elif command == "turret_right":
                    print("Turret RIGHT – odebrano komendę turret_right (Orange Pi)")
                elif command == "turret_stop":
                    print("Turret RIGHT – odebrano komendę turret_stop (Orange Pi)")
                else:
                    continue

        except websockets.exceptions.ConnectionClosed as e:
            print(f"WebSocket zamknięty: {e}")

def update_local_settings(new_settings):
    """ Zapisuje nowe ustawienia do settings.json i aktualizuje zmienną globalną """
    global local_settings
    save_local_settings(new_settings)  # Zapisz do pliku
    local_settings = load_local_settings()  # Wczytaj do globalnej zmiennej

def handle_motor_command(command):
    """ Używa globalnej zmiennej `local_settings` zamiast czytać plik za każdym razem """
    global local_settings

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
