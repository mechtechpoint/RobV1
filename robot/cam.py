#!/usr/bin/env python3
import av
import pygame
import numpy as np
import time

def main():
    # Otwieramy /dev/video1 z wymuszoną rozdzielczością 320x240 i 15 FPS
    container = av.open(
        "/dev/video1",
        format="v4l2",
        options={
            "video_size": "320x240",
            "framerate": "15",
        }
    )

    pygame.init()
    screen_width, screen_height = 640, 480
    screen = pygame.display.set_mode((screen_width, screen_height))
    pygame.display.set_caption("Podgląd z kamery (320x240 -> wyświetlane 640x480)")

    running = True

    # Iterujemy po klatkach
    for frame in container.decode(video=0):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break
        if not running:
            break

        # Konwersja do numpy array (RGB)
        img_rgb = frame.to_rgb().to_ndarray()

        # Tworzymy surface z obrazu
        surf = pygame.surfarray.make_surface(img_rgb)

        # (opcjonalnie) Obracamy surface o 90 stopni w lewo:
        surf = pygame.transform.rotate(surf, -90)

        # Skalujemy do okna 640x480 (jeśli chcesz, możesz zmienić)
        surf = pygame.transform.scale(surf, (screen_width, screen_height))

        # Wyświetlamy
        screen.blit(surf, (0, 0))
        pygame.display.flip()

        # Krótka pauza, by nie przekraczać ~15 FPS
        time.sleep(1/15)

    pygame.quit()
    container.close()

if __name__ == "__main__":
    main()
