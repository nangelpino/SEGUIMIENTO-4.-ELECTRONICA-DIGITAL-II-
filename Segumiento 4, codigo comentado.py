from machine import Pin, I2C, PWM   # Importa clases para manejar pines digitales, comunicación I2C y señal PWM
import framebuf                     # Permite trabajar con buffers gráficos (sprites)
import ssd1306                      # Controlador para la pantalla OLED SSD1306
import utime                        # Manejo de tiempo (milisegundos, delays)
import random                       # Generación de valores aleatorios

# ---------------- CONFIGURACIÓN ----------------
PIN_SDA = 21                        # Pin de datos I2C
PIN_SCL = 22                        # Pin de reloj I2C
PIN_BTN_UP = 32                     # Pin botón arriba
PIN_BTN_DOWN = 33                   # Pin botón abajo
PIN_BTN_START = 25                  # Pin botón start
PIN_BUZZ = 26                       # Pin del buzzer

OLED_W, OLED_H = 128, 64            # Resolución de la pantalla OLED
FPS = 30                            # Frames por segundo
FRAME_MS = int(1000 / FPS)          # Tiempo por frame en milisegundos

PLAYER_W, PLAYER_H = 8, 8           # Tamaño del jugador
PLAYER_X = 10                       # Posición fija en X
OB_W, OB_H = 8, 10                  # Tamaño de obstáculos

MODES = ["CLÁSICO", "CONTRA-TIEMPO", "HARDCORE"]  # Lista de modos
CONTRA_SECONDS = 60                 # Duración modo contra-tiempo

# ---------------- HARDWARE ----------------
i2c = I2C(0, scl=Pin(PIN_SCL), sda=Pin(PIN_SDA), freq=400000)  # Inicializa bus I2C
oled = ssd1306.SSD1306_I2C(OLED_W, OLED_H, i2c, addr=0x3C)     # Inicializa pantalla OLED

# Parche OLED
if not hasattr(oled, "hline"):      # Verifica si existe función hline
    def hline(x, y, w, color):     # Define función línea horizontal
        for i in range(w):         # Recorre el ancho
            oled.pixel(x + i, y, color)  # Dibuja pixel a pixel
    oled.hline = hline             # Asigna función al objeto

if not hasattr(oled, "vline"):     # Verifica función línea vertical
    def vline(x, y, h, color):     # Define función
        for i in range(h):         # Recorre altura
            oled.pixel(x, y + i, color)  # Dibuja pixel
    oled.vline = vline             # Asigna

if not hasattr(oled, "blit"):      # Verifica función blit (sprites)
    def blit(fb, x0, y0):          # Define función blit
        try:
            w = fb.width           # Ancho del buffer
            h = fb.height          # Alto del buffer
        except AttributeError:
            w = 8                  # Valor por defecto
            h = 8
        for iy in range(h):        # Recorre filas
            for ix in range(w):    # Recorre columnas
                color = fb.pixel(ix, iy)  # Obtiene pixel
                if color:
                    oled.pixel(x0 + ix, y0 + iy, 1)  # Dibuja pixel
    oled.blit = blit               # Asigna función

# ---------------- BOTONES ----------------
btn_up = Pin(PIN_BTN_UP, Pin.IN, Pin.PULL_UP)       # Botón arriba con pull-up
btn_down = Pin(PIN_BTN_DOWN, Pin.IN, Pin.PULL_UP)   # Botón abajo
btn_start = Pin(PIN_BTN_START, Pin.IN, Pin.PULL_UP) # Botón start

# ---------------- BUZZER ----------------
buzzer_pwm = PWM(Pin(PIN_BUZZ))   # Inicializa PWM en buzzer
buzzer_pwm.duty(0)                # Lo apaga

def buzzer_tone(freq, dur_ms, duty=512):  # Función sonido temporal
    buzzer_pwm.freq(int(freq))            # Configura frecuencia
    buzzer_pwm.duty(int(duty))            # Configura intensidad
    utime.sleep_ms(dur_ms)                # Espera duración
    buzzer_pwm.duty(0)                    # Apaga

def buzzer_async(freq, duty=400):         # Sonido continuo
    buzzer_pwm.freq(int(freq))            # Frecuencia
    buzzer_pwm.duty(int(duty))            # Intensidad

def buzzer_stop():                        # Detiene buzzer
    buzzer_pwm.duty(0)

