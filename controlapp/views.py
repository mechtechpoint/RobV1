# views.py

import os
import json
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(BASE_DIR, 'settings.json')

def index(request):
    return render(request, "controlapp/index.html")

def login_view(request):
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("control")
    return render(request, "controlapp/login.html")

@login_required
def logout_view(request):
    logout(request)
    return redirect("login")

@login_required
def control_view(request):
    return render(request, "controlapp/control.html")

@login_required
def settings_view(request):
    """
    Widok do wyświetlania i edycji ustawień (step_time_go, step_time_back, step_time_turn, itp.).
    """
    if request.method == 'POST':
        # 1) Pobierz wartości z formularza
        step_time_go = float(request.POST.get('step_time_go', '250'))
        step_time_back = float(request.POST.get('step_time_back', '250'))
        step_time_turn = float(request.POST.get('step_time_turn', '250'))
        engine_left_calib = float(request.POST.get('engine_left_calib', '1.0'))
        engine_right_calib = float(request.POST.get('engine_right_calib', '1.0'))
        step_time_turret = float(request.POST.get('step_time_turret', '500'))
        steps_turret = int(request.POST.get('steps_turret', '200'))
        step_time_turret2 = float(request.POST.get('step_time_turret2', '500'))
        steps_turret2 = int(request.POST.get('steps_turret2', '200')),
        turret_mark_x = int(request.POST.get('turret_mark_x', '160'))
        turret_mark_y = int(request.POST.get('turret_mark_y', '120'))

        # 2) Zaktualizuj plik settings.json na serwerze
        new_data = {
            "step_time_go": step_time_go,
            "step_time_back": step_time_back,
            "step_time_turn": step_time_turn,
            "engine_left_calib": engine_left_calib,
            "engine_right_calib": engine_right_calib,
            "step_time_turret": step_time_turret,
            "steps_turret": steps_turret,
            "step_time_turret2": step_time_turret2,
            "steps_turret2": steps_turret2,
            "turret_mark_x": turret_mark_x,
            "turret_mark_y": turret_mark_y
        }
        with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(new_data, f, ensure_ascii=False, indent=4)

        # 3) Wyślij event do wszystkich klientów WebSocket (np. do Orange Pi),
        #    żeby i oni zaktualizowali swoje pliki
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "motor_control",
            {
                "type": "settings_update",  # nazwa eventu -> method_name w Consumerze
                "settings_data": new_data
            }
        )

        return redirect("settings")  # Powrót do strony Settings (lub do "control", wg uznania)

    else:
        # Odczytaj aktualne wartości z pliku settings.json i wyświetl w formularzu
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                current_data = json.load(f)
        else:
            # Jeśli nie ma pliku, stwórz domyślne
            current_data = {
                "step_time_go": 250,
                "step_time_back": 250,
                "step_time_turn": 250,
                "engine_left_calib": 1.0,
                "engine_right_calib": 1.0,
                "step_time_turret": 500.0,
                "steps_turret": 200,
                "step_time_turret2": 500.0,
                "steps_turret2": 200,
                "turret_mark_x": 160,
                "turret_mark_y": 120
            }

        return render(request, "controlapp/settings.html", {"settings_data": current_data})
