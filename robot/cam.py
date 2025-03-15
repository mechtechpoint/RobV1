#!/usr/bin/env python3
import av
import pygame
import numpy as np

def main():
    container = av.open("/dev/video1", format="v4l2")

    pygame.init()
    screen_width, screen_height = 640, 480
    screen = pygame.display.set_mode((screen_width, screen_height))
    pygame.display.set_caption("Podgląd z kamery (bez OpenCV)")

    running = True
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

        # Obracamy surface o 90 stopni w lewo (jeśli potrzeba w prawo, użyj +90)
        # Proste podejście: spróbuj 90, -90, 180 aż obraz się wyświetli zgodnie
        surf = pygame.transform.rotate(surf, -90)

        # Skalujemy do rozmiarów okna, jeśli trzeba
        surf = pygame.transform.scale(surf, (screen_width, screen_height))

        screen.blit(surf, (0, 0))
        pygame.display.flip()

    pygame.quit()
    container.close()

if __name__ == "__main__":
    main()
