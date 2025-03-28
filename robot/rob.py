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
import subprocess
import time

arduino_port = "/dev/ttyUSB0"
baud_rate = 9600
ser = serial.Serial(arduino_port, baud_rate)

LOCAL_SETTINGS_PATH = "settings.json"
local_settings = {}

camera_thread = None
camera_running = False
loop = None  # Przechowuje event loop dla WebSocket


def find_cameras():
    """
    Zwraca słownik o strukturze:
    {
      "Integrated Camera: Integrated C (usb-5311000.usb-1.1)": ["/dev/video3", "/dev/video4"],
      "Integrated Camera: Integrated C (usb-xhci-hcd.1.auto-1.1)": ["/dev/video1", "/dev/video2"],
      ...
    }
    """
    devices = {}
    output = subprocess.check_output(["v4l2-ctl", "--list-devices"]).decode("utf-8", errors="replace")
    lines = [line.strip() for line in output.split("\n") if line.strip()]
    
    current_title = None
    for line in lines:
        if line.startswith("/dev/video"):
            # to jest linia z ścieżką urządzenia np. "/dev/video1"
            if current_title is not None:
                devices[current_title].append(line)
        else:
            # to jest nazwa "nagłówkowa", np. "Integrated Camera: Integrated C (usb-5311000.usb-1.1)"
            current_title = line
            devices[current_title] = []
    
    return devices

def get_my_cameras():
    """
    Zwraca krotkę (front_dev, turret_dev), próbując otworzyć kolejne /dev/videoX
    skojarzone z front_substring i turret_substring.
    """
    all_cameras = find_cameras()
    
    turret_substring = "usb-5311000.usb-1.1"      # dopasuj do nazwy z `v4l2-ctl --list-devices`
    front_substring  = "usb-xhci-hcd.1.auto-1.1" # dopasuj do nazwy z `v4l2-ctl --list-devices`
    
    turret_dev = None
    front_dev = None

    for camera_title, dev_paths in all_cameras.items():
        # Jeżeli ta kamera w tytule ma substring "turret"
        if turret_substring in camera_title:
            for path in dev_paths:
                try:
                    test = av.open(path, format="v4l2")
                    test.close()
                    # Jeśli udało się otworzyć, to bierzemy tę ścieżkę i kończymy
                    turret_dev = path
                    break
                except Exception as e:
                    print(f"Nie udało się otworzyć turret_dev {path}: {e}")
        
        # Jeżeli ta kamera w tytule ma substring "front"
        elif front_substring in camera_title:
            for path in dev_paths:
                try:
                    test = av.open(path, format="v4l2")
                    test.close()
                    # Jeśli się udało, wybieramy tę ścieżkę
                    front_dev = path
                    break
                except Exception as e:
                    print(f"Nie udało się otworzyć front_dev {path}: {e}")

    return front_dev, turret_dev



def load_local_settings():
    """ Wczytuje plik settings.json za każdym razem, gdy jest potrzebny """
    if not os.path.exists(LOCAL_SETTINGS_PATH):
        default_data = {
            "step_time_go": 250,
            "step_time_back": 250,
            "step_time_turn": 250,
            "engine_left_calib": 1.0,
            "engine_right_calib": 1.0,
            "step_time_turret": 500.0,
            "steps_turret": 200
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

def convert_frame_to_jpeg_base64(frame):
    """
    Konwertuje klatkę z PyAV (av.VideoFrame) do base64 w formacie JPEG.
    """
    # Krok 1: zamieniamy ramkę z PyAV na tablicę w formacie RGB
    img_rgb = frame.to_rgb().to_ndarray()

    # Krok 2: tworzymy obraz PIL z tablicy
    pil_img = Image.fromarray(img_rgb)

    # Krok 3: kompresja do JPEG w pamięci
    buffer = io.BytesIO()
    pil_img.save(buffer, format="JPEG", quality=50)  # quality możesz dowolnie zmienić

    # Krok 4: konwersja bufora do base64
    base64_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return base64_str



def send_two_camera_frames(websocket):
    global camera_running, loop
    try:
        front_dev, turret_dev = get_my_cameras()
        container_front = av.open(f"{front_dev}", format="v4l2")
        container_turret = av.open(f"{turret_dev}", format="v4l2")

        front_stream = container_front.streams.video[0]
        turret_stream = container_turret.streams.video[0]


        while camera_running:
            # Pobierz maksymalnie 1 klatkę z front i 1 z turret (odrzuć resztę)
            front_packet = next(container_front.demux(front_stream), None)
            turret_packet = next(container_turret.demux(turret_stream), None)
            
            if front_packet is None or front_packet.is_corrupt:
                continue
            if turret_packet is None or turret_packet.is_corrupt:
                continue

            try:
                front_frames = front_packet.decode()
                turret_frames = turret_packet.decode()
            except:
                continue

            if not front_frames or not turret_frames:
                continue

            # Bierz tylko ostatnią klatkę z dekodowania (gdyby było kilka)
            front_frame = front_frames[-1]
            turret_frame = turret_frames[-1]

            # Konwersja -> np. co 3 klatkę wysyłamy
            # (albo w ogóle bez liczenia, bo i tak zredukowaliśmy fps do 10)
            img_front_b64 = convert_frame_to_jpeg_base64(front_frame)
            img_turret_b64 = convert_frame_to_jpeg_base64(turret_frame)

            # Wysyłamy asynchronicznie
            data_to_send = {
                "image_front": img_front_b64,
                "image_turret": img_turret_b64
            }
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    websocket.send(json.dumps(data_to_send)),
                    loop
                )

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
    
    time.sleep(0.5)


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
                    handle_turret_command("left")
                elif command == "turret_right":
                    print("Turret RIGHT – odebrano komendę turret_right (Orange Pi)")
                    handle_turret_command("right")
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

def handle_turret_command(direction):

    global local_settings
    step_time_turret = local_settings.get("step_time_turret", 500.0)  # w µs
    steps_turret = local_settings.get("steps_turret", 200)
    cmd = f"sudo python3 motor_control.py {direction} {step_time_turret} {steps_turret}"
    print(f"Wywołanie wieżyczki: {cmd}")
    os.system(cmd)

if __name__ == "__main__":
    asyncio.run(listen())
