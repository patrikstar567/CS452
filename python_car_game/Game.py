import pygame, sys, time, random, datetime
from pygame.locals import *
from database import (
    get_or_create_player,
    save_score,
    get_player_stats,
    player_owns_skin,
    unlock_skin,
)

pygame.init()

# ---------------- SETTINGS ----------------
FPS = 60
FramePerSec = pygame.time.Clock()
sprite_sheet_path = "Porcupine - sprite sheet.png"  # default skin
boss_mode = False  

# Colors
WHITE  = (255, 255, 255)
BLACK  = (0, 0, 0)
RED    = (255,   0,   0)
GREEN  = (0,   255,   0)
BLUE   = (0,     0, 255)
YELLOW = (255, 255,   0)

# Screen setup
SCREEN_WIDTH  = 600
SCREEN_HEIGHT = 400
DEBUG_HITBOX  = False

font_large = pygame.font.SysFont("Verdana", 60)
font_med   = pygame.font.SysFont("Verdana", 30)
font_small = pygame.font.SysFont("Verdana", 20)

DISPLAYSURF = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Porcupine Infinite Road")

# Load background
background = pygame.image.load("scrol road.png").convert()
BG_HEIGHT   = background.get_height()
camera_y    = BG_HEIGHT - SCREEN_HEIGHT
last_camera_y = camera_y

# ---------------- ENEMY TYPES ----------------
ENEMY_TYPES = [
    {"name": "CompactCar", "image": "Enemy.png",       "speed_range": (3, 4)},
    {"name": "Sedan",      "image": "Enemy.png",       "speed_range": (4, 5)},
    {"name": "Truck",      "image": "Enemy.png",       "speed_range": (2, 3)},
    {"name": "Police",     "image": "POLICE_LEFT.png", "speed_range": (8, 12)},
    {"name": "Taxi",       "image": "Enemy.png",       "speed_range": (4, 6)},
]

# Global projectile group
projectiles = pygame.sprite.Group()

# ---------------- ENEMY ----------------
class Enemy(pygame.sprite.Sprite):
    def __init__(self, lane_y, direction, enemy_type):
        super().__init__()
        self.image = pygame.image.load(enemy_type["image"]).convert_alpha()
        if direction == "left":
            self.image = pygame.transform.flip(self.image, True, False)

        self.rect = self.image.get_rect()
        global boss_mode

        # Hitbox
        self.hitbox = self.rect.copy()
        w, h = self.rect.size
        self.hitbox.width  = int(w * 0.7)
        self.hitbox.height = int(h * 0.6)
        self.hitbox.center = self.rect.center

        self.lane_y    = lane_y
        self.direction = direction
        self.speed     = random.randint(*enemy_type["speed_range"])
        self.world_y   = lane_y

        if direction == "right":
            self.world_x = random.randint(-SCREEN_WIDTH, SCREEN_WIDTH)
        else:
            self.world_x = random.randint(0, SCREEN_WIDTH * 2)

    def update(self):
        if self.direction == "right":
            self.world_x += self.speed
            if self.world_x > SCREEN_WIDTH + self.rect.width:
                if boss_mode:
                    self.kill()
                else: 
                    self.world_x = -self.rect.width
        else:
            self.world_x -= self.speed
            if self.world_x < -self.rect.width:
                if boss_mode:
                    self.kill()
                else:
                    self.world_x = SCREEN_WIDTH + self.rect.width

    def draw(self, surface, camera_y):
        screen_y = (self.world_y - camera_y) % BG_HEIGHT
        if -self.rect.height < screen_y < SCREEN_HEIGHT:
            surface.blit(self.image, (self.world_x, screen_y))
            self.hitbox.center = (
                self.world_x + self.rect.width // 2,
                screen_y + self.rect.height // 2,
            )
            if DEBUG_HITBOX:
                pygame.draw.rect(surface, RED, self.hitbox, 1)


