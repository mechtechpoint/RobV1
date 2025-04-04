import wiringpi
import time

PIN = 16

def main():
    # Inicjalizacja biblioteki wiringPi
    wiringpi.wiringPiSetup()
    
    # Ustaw pin jako wyjście
    wiringpi.pinMode(PIN, 1)
    
    # Włącz pin na 2 sekundy
    print("Włączam pin 16 na 2 sekundy...")
    wiringpi.digitalWrite(PIN, 0)
    time.sleep(0.1)
    
    # Wyłącz pin
    wiringpi.digitalWrite(PIN, 1)
    print("Pin 16 został wyłączony.")

if __name__ == "__main__":
    main()