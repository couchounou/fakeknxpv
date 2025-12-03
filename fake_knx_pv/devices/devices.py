import threading
import time


class volet:
    def __init__(self):
        self.position = 0  # 0 = fermé, 100 = ouvert
        self._en_mouvement = False
        self._thread = None

    def _move(self, target):
        self._en_mouvement = True
        start = self.position
        delta = target - start
        duration = 20.0 * abs(delta) / 100  # proportionnel à la distance
        t0 = time.time()
        while self._en_mouvement and self.position != target:
            elapsed = time.time() - t0
            progress = min(1, elapsed / duration)
            self.position = int(start + delta * progress)
            time.sleep(0.1)
        self.position = target
        self._en_mouvement = False

    def monter(self):
        self._start_thread(100)

    def descendre(self):
        self._start_thread(0)

    def stop(self):
        self._en_mouvement = False
        if self._thread and self._thread.is_alive():
            self._thread.join()

    def set_position(self, x):
        self._start_thread(max(0, min(100, int(x))))

    def _start_thread(self, target):
        self.stop()
        self._thread = threading.Thread(target=self._move, args=(target,))
        self._thread.start()

    def get_position(self):
        return self.position