# ---------------- SPRITE ----------------
SPRITE = bytearray([                     # Define sprite en bits
    0b00111100,
    0b01111110,
    0b11111111,
    0b11011011,
    0b11111111,
    0b01111110,
    0b00111100,
    0b00011000
])
fb_player = framebuf.FrameBuffer(SPRITE, PLAYER_W, PLAYER_H, framebuf.MONO_HMSB)  # Convierte sprite

# ---------------- BOTÓN DEBOUNCE ----------------
class DebouncedButton:                  # Clase para eliminar rebotes
    def __init__(self, pin_obj, active_value=0, debounce_ms=40):
        self.pin = pin_obj              # Guarda pin
        self.active = active_value      # Valor activo (0)
        self.debounce_ms = debounce_ms  # Tiempo de debounce
        self._last_state = self.pin.value()  # Estado anterior
        self._last_time = utime.ticks_ms()   # Tiempo anterior
        self._pressed_flag = False      # Bandera de pulsación

    def update(self):
        v = self.pin.value()            # Lee estado actual
        now = utime.ticks_ms()          # Tiempo actual
        if v != self._last_state:       # Si cambia
            self._last_time = now       # Actualiza tiempo
            self._last_state = v        # Guarda estado
        else:
            if utime.ticks_diff(now, self._last_time) > self.debounce_ms:
                if v == self.active and not self._pressed_flag:
                    self._pressed_flag = True
                    return True         # Detecta pulsación válida
                if v != self.active and self._pressed_flag:
                    self._pressed_flag = False
        return False

btn_up_w = DebouncedButton(btn_up)        # Botón arriba con debounce
btn_down_w = DebouncedButton(btn_down)    # Botón abajo
btn_start_w = DebouncedButton(btn_start)  # Botón start

# ---------------- COLISION ----------------
def aabb(ax, ay, aw, ah, bx, by, bw, bh):  # Función de colisión tipo caja
    return not (ax+aw <= bx or bx+bw <= ax or ay+ah <= by or by+bh <= ay)

# ---------------- CLASES ----------------
class Player:
    def __init__(self, y):
        self.x = PLAYER_X            # Posición X fija
        self.y = y                   # Posición Y
        self.w = PLAYER_W            # Ancho
        self.h = PLAYER_H            # Alto

    def move_up(self):
        if self.y > 0:               # Verifica límite superior
            self.y -= 8              # Sube
            buzzer_tone(1500, 30, 400)  # Sonido

    def move_down(self):
        if self.y + self.h < OLED_H: # Verifica límite inferior
            self.y += 8              # Baja
            buzzer_tone(1400, 30, 400)

    def draw(self, d):
        d.blit(fb_player, int(self.x), int(self.y))  # Dibuja Sprite
class Obstacle:                                   # Clase que representa los obstáculos
    def __init__(self, x, y, w=OB_W, h=OB_H, speed=2):  # Constructor con posición, tamaño y velocidad
        self.x = x                                # Posición en X
        self.y = y                                # Posición en Y
        self.w = w                                # Ancho del obstáculo
        self.h = h                                # Alto del obstáculo
        self.speed = speed                        # Velocidad de movimiento

    def update(self):                             # Método para actualizar posición
        self.x -= self.speed                      # Mueve el obstáculo hacia la izquierda
        buzzer_async(900 + random.randint(-100, 100), 300)  # Genera sonido con frecuencia aleatoria

    def offscreen(self):                          # Verifica si salió de pantalla
        return (self.x + self.w) < 0              # Retorna True si ya no es visible

    def draw(self, d):                            # Método para dibujar el obstáculo
        for yy in range(self.h):                  # Recorre la altura del obstáculo
            d.hline(int(self.x), int(self.y)+yy, int(self.w), 1)  # Dibuja línea horizontal por cada fila