# ---------------- Boss ----------------
class Boss(pygame.sprite.Sprite):
    def __init__(self, lane_y):
        super().__init__()

        self.sheet = pygame.image.load("idle_32x32_4rows.png").convert_alpha()

        self.frame_width  = 32
        self.frame_height = 32

        sheet_w, sheet_h = self.sheet.get_size()
        self.num_frames = sheet_h // self.frame_height

        self.frames = []
        for i in range(self.num_frames):
            frame = pygame.Surface((self.frame_width, self.frame_height), pygame.SRCALPHA)
            frame.blit(
                self.sheet,
                (0, 0),
                (0, i * self.frame_height, self.frame_width, self.frame_height),
            )
            frame = pygame.transform.scale(frame, (96, 96))
            self.frames.append(frame)

        self.current_frame   = 0
        self.animation_speed = FPS / self.num_frames
        self.frame_counter   = 0

        self.image = self.frames[0]
        self.rect  = self.image.get_rect()

        # World position
        self.world_x = SCREEN_WIDTH // 2 - self.rect.width // 2
        self.world_y = lane_y

        # Movement
        self.speed_x = 3
        self.speed_y = 2

        # Shooting (effectively disabled)
        self.shoot_cooldown = 60
        self.shoot_timer = 0

        # HP / damage phase
        self.max_hp = 5
        self.hp = self.max_hp

        self.is_vulnerable = False
        self.phase_timer   = 0
        self.vuln_timer    = 0
        self.took_hit_this_phase = False

        # flashing
        self.flash_timer      = 0
        self.flash_on         = False
        self.after_hit_timer  = 0

        # Hitbox
        self.hitbox = self.rect.copy()
        w, h = self.rect.size
        self.hitbox.width  = int(w * 0.7)
        self.hitbox.height = int(h * 0.6)
        self.hitbox.center = self.rect.center

    def update(self):
        global camera_y

        # Animation
        self.frame_counter += 1
        if self.frame_counter >= self.animation_speed:
            self.frame_counter = 0
            self.current_frame = (self.current_frame + 1) % self.num_frames
            self.image = self.frames[self.current_frame]

        # Movement in world space
        self.world_x += self.speed_x
        self.world_y += self.speed_y

        # Horizontal bounce
        if self.world_x < 0 or self.world_x + self.rect.width > SCREEN_WIDTH:
            self.speed_x *= -1

        # Vertical bounce
        screen_y = (self.world_y - camera_y) % BG_HEIGHT
        TOP_LIMIT    = 40
        BOTTOM_LIMIT = SCREEN_HEIGHT - self.rect.height - 40
        if screen_y < TOP_LIMIT or screen_y > BOTTOM_LIMIT:
            self.speed_y *= -1

        # Shooting (disabled by huge cooldown, but we'll keep logic)
        self.shoot_timer += 1
        if self.shoot_timer >= self.shoot_cooldown:
            self.shoot_timer = 0
            self.shoot()

        # Damage-phase timers
        if self.is_vulnerable:
            self.vuln_timer += 1

            if not self.took_hit_this_phase:
                # flashing while vulnerable & not yet hit
                self.flash_timer += 1
                if self.flash_timer >= 5:
                    self.flash_timer = 0
                    self.flash_on = not self.flash_on
            else:
                # after we've been hit this phase, keep flashing for 1 second
                self.after_hit_timer += 1
                if self.after_hit_timer >= FPS:
                    self.flash_on = False

            # End of 5-second vulnerable window
            if self.vuln_timer >= 5 * FPS:
                self.is_vulnerable = False
                self.vuln_timer = 0
                self.phase_timer = 0
                self.took_hit_this_phase = False
                self.flash_on = False
                self.flash_timer = 0
                self.after_hit_timer = 0
        else:
            # wait 10 seconds between damage phases
            self.phase_timer += 1
            if self.phase_timer >= 10 * FPS:
                self.is_vulnerable = True
                self.vuln_timer = 0
                self.phase_timer = 0
                self.took_hit_this_phase = False
                self.flash_timer = 0
                self.flash_on = True
                self.after_hit_timer = 0

    def take_hit(self):
        # returns True if boss dies
        if not self.is_vulnerable or self.took_hit_this_phase:
            return False
        self.hp -= 1
        self.took_hit_this_phase = True
        self.after_hit_timer = 0
        return self.hp <= 0

    def shoot(self):
        global projectiles
        cx = self.world_x + self.rect.width  // 2
        cy = self.world_y + self.rect.height // 2
        speed = 6

        directions = [
            (0, -speed),
            (0,  speed),
            (-speed, 0),
            ( speed, 0),
        ]

        for vx, vy in directions:
            projectiles.add(Projectile(cx, cy, vx, vy))

    def draw(self, surface, camera_y):
        screen_y = (self.world_y - camera_y) % BG_HEIGHT
        if -self.rect.height < screen_y < SCREEN_HEIGHT:
            img = self.frames[self.current_frame]
            if self.is_vulnerable and self.flash_on:
                img = img.copy()
                img.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGBA_ADD)

            surface.blit(img, (self.world_x, screen_y))

            self.hitbox.center = (
                self.world_x + self.rect.width // 2,
                screen_y + self.rect.height // 2,
            )
            if DEBUG_HITBOX:
                pygame.draw.rect(surface, RED, self.hitbox, 1)


