from machine import Pin, I2C, PWM   # Importa Pin para manejar GPIO, I2C para la OLED y PWM para el buzzer
import framebuf                     # Librería para manejar sprites y gráficos en memoria
import ssd1306                      # Driver de la pantalla OLED SSD1306
import utime                        # Librería de tiempo en MicroPython
import random                       # Librería para números aleatorios

# ---------------- CONFIGURACIÓN ----------------
PIN_SDA = 21                        # Pin SDA del bus I2C
PIN_SCL = 22                        # Pin SCL del bus I2C
PIN_BTN_UP = 32                     # Pin del botón subir
PIN_BTN_DOWN = 33                   # Pin del botón bajar
PIN_BTN_START = 25                  # Pin del botón start
PIN_BUZZ = 26                       # Pin conectado al buzzer pasivo

OLED_W, OLED_H = 128, 64            # Resolución de la pantalla OLED
FPS = 30                            # Frames por segundo del juego
FRAME_MS = int(1000 / FPS)          # Tiempo de cada frame en milisegundos

PLAYER_W, PLAYER_H = 8, 8           # Tamaño del jugador
PLAYER_X = 10                       # Posición fija X del jugador
OB_W, OB_H = 8, 10                  # Tamaño de los obstáculos

MODES = ["CLÁSICO", "CONTRA-TIEMPO", "HARDCORE"]  # Lista de modos de juego
CONTRA_SECONDS = 60                 # Duración del modo contra-tiempo

# ---------------- HARDWARE ----------------
i2c = I2C(0, scl=Pin(PIN_SCL), sda=Pin(PIN_SDA), freq=400000)  # Inicializa bus I2C
oled = ssd1306.SSD1306_I2C(OLED_W, OLED_H, i2c, addr=0x3C)    # Inicializa pantalla OLED

# Parche OLED
if not hasattr(oled, "hline"):      # Verifica si existe función hline
    def hline(x, y, w, color):      # Función para dibujar línea horizontal
        for i in range(w):          # Recorre el ancho de la línea
            oled.pixel(x + i, y, color)  # Dibuja píxel por píxel
    oled.hline = hline              # Asigna función al objeto oled

if not hasattr(oled, "vline"):      # Verifica si existe función vertical
    def vline(x, y, h, color):      # Función para línea vertical
        for i in range(h):          # Recorre altura
            oled.pixel(x, y + i, color)  # Dibuja píxeles verticalmente
    oled.vline = vline              # Asigna función vertical

if not hasattr(oled, "blit"):       # Verifica si existe blit
    def blit(fb, x0, y0):           # Función para copiar sprites
        try:                        # Intenta obtener tamaño real del framebuffer
            w = fb.width
            h = fb.height
        except AttributeError:      # Si no existen atributos width/height
            w = 8
            h = 8
        for iy in range(h):         # Recorre filas
            for ix in range(w):     # Recorre columnas
                color = fb.pixel(ix, iy)  # Obtiene estado del píxel
                if color:           # Si el píxel está encendido
                    oled.pixel(x0 + ix, y0 + iy, 1)  # Dibuja píxel en OLED
    oled.blit = blit                # Agrega función blit

# ---------------- BOTONES ----------------
btn_up = Pin(PIN_BTN_UP, Pin.IN, Pin.PULL_UP)          # Configura botón UP
btn_down = Pin(PIN_BTN_DOWN, Pin.IN, Pin.PULL_UP)      # Configura botón DOWN
btn_start = Pin(PIN_BTN_START, Pin.IN, Pin.PULL_UP)    # Configura botón START

# ---------------- BUZZER ----------------
buzzer_pwm = PWM(Pin(PIN_BUZZ))   # Inicializa PWM en buzzer
buzzer_pwm.duty(0)                # Apaga buzzer inicialmente

def buzzer_tone(freq, dur_ms, duty=512):  # Función para sonido temporal
    buzzer_pwm.freq(int(freq))            # Configura frecuencia
    buzzer_pwm.duty(int(duty))            # Activa PWM
    utime.sleep_ms(dur_ms)                # Espera duración del sonido
    buzzer_pwm.duty(0)                    # Apaga buzzer

def buzzer_async(freq, duty=400):         # Sonido continuo
    buzzer_pwm.freq(int(freq))            # Cambia frecuencia
    buzzer_pwm.duty(int(duty))            # Activa PWM

def buzzer_stop():
    buzzer_pwm.duty(0)                    # Apaga buzzer

# ---------------- SPRITE ----------------
SPRITE = bytearray([              # Sprite del jugador en binario
    0b00111100,
    0b01111110,
    0b11111111,
    0b11011011,
    0b11111111,
    0b01111110,
    0b00111100,
    0b00011000
])

fb_player = framebuf.FrameBuffer( # Convierte sprite en framebuffer
    SPRITE,
    PLAYER_W,
    PLAYER_H,
    framebuf.MONO_HMSB
)

# ---------------- BOTÓN DEBOUNCE ----------------
class DebouncedButton:            # Clase anti-rebote de botones

    def __init__(self, pin_obj, active_value=0, debounce_ms=40):
        self.pin = pin_obj                # Guarda pin
        self.active = active_value        # Valor activo
        self.debounce_ms = debounce_ms    # Tiempo anti-rebote
        self._last_state = self.pin.value()  # Último estado leído
        self._last_time = utime.ticks_ms()   # Último tiempo leído
        self._pressed_flag = False           # Estado de pulsación

    def update(self):
        v = self.pin.value()              # Lee estado actual
        now = utime.ticks_ms()            # Tiempo actual

        if v != self._last_state:         # Si cambió el estado
            self._last_time = now         # Reinicia temporizador
            self._last_state = v          # Actualiza estado

        else:
            if utime.ticks_diff(now, self._last_time) > self.debounce_ms:
                if v == self.active and not self._pressed_flag:
                    self._pressed_flag = True
                    return True           # Detecta pulsación válida

                if v != self.active and self._pressed_flag:
                    self._pressed_flag = False  # Libera botón

        return False                      # No hubo pulsación válida

btn_up_w = DebouncedButton(btn_up)        # Botón UP con debounce
btn_down_w = DebouncedButton(btn_down)    # Botón DOWN con debounce
btn_start_w = DebouncedButton(btn_start)  # Botón START con debounce