class Difficulty:                                 # Clase que controla la dificultad del juego
    def __init__(self, mode):                     # Constructor con modo de juego
        self.mode = mode                          # Guarda el modo seleccionado
        self.reset()                              # Inicializa valores según el modo

    def reset(self):                              # Configura valores iniciales
        if self.mode == 0:                        # Si modo es CLÁSICO
            self.spawn_ms = 1200                  # Tiempo entre aparición de obstáculos
            self.base_speed = 1.2                 # Velocidad base
            self.min_spawn = 700                  # Tiempo mínimo entre obstáculos
            self.step_time = 6000                 # Tiempo para aumentar dificultad
            self.speed_limit = 3.0                # Límite de velocidad
            self.label = "CLÁSICO"                # Nombre del modo
        elif self.mode == 1:                      # Si modo es CONTRA-TIEMPO
            self.spawn_ms = 800
            self.base_speed = 2.2
            self.min_spawn = 400
            self.step_time = 3000
            self.speed_limit = 3.5
            self.label = "CONTRA"
        else:                                     # Si modo es HARDCORE
            self.spawn_ms = 400
            self.base_speed = 4.0
            self.min_spawn = 150
            self.step_time = 1200
            self.speed_limit = 6.5
            self.label = "HARDCORE"
        self.last_tick = utime.ticks_ms()         # Guarda tiempo actual

    def escalate(self):                           # Método que aumenta la dificultad
        now = utime.ticks_ms()                    # Tiempo actual
        if utime.ticks_diff(now, self.last_tick) > self.step_time:  # Verifica si pasó el tiempo definido
            if self.spawn_ms > self.min_spawn:    # Si aún puede disminuir tiempo de aparición
                self.spawn_ms = max(self.min_spawn, self.spawn_ms - 30)  # Reduce tiempo entre obstáculos
            if self.base_speed < self.speed_limit:  # Si aún puede aumentar velocidad
                self.base_speed += 0.1            # Incrementa velocidad
            self.last_tick = now                  # Reinicia contador de tiempo

STATE_MENU = 0                                   # Estado del menú
STATE_GAME = 1                                   # Estado jugando
STATE_GAMEOVER = 2                               # Estado game over
STATE_PAUSE = 3                                  # Estado pausa

