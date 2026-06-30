import pygame as pg
import os
import json
from spritesheet import SpriteSheet
import random
import numpy as np

SCREEN = WIDTH, HEIGHT = 640, 360
pg.init()
clock = pg.time.Clock()
screen = pg.display.set_mode(SCREEN)

font = pg.font.Font(r"assets\fonts\KiwiSoda.ttf", 24)
golden_mask = pg.image.load(r"assets\images\golden_mask.png")

modification_types = {
    "grow_speed",
    "money_multiplier",
    "golden_chance",
    "slap_dmg",
    "bonus_kill",
}


def apply_mask(target, mask):
    """
    Blits `mask` onto `target` with normal alpha blending,
    then clips the output to target's original alpha shape
    (so nothing becomes visible where target was transparent).
    """
    target = target.convert_alpha()
    mask = mask.convert_alpha()

    if mask.get_size() != target.get_size():
        mask = pg.transform.smoothscale(mask, target.get_size())

    result = target.copy()
    result.blit(mask, (0, 0))  # normal alpha-over-alpha blend

    # Clip output alpha to target's original alpha (per-pixel min)
    target_alpha = pg.surfarray.pixels_alpha(target)
    result_alpha = pg.surfarray.pixels_alpha(result)
    np.minimum(result_alpha, target_alpha, out=result_alpha)
    del target_alpha, result_alpha  # release locks before further use

    return result


def image_from_spreadsheet(path, data_path):
    ss = SpriteSheet(path)
    with open(data_path, "r") as f:
        data = json.load(f)

    w, h = data["meta"]["frame"]["w"], data["meta"]["frame"]["h"]
    layers = len(data["meta"]["layers"]) - 1
    images = ss.load_strip((0, 0, w, h), layers)

    result = pg.Surface((w, h), pg.SRCALPHA)
    result.blits([(img, (0, 0)) for img in images])
    return result

def get_center(surface: pg.surface.Surface, pos):
    w,h = surface.get_width(),surface.get_height()
    x = pos[0]-w//2
    y=pos[1]-h//2
    return (x,y)

class Item:
    def __init__(self, price, modifiers, level, one_time=False):
        """
        modifiers = {
            'name1':mod_val_int,
            'mod2':...,
            ...
        }
        """
        self.level = level
        self.price = price
        self.one_time = one_time

        self.modifiers = modifiers


class PlayerStats:
    def __init__(self):
        self.score = 0
        self.money = 0
        self.upgrades = {
            "grow_speed": 0,  # (0,1) ------ 0 is worst ////  1 is best
            "money_multiplier": 1,
            "golden_chance": 1,  # 1,100
            "slap_dmg": 1,  # 1,5
            "bonus_kill": 0,  # idk money for each kill
        }

    def buy(self, item: Item):

        pass


class Button:
    def __init__(
        self,
        pos,
        scale,
        text="",
        path="",
        hover_scale=(1.02, 1.02),
    ):
        self.rect = pg.Rect(pos[0], pos[1], scale[0], scale[1])
        self.text = text
        self.path = path
        self.current_scale = (1, 1)
        self.hover_scale = hover_scale

        if len(text) != 0:
            self.surf = font.render(self.text, True, (255, 255, 255))
        elif len(path) != 0:
            self.surf = pg.image.load(path)

        self.surf_rect = self.surf.get_rect(center=self.rect.center)

    def draw(self, surface):
        # rect = pg.draw.rect(surface, (255,255,255), self.rect, border_radius=8)
        # rect = pg.transform.scale(rect, self.current_scale)
        surface.blit(self.surf, self.surf_rect)

    def update(self, mouse_pos):
        self.animate(mouse_pos)

    def animate(self, mouse_pos):
        if self.rect.collidepoint(mouse_pos):
            self.current_scale = self.hover_scale
        else:
            self.current_scale = (1, 1)

    def check_click(self, mouse_pos):
        return self.rect.collidepoint(mouse_pos) and pg.mouse.get_pressed()[0]