# ---------------- PROJECTILE ----------------
class Projectile(pygame.sprite.Sprite):
    def __init__(self, world_x, world_y, vx, vy):
        super().__init__()
        self.image = pygame.Surface((16, 16), pygame.SRCALPHA)
        pygame.draw.circle(self.image, RED, (8, 8), 8)

        self.rect = self.image.get_rect()
        self.world_x = world_x
        self.world_y = world_y
        self.vx = vx
        self.vy = vy

        self.hitbox = self.rect.copy()
        self.hitbox.width  = int(self.rect.width * 0.8)
        self.hitbox.height = int(self.rect.height * 0.8)
        self.hitbox.center = self.rect.center

    def update(self):
        global camera_y

        # move in world space
        self.world_x += self.vx
        self.world_y += self.vy

        # compute screen position
        screen_y = (self.world_y - camera_y) % BG_HEIGHT
        self.rect.center = (int(self.world_x), int(screen_y))
        self.hitbox.center = self.rect.center

        # kill if off-screen
        if (self.rect.right < 0 or self.rect.left > SCREEN_WIDTH or
            self.rect.bottom < 0 or self.rect.top > SCREEN_HEIGHT):
            self.kill()

    def draw(self, surface, camera_y):
        screen_y = (self.world_y - camera_y) % BG_HEIGHT
        surface.blit(self.image, (self.world_x - self.rect.width // 2,
                                  screen_y   - self.rect.height // 2))
        self.rect.center = (int(self.world_x), int(screen_y))
        self.hitbox.center = self.rect.center
        if DEBUG_HITBOX:
            pygame.draw.rect(surface, YELLOW, self.hitbox, 1)


# ---------------- COIN OBJECT ----------------
class Object(pygame.sprite.Sprite):
    def __init__(self, lane_y):
        super().__init__()

        # Horizontal coin sprite sheet
        self.sheet = pygame.image.load("coin1_16x16.png").convert_alpha()
        self.frame_width  = 16
        self.frame_height = 16
        sheet_width, sheet_height = self.sheet.get_size()

        self.num_frames = sheet_width // self.frame_width

        self.frames = []
        for i in range(self.num_frames):
            frame = pygame.Surface((self.frame_width, self.frame_height), pygame.SRCALPHA)
            frame.blit(
                self.sheet,
                (0, 0),
                (i * self.frame_width, 0, self.frame_width, self.frame_height),
            )
            frame = pygame.transform.scale(frame, (32, 32))
            self.frames.append(frame)

        self.current_frame   = 0
        self.animation_speed = FPS / self.num_frames
        self.frame_counter   = 0

        self.image  = self.frames[0]
        self.rect   = self.image.get_rect()
        self.hitbox = self.rect.copy()
        w, h = self.rect.size
        self.hitbox.width  = int(w * 0.7)
        self.hitbox.height = int(h * 0.6)
        self.hitbox.center = self.rect.center

        self.lane_y  = lane_y
        self.world_y = lane_y
        self.world_x = random.randint(50, SCREEN_WIDTH - 50)

    def update(self):
        self.frame_counter += 1
        if self.frame_counter >= self.animation_speed:
            self.frame_counter = 0
            self.current_frame = (self.current_frame + 1) % self.num_frames
            self.image = self.frames[self.current_frame]

    def draw(self, surface, camera_y):
        screen_y = (self.world_y - camera_y) % BG_HEIGHT
        if -self.rect.height < screen_y < SCREEN_HEIGHT:
            surface.blit(self.image, (self.world_x, screen_y))
            self.hitbox.center = (
                self.world_x + self.rect.width // 2,
                screen_y + self.rect.height // 2,
            )
            if DEBUG_HITBOX:
                pygame.draw.rect(surface, RED, self.hitbox, 1)


# ---------------- PLAYER ----------------
class Player(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__()
        global sprite_sheet_path

        self.sheet = pygame.image.load(sprite_sheet_path).convert_alpha()

        # These sizes work with your current sheets
        self.frame_width  = 32
        self.frame_height = 32

        sheet_width, sheet_height = self.sheet.get_size()
        self.cols = sheet_width // self.frame_width
        self.rows = sheet_height // self.frame_height

        self.animations = []
        for col in range(self.cols):
            column_frames = []
            for row in range(self.rows):
                x = col * self.frame_width
                y = row * self.frame_height
                frame = pygame.Surface((self.frame_width, self.frame_height), pygame.SRCALPHA)
                frame.blit(self.sheet, (0, 0), (x, y, self.frame_width, self.frame_height))
                frame = pygame.transform.scale(frame, (64, 64))
                column_frames.append(frame)
            self.animations.append(column_frames)

        self.direction       = "up"
        self.current_frame   = 0
        self.animation_speed = 0.2
        self.image = self.animations[self.get_col()][int(self.current_frame)]

        self.rect = self.image.get_rect(center=(SCREEN_WIDTH // 2, int(SCREEN_HEIGHT * 0.75)))

        self.hitbox = self.rect.copy()
        self.hitbox.width  = int(self.rect.width * 0.45)
        self.hitbox.height = int(self.rect.height * 0.45)
        self.hitbox.center = self.rect.center

        self.move_speed = 5

    def get_col(self):
        direction_map = {"down": 1, "left": 3, "right": 0, "up": 2}
        return direction_map[self.direction]

    def move(self):
        global camera_y
        pressed = pygame.key.get_pressed()
        moved = False

        if not boss_mode:
            if pressed[K_w]:
                camera_y -= self.move_speed
                self.direction = "up"
                moved = True

            if pressed[K_s]:
                camera_y += self.move_speed
                self.direction = "down"
                moved = True
        else:
            if pressed[K_w] and self.rect.top > 0:
                self.rect.move_ip(0, -self.move_speed)
                self.direction = "up"
                moved = True

            if pressed[K_s] and self.rect.bottom < SCREEN_HEIGHT:
                self.rect.move_ip(0, self.move_speed)
                self.direction = "down"
                moved = True

        if pressed[K_a] and self.rect.left > 0:
            self.rect.move_ip(-self.move_speed, 0)
            self.direction = "left"
            moved = True

        if pressed[K_d] and self.rect.right < SCREEN_WIDTH:
            self.rect.move_ip(self.move_speed, 0)
            self.direction = "right"
            moved = True

        if not boss_mode:
            if camera_y < 0:
                camera_y += BG_HEIGHT
            elif camera_y > BG_HEIGHT:
                camera_y -= BG_HEIGHT

        if moved:
            self.current_frame += self.animation_speed
            if self.current_frame >= len(self.animations[self.get_col()]):
                self.current_frame = 0
        else:
            self.current_frame = 0

        self.image = self.animations[self.get_col()][int(self.current_frame)]
        self.hitbox.center = self.rect.center

    def draw(self, surface):
        surface.blit(self.image, self.rect)
        if DEBUG_HITBOX:
            pygame.draw.rect(surface, BLUE, self.hitbox, 1)


# ---------------- HELPERS ----------------
def build_enemies():
    enemies = pygame.sprite.Group()
    lane_spacing = 120
    num_lanes = int(BG_HEIGHT / lane_spacing)
    for i in range(num_lanes):
        lane_y    = BG_HEIGHT - 200 - (i * lane_spacing)
        direction = "right" if i % 2 == 0 else "left"
        enemy_type = random.choice(ENEMY_TYPES)
        enemies.add(Enemy(lane_y, direction, enemy_type))
    return enemies

def build_objects():
    objects = pygame.sprite.Group()
    lane_spacing = 800
    num_lanes = int(BG_HEIGHT / lane_spacing)
    for i in range(num_lanes):
        lane_y = BG_HEIGHT - 200 - (i * lane_spacing)
        objects.add(Object(lane_y))
    return objects

def build_boss():
    boss_group = pygame.sprite.Group()
    lane_y = BG_HEIGHT - 200
    boss_sprite = Boss(lane_y)
    boss_group.add(boss_sprite)
    return boss_group

def draw_text_center(text, font, color, y_offset=0):
    label = font.render(text, True, color)
    rect  = label.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + y_offset))
    DISPLAYSURF.blit(label, rect)

def load_preview_frame(path, frame_w=32, frame_h=32, scale=64):
    sheet = pygame.image.load(path).convert_alpha()
    frame = pygame.Surface((frame_w, frame_h), pygame.SRCALPHA)
    frame.blit(sheet, (0, 0), (0, 0, frame_w, frame_h))
    frame = pygame.transform.scale(frame, (scale, scale))
    return frame


# ---------------- GAME SCREENS ----------------
def menu_screen(player_id, username):
    while True:
        DISPLAYSURF.fill(WHITE)
        stats = get_player_stats(player_id)

        draw_text_center(f"Welcome, {username}!",  font_med,   BLACK, -120)
        draw_text_center(f"Games Played: {stats['games_played']}", font_small, BLACK, -60)
        draw_text_center(f"High Score: {stats['high_score']}",     font_small, BLACK, -30)
        draw_text_center(f"Average Score: {stats['avg_score']:.1f}", font_small, BLACK, 0)
        draw_text_center(f"Coins: {stats['coins']}",               font_small, BLACK, 30)

        draw_text_center("Press S for Shop",   font_med,   BLUE,  70)
        draw_text_center("Press SPACE to Play",font_med,   GREEN, 110)
        draw_text_center("Press Q to Quit",    font_small, RED,   150)

        pygame.display.update()

        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit()
                sys.exit()
            if event.type == KEYDOWN:
                if event.key == K_SPACE:
                    return
                if event.key == K_q:
                    pygame.quit()
                    sys.exit()
                if event.key == K_s:
                    shop_screen(player_id, username)

def game_over_screen(player_id, username, score):
    high_score = get_player_stats(player_id)['high_score']
    while True:
        DISPLAYSURF.fill(RED)
        draw_text_center("GAME OVER",             font_large, WHITE, -80)
        draw_text_center(f"Your Score: {score}",  font_med,   WHITE, 0)
        draw_text_center(f"All-Time High: {high_score}", font_small, YELLOW, 40)
        draw_text_center("Press R to Return to Menu", font_small, WHITE, 100)
        draw_text_center("Press Q to Quit",           font_small, WHITE, 130)
        pygame.display.update()

        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit()
                sys.exit()
            if event.type == KEYDOWN:
                if event.key == K_r:
                    return
                if event.key == K_q:
                    pygame.quit()
                    sys.exit()


# ---------------- SHOP ----------------
def shop_screen(player_id, username):
    global sprite_sheet_path

    porcu_img   = load_preview_frame("Porcupine - sprite sheet.png")
    peacock_img = load_preview_frame("Peacock-walk-Sheet.png")
    robot_img   = load_preview_frame("robotgood.png")
    plane_img   = load_preview_frame("plane_4x4_single.png")

    while True:
        DISPLAYSURF.fill(WHITE)

        stats        = get_player_stats(player_id)
        coins_avail  = stats["coins"]

        owns_porcupine = True
        owns_peacock   = player_owns_skin(player_id, "peacock")
        owns_robot     = player_owns_skin(player_id, "robot")
        owns_plane     = player_owns_skin(player_id, "plane")

        title = font_med.render("SHOP", True, BLACK)
        DISPLAYSURF.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 20))

        coins_label = font_small.render(f"Coins: {coins_avail}", True, BLACK)
        DISPLAYSURF.blit(coins_label, (SCREEN_WIDTH - coins_label.get_width() - 20, 20))

        ROW_START_Y   = 70
        ROW_SPACING   = 70
        IMG_X         = 40
        TEXT_OFFSET_X = 120

        def draw_skin_row(y, img, text, owned):
            DISPLAYSURF.blit(img, (IMG_X, y))
            color = GREEN if owned else BLACK
            label = font_small.render(text, True, color)
            DISPLAYSURF.blit(label, (TEXT_OFFSET_X, y + 10))
            if owned:
                check = font_small.render("✓", True, GREEN)
                DISPLAYSURF.blit(check, (IMG_X + img.get_width() + 8, y))

        y = ROW_START_Y
        porcu_text = "Default Porcupine — Press 0 to select"
        draw_skin_row(y, porcu_img, porcu_text, owns_porcupine)

        y = ROW_START_Y + ROW_SPACING
        if owns_peacock:
            peacock_text = "Peacock — Press 1 to select"
        else:
            peacock_text = "40 Coins Peacock — Press 1 to purchase"
        draw_skin_row(y, peacock_img, peacock_text, owns_peacock)

        y = ROW_START_Y + ROW_SPACING * 2
        if owns_robot:
            robot_text = "Robot — Press 2 to select"
        else:
            robot_text = "80 Coins Robot — Press 2 to purchase"
        draw_skin_row(y, robot_img, robot_text, owns_robot)

        y = ROW_START_Y + ROW_SPACING * 3
        if owns_plane:
            plane_text = "Plane — Press 3 to select"
        else:
            plane_text = "120 Coins Plane — Press 3 to purchase"
        draw_skin_row(y, plane_img, plane_text, owns_plane)

        draw_text_center("Press R to Return", font_small, RED, 150)

        pygame.display.update()

        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit()
                sys.exit()

            if event.type == KEYDOWN:
                if event.key == K_r:
                    return

                if event.key == K_0:
                    sprite_sheet_path = "Porcupine - sprite sheet.png"

                if event.key == K_1:
                    if owns_peacock:
                        sprite_sheet_path = "Peacock-walk-Sheet.png"
                    elif coins_avail >= 40:
                        unlock_skin(player_id, "peacock")
                        sprite_sheet_path = "Peacock-walk-Sheet.png"

                if event.key == K_2:
                    if owns_robot:
                        sprite_sheet_path = "robotgood.png"
                    elif coins_avail >= 80:
                        unlock_skin(player_id, "robot")
                        sprite_sheet_path = "robotgood.png"

                if event.key == K_3:
                    if owns_plane:
                        sprite_sheet_path = "plane_4x4_single.png"
                    elif coins_avail >= 120:
                        unlock_skin(player_id, "plane")
                        sprite_sheet_path = "plane_4x4_single.png"


# ---------------- MAIN GAME LOGIC ----------------
def play_game(player_id, username):
    global camera_y, last_camera_y
    global boss_mode
    global projectiles

    COINS       = 0
    DISTANCE    = 0
    DIST_SCORE  = 0
    BONUS_SCORE = 0
    SCORE       = 0
    boss_mode = False
    boss_defeated = False

    camera_y      = BG_HEIGHT - SCREEN_HEIGHT
    last_camera_y = camera_y

    enemies = build_enemies()
    objects = build_objects()
    boss    = build_boss()
    P1      = Player()
    projectiles.empty()

    while True:
        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit()
                sys.exit()

        P1.move()
        enemies.update()
        objects.update()
        if boss_mode:
            boss.update()
            projectiles.update()

        # distance / score only when not in boss mode
        if camera_y < last_camera_y and not boss_mode:
            DISTANCE += (last_camera_y - camera_y)
            DIST_SCORE = int(DISTANCE / 50)
        SCORE = DIST_SCORE + BONUS_SCORE

        # Start boss once, when score high enough
        if SCORE >= 200 and (not boss_mode) and (not boss_defeated):
            boss_mode = True
            for bos in boss:
                bos.world_y = camera_y + 50

        last_camera_y = camera_y

        # Draw background (tiled)
        scroll_y = camera_y % BG_HEIGHT
        DISPLAYSURF.blit(background, (0, -scroll_y))
        DISPLAYSURF.blit(background, (0, BG_HEIGHT - scroll_y))

        # Draw everything
        for enemy in enemies:
            enemy.draw(DISPLAYSURF, camera_y)
        for obj in objects:
            obj.draw(DISPLAYSURF, camera_y)
        if boss_mode:
            for bos in boss:
                bos.draw(DISPLAYSURF, camera_y)
            for proj in projectiles:
                proj.draw(DISPLAYSURF, camera_y)
        P1.draw(DISPLAYSURF)

        # HUD
        score_label = font_small.render(f"Score: {SCORE}", True, BLACK)
        coin_label  = font_small.render(f"Coins: {COINS}", True, BLACK)
        DISPLAYSURF.blit(score_label, (10, 10))
        DISPLAYSURF.blit(coin_label,  (10, 40))

        # Collisions with cars → game over
        for enemy in enemies:
            if P1.hitbox.colliderect(enemy.hitbox):
                pygame.mixer.Sound('crash.wav').play()
                save_score(player_id, SCORE, DISTANCE, COINS)
                game_over_screen(player_id, username, SCORE)
                return

        # Collisions with boss
        if boss_mode:
            for bos in list(boss):
                if P1.hitbox.colliderect(bos.hitbox):
                    if bos.is_vulnerable:
                        # boss has collision: we push the player out instead of dying
                        dx = P1.hitbox.centerx - bos.hitbox.centerx
                        dy = P1.hitbox.centery - bos.hitbox.centery
                        if abs(dx) > abs(dy):
                            if dx > 0:
                                P1.rect.left = bos.hitbox.right
                            else:
                                P1.rect.right = bos.hitbox.left
                        else:
                            if dy > 0:
                                P1.rect.top = bos.hitbox.bottom
                            else:
                                P1.rect.bottom = bos.hitbox.top
                        P1.hitbox.center = P1.rect.center

                        # Only first hit per phase does damage
                        if not bos.took_hit_this_phase:
                            boss_dead = bos.take_hit()
                            if boss_dead:
                                boss_mode = False
                                boss_defeated = True
                                projectiles.empty()
                                bos.kill()
                                # >>> REBUILD CARS + COINS AFTER BOSS <<<
                                enemies = build_enemies()
                                objects = build_objects()
                    else:
                        # boss not vulnerable → player dies
                        pygame.mixer.Sound('crash.wav').play()
                        save_score(player_id, SCORE, DISTANCE, COINS)
                        game_over_screen(player_id, username, SCORE)
                        return

        # Collisions with boss projectiles → game over
        if boss_mode:
            for proj in list(projectiles):
                if P1.hitbox.colliderect(proj.hitbox):
                    pygame.mixer.Sound('crash.wav').play()
                    save_score(player_id, SCORE, DISTANCE, COINS)
                    game_over_screen(player_id, username, SCORE)
                    return

        # Collisions with coins
        for obj in list(objects):
            if P1.hitbox.colliderect(obj.hitbox):
                if not boss_mode:
                    COINS += 1
                objects.remove(obj)

        # Random extra coins
        if len(objects) < 10 and random.random() < 0.02:
            lane_y = random.randint(0, BG_HEIGHT)
            objects.add(Object(lane_y))

        pygame.display.update()
        FramePerSec.tick(FPS)


# ---------------- LOGIN ----------------
def login_screen():
    username = ""
    entering = True
    while entering:
        DISPLAYSURF.fill(WHITE)
        draw_text_center("Enter Your Name:", font_med, BLACK, -40)
        draw_text_center(username + "_",     font_large, GREEN, 20)
        draw_text_center("Press ENTER to continue", font_small, BLACK, 100)
        pygame.display.update()

        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit()
                sys.exit()
            if event.type == KEYDOWN:
                if event.key == K_RETURN and username.strip():
                    entering = False
                elif event.key == K_BACKSPACE:
                    username = username[:-1]
                elif len(username) < 12 and event.unicode.isprintable():
                    username += event.unicode

    return username.strip()


# ---------------- MAIN LOOP ----------------
def main():
    username  = login_screen()
    player_id = get_or_create_player(username)

    while True:
        menu_screen(player_id, username)
        play_game(player_id, username)

if __name__ == "__main__":
    main()