class Game:                                      # Clase principal del juego
    def __init__(self):                          # Constructor
        self.state = STATE_MENU                  # Estado inicial menú
        self.mode_idx = 0                        # Índice del modo seleccionado
        self.player = Player((OLED_H - PLAYER_H)//2)  # Inicializa jugador centrado
        self.obstacles = []                      # Lista de obstáculos
        self.last_spawn = utime.ticks_ms()       # Tiempo del último obstáculo creado
        self.difficulty = Difficulty(self.mode_idx)  # Configuración de dificultad
        self.score = 0                           # Puntaje inicial
        self.start_time = 0                      # Tiempo de inicio
        self.survival_time = 0                   # Tiempo sobrevivido
        self.obstacles_dodged = 0                # Obstáculos esquivados

    def start(self):                             # Método para iniciar juego
        self.state = STATE_GAME                  # Cambia estado a jugando
        self.player = Player((OLED_H - PLAYER_H)//2)  # Reinicia jugador
        self.obstacles = []                      # Limpia obstáculos
        self.score = 0                           # Reinicia puntaje
        self.last_spawn = utime.ticks_ms()       # Reinicia tiempo de spawn
        self.start_time = utime.ticks_ms()       # Marca inicio del juego
        self.obstacles_dodged = 0                # Reinicia contador
        self.difficulty = Difficulty(self.mode_idx)  # Reinicia dificultad
        buzzer_tone(1200, 150, 512)              # Sonido de inicio

    def game_over(self):                         # Método de fin de juego
        self.state = STATE_GAMEOVER              # Cambia estado
        buzzer_tone(300, 400, 700)               # Sonido grave
        buzzer_stop()                            # Apaga buzzer

    def spawn(self):                             # Genera nuevo obstáculo
        y = random.randint(0, OLED_H - OB_H)     # Posición aleatoria en Y
        x = OLED_W                               # Aparece en el borde derecho
        speed = int(self.difficulty.base_speed + random.random()*1.8)  # Velocidad variable
        self.obstacles.append(Obstacle(x, y, OB_W, OB_H, speed))  # Añade obstáculo a lista

    def update(self):                            # Lógica principal del juego
        if self.state != STATE_GAME:             # Si no está en juego
            return                              # No hace nada

        self.survival_time = (utime.ticks_ms() - self.start_time)//1000  # Calcula tiempo sobrevivido

        self.difficulty.escalate()               # Aumenta dificultad progresivamente

        now = utime.ticks_ms()                   # Tiempo actual
        if utime.ticks_diff(now, self.last_spawn) > self.difficulty.spawn_ms:  # Control de spawn
            self.spawn()                         # Crea obstáculo
            self.last_spawn = now                # Actualiza tiempo

        for ob in list(self.obstacles):          # Recorre copia de lista
            ob.update()                          # Actualiza posición
            if ob.offscreen():                   # Si salió de pantalla
                self.obstacles.remove(ob)        # Elimina obstáculo
                self.score += 5                  # Suma puntos
                self.obstacles_dodged += 1       # Incrementa contador

        for ob in self.obstacles:                # Recorre obstáculos
            if aabb(self.player.x, self.player.y, self.player.w, self.player.h,
                    ob.x, ob.y, ob.w, ob.h):     # Verifica colisión
                self.game_over()                 # Termina juego
                return                          # Sale del método

        if self.mode_idx == 1:                   # Si modo es contra-tiempo
            elapsed = (utime.ticks_ms() - self.start_time) // 1000  # Tiempo transcurrido
            if elapsed >= CONTRA_SECONDS:        # Si se acabó el tiempo
                self.game_over()                 # Termina juego

    def draw(self, d):                           # Método para dibujar en pantalla
        d.fill(0)                                # Limpia pantalla

        if self.state == STATE_MENU:             # Si está en menú
            d.text("DODGER", 36, 6, 1)           # Título
            d.text("MODO:", 6, 24, 1)            # Texto modo
            d.text(MODES[self.mode_idx], 46, 24, 1)  # Muestra modo actual
            d.text("START -> JUGAR", 18, 44, 1)  # Instrucción

        elif self.state == STATE_GAME:           # Si está jugando
            d.text("S:"+str(self.score), 0, 0, 1)  # Puntaje
            d.text("O:"+str(self.obstacles_dodged), 40, 0, 1)  # Obstáculos
            d.text("T:"+str(self.survival_time), 90, 0, 1)  # Tiempo
            d.hline(0, 10, OLED_W, 1)           # Línea separadora

            self.player.draw(d)                 # Dibuja jugador
            for ob in self.obstacles:           # Recorre obstáculos
                ob.draw(d)                      # Dibuja cada uno

        elif self.state == STATE_PAUSE:         # Si está en pausa
            d.text("PAUSA", 40, 20, 1)          # Texto pausa
            d.text("S:"+str(self.score), 30, 40, 1)  # Puntaje
            d.text("START=CONT", 10, 55, 1)     # Instrucción

        elif self.state == STATE_GAMEOVER:      # Si terminó el juego
            d.text("GAME OVER", 30, 10, 1)
            d.text("P:"+str(self.score), 30, 25, 1)
            d.text("T:"+str(self.survival_time), 30, 35, 1)
            d.text("O:"+str(self.obstacles_dodged), 30, 45, 1)
            d.text("START -> MENU", 5, 58, 1)

        d.show()                                # Actualiza pantalla

game = Game()                                   # Crea instancia del juego

try:
    while True:                                 # Bucle infinito principal
        if btn_up_w.update():                   # Si botón arriba presionado
            if game.state == STATE_MENU:
                game.mode_idx = (game.mode_idx - 1) % len(MODES)  # Cambia modo
                buzzer_tone(1100, 40, 400)      # Sonido
            elif game.state == STATE_GAME:
                game.player.move_up()           # Mueve jugador

        if btn_down_w.update():                 # Si botón abajo
            if game.state == STATE_MENU:
                game.mode_idx = (game.mode_idx + 1) % len(MODES)
                buzzer_tone(900, 40, 400)
            elif game.state == STATE_GAME:
                game.player.move_down()

        if btn_start_w.update():                # Si botón start
            if game.state == STATE_MENU:
                game.start()                   # Inicia juego
            elif game.state == STATE_GAME:
                game.state = STATE_PAUSE       # Pausa
            elif game.state == STATE_PAUSE:
                game.state = STATE_GAME        # Reanuda
            elif game.state == STATE_GAMEOVER:
                game.state = STATE_MENU        # Regresa al menú

        game.update()                          # Actualiza lógica del juego
        game.draw(oled)                        # Dibuja en pantalla
        utime.sleep_ms(FRAME_MS)               # Control de velocidad

except KeyboardInterrupt:                      # Si se detiene manualmente
    buzzer_stop()                             # Apaga buzzer
    oled.fill(0)                              # Limpia pantalla
    oled.text("Fin del juego", 24, 28, 1)     # Mensaje final
    oled.show()                               # Muestra en pantalla
