#!/usr/bin/env python3

import sys
import wiringpi
import time

STEP_PIN = 9   # PD15
DIR_PIN = 10   # PD16

def main():
    # Inicjalizacja biblioteki wiringPi
    wiringpi.wiringPiSetup()
    
    # Ustaw piny jako wyjścia
    wiringpi.pinMode(STEP_PIN, 1)
    wiringpi.pinMode(DIR_PIN, 1)

    # Sprawdź, czy mamy przekazane argumenty:
    # 1) direction (left/right)
    # 2) step_time (w µs)
    # 3) steps (liczba kroków)
    if len(sys.argv) < 4:
        print("Użycie: motor_control.py [right|left] [step_time_us] [steps]")
        sys.exit(1)

    direction = sys.argv[1].lower()

    try:
        step_time_us = float(sys.argv[2])  # np. 500.0
        steps = int(sys.argv[3])
    except ValueError:
        print("Błędne parametry. Upewnij się, że step_time_us jest float, a steps to int.")
        sys.exit(1)

    # Ustaw kierunek na DIR_PIN
    # (zależnie od logiki Twojego sterownika: 0 = prawo, 1 = lewo lub odwrotnie)
    if direction == 'right':
        wiringpi.digitalWrite(DIR_PIN, 0)  # np. w prawo
    elif direction == 'left':
        wiringpi.digitalWrite(DIR_PIN, 1)  # np. w lewo
    else:
        print(f"Nieznany kierunek: {direction}. Oczekiwano: right lub left.")
        sys.exit(1)

    print(f"Rozpoczynam {steps} kroków w kierunku: {direction}. step_time_us={step_time_us}")

    # step_time_us trzeba zamienić na sekundy:
    step_time_s = step_time_us / 1_000_000.0  # np. 500.0 µs = 0.0005 s

    # Generujemy impulsy kroków (STEP_PIN)
    for i in range(steps):
        wiringpi.digitalWrite(STEP_PIN, 1)
        time.sleep(step_time_s)
        wiringpi.digitalWrite(STEP_PIN, 0)
        time.sleep(step_time_s)

    print(f"Zakończyłem {steps} kroków w kierunku: {direction}.")

    # Opcjonalnie przywrócenie pinów do stanu INPUT:
    # wiringpi.pinMode(STEP_PIN, 0)
    # wiringpi.pinMode(DIR_PIN, 0)

if __name__ == "__main__":
    main()