class Plant(Button):
    def __init__(
        self,
        health,
        grow_time,
        value,
        sprite_path,
        pos,
        stats: PlayerStats,
        sheet_data="",
        sprite_nr=-1,
    ):

        self.health = health
        self.grow_time = max(0.25, grow_time - grow_time * stats.upgrades["grow_speed"])
        self.golden = random.uniform(0, 100) <= stats.upgrades["golden_chance"]
        self.value = value
        self.timer = 0
        self.collectable = False
        self.sprite_path = sprite_path
        self.pos = pos
        self.current_frame = 0

        self.ss = SpriteSheet(self.sprite_path)

        with open(sheet_data, "r") as f:
            self.sheet_data = json.load(f)

        self.layers = len(self.sheet_data["meta"]["layers"]) - 1
        if sprite_nr >= self.layers:
            sprite_nr = self.layers - 1
        if sprite_nr == -1:
            sprite_nr = random.randint(0, self.layers - 1)
        self.sprite_nr = sprite_nr
        self.imgs = self.ss.load_strip(
            (
                0,
                self.sprite_nr * self.sheet_data["meta"]["frame"]["h"],
                self.sheet_data["meta"]["frame"]["w"],
                self.sheet_data["meta"]["frame"]["h"],
            ),
            self.sheet_data["meta"]["frames"],
        )
        self.img = self.imgs[0]
        pos = get_center(self.img, pos)
        self.pos = pos
        # print(f"IMAGE: {self.img}, index: {self.sprite_nr}, layers: {self.layers}")
        self.rect = self.img.get_rect()
        super().__init__(self.pos, self.img.get_size(), text="nigger")

    def get_payout(self, stats: PlayerStats):
        return (
            random.randrange(max(0, self.value - 20), self.value)
            * stats.upgrades["money_multiplier"]
            * (1.5 if self.golden else 1)
        )

    def update(self, dt, mouse_pos):
        self.animate(mouse_pos)
        self.grow(dt)

        if self.collectable and self.check_click(mouse_pos):
            # delete
            # print("COLLECT")
            return True
        return False

    def animate(self, mouse_pos):
        if self.rect.collidepoint(mouse_pos) and self.collectable:
            self.current_scale = self.hover_scale
        else:
            self.current_scale = (1, 1)

    def draw(self, screen):
        base_w = self.sheet_data["meta"]["frame"]["w"]
        base_h = self.sheet_data["meta"]["frame"]["h"]

        target_w = int(base_w * self.current_scale[0])
        target_h = int(base_h * self.current_scale[1])

        scaled_img = pg.transform.scale(self.img, (target_w, target_h))

        orig_center_x = self.pos[0] + (base_w // 2)
        orig_center_y = self.pos[1] + (base_h // 2)

        self.rect = scaled_img.get_rect(center=(orig_center_x, orig_center_y))
        if self.golden:
            global golden_mask
            scaled_img = apply_mask(scaled_img, golden_mask)

        screen.blit(scaled_img, self.rect)

    def grow(self, dt):
        if self.timer <= self.grow_time:
            self.timer += dt

            progress = self.timer / self.grow_time
            frame_index = int(progress * len(self.imgs))
            frame_index = min(frame_index, len(self.imgs) - 1)
            # print(progress, frame_index)
            self.current_frame = frame_index
            self.img = self.imgs[self.current_frame]
        else:
            # fully grown
            self.collectable = True
            self.img = self.imgs[-1]


class Entity:
    def __init__(self, scale, pos, speed, atk):
        self.scale = scale
        self.pos = pos
        self.speed = speed
        self.atk = atk

    def update(self):
        self.move()

    def move(self):
        pass

    def damage_plant(self, plant):
        pass


def main():
    background_img = pg.image.load(r"assets\images\background.png").convert()
    player = PlayerStats()
    vase = image_from_spreadsheet(r"assets\images\vase.png", r"assets\images\vase.json")
    plant = None
    running = True
    money_text = font.render(f'MONEY: {player.money}',True,(50,150,0))

    while running:

        for event in pg.event.get():
            if event.type == pg.QUIT:
                running = False

        dt = clock.tick(60) / 1000

        if plant is None:
            plant = Plant(
                health=100,
                grow_time=15,
                value=100,
                sprite_path=r"assets\images\plants.png",
                pos=(WIDTH // 2, HEIGHT // 2-10),
                sheet_data=r"assets\images\plants.json",
                stats=player,
            )

        mouse_pos = pg.mouse.get_pos()
        screen.fill((0, 0, 0))
        screen.blit(background_img, (0, 0))

        screen.blit(vase, get_center(vase, (WIDTH // 2, HEIGHT // 2 + 100)))

        plant.draw(screen)
        clicked = plant.update(dt, mouse_pos)
        
        if clicked:
            # collect
            value = plant.get_payout(player)
            player.money += value
            print("Coins", player.money)
            money_text = font.render(f'MONEY: {player.money}',True,(50,150,0))
            plant = None

        screen.blit(money_text, (10,10))
        pg.display.flip()


if __name__ == "__main__":
    main()
