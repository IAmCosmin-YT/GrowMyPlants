import pygame as pg
import os
import json
from spritesheet import SpriteSheet
import random
import numpy as np

DEBUG = False

SCREEN = WIDTH, HEIGHT = 640, 360
pg.init()
clock = pg.time.Clock()
screen = pg.display.set_mode(SCREEN)

font_kiwi = pg.font.Font(r"assets\fonts\KiwiSoda.ttf", 24)
font_arial = pg.font.SysFont("Arial", 24)
golden_mask = pg.image.load(r"assets\images\golden_mask.png")

modification_types = {
    "grow_speed",
    "money_multiplier",
    "golden_chance",
    "slap_dmg",
    "bonus_kill",
}


def apply_mask(target, mask, alpha=255):
    target = target.convert_alpha()
    mask = mask.convert_alpha()

    if mask.get_size() != target.get_size():
        mask = pg.transform.smoothscale(mask, target.get_size())
    mask.set_alpha(alpha)
    result = target.copy()
    result.blit(mask, (0, 0))  # normal alpha-over-alpha blend

    # Clip output alpha to target's original alpha (per-pixel min)
    target_alpha = pg.surfarray.pixels_alpha(target)
    result_alpha = pg.surfarray.pixels_alpha(result)
    np.minimum(result_alpha, target_alpha, out=result_alpha)
    del target_alpha, result_alpha  # release locks before further use

    return result


def make_wet_overlay(base_surf, color=(36, 67, 160), alpha=90):
    """Creates a tinted overlay matching the alpha shape of base_surf."""
    overlay = pg.Surface(base_surf.get_size(), pg.SRCALPHA)
    overlay.fill((*color, alpha))

    base_alpha = pg.surfarray.pixels_alpha(base_surf)
    overlay_alpha = pg.surfarray.pixels_alpha(overlay)
    np.minimum(overlay_alpha, base_alpha, out=overlay_alpha)
    del base_alpha, overlay_alpha

    return overlay


def image_from_spreadsheet(path, data_path, apply_masks=False, masks_to_apply=[]):
    ss = SpriteSheet(path)
    with open(data_path, "r") as f:
        data = json.load(f)

    w, h = data["meta"]["frame"]["w"], data["meta"]["frame"]["h"]
    layers = len(data["meta"]["layers"]) - 1
    images = ss.load_strip((0, 0, w, h), layers)

    if apply_masks and data["meta"]["masks"]:
        for i in range(len(images)):
            img = images[i]
            for mask_info in data["meta"]["masks"]:
                if (
                    mask_info["name"] in masks_to_apply
                    and mask_info["layer"] == data["meta"]["layers"][i + 1]["name"]
                ):
                    mask_path = mask_info["path"]
                    mask = pg.image.load(mask_path).convert_alpha()
                    img = apply_mask(img, mask)
                    images[i] = img

    result = pg.Surface((w, h), pg.SRCALPHA)
    result.blits([(img, (0, 0)) for img in images])
    return result


def get_center(surface: pg.surface.Surface, pos):
    w, h = surface.get_width(), surface.get_height()
    x = pos[0] - w // 2
    y = pos[1] - h // 2
    return (x, y)


def draw_debug_lines(
    screen, lines, pos=(10, 10), color=(255, 255, 255), line_spacing=4, bg=True
):
    """Render a list of debug strings stacked vertically, with an optional background for readability."""
    x, y = pos
    rendered = [font_arial.render(line, True, color) for line in lines]

    if bg:
        width = max(r.get_width() for r in rendered) + 12
        height = (
            sum(r.get_height() for r in rendered)
            + line_spacing * (len(rendered) - 1)
            + 12
        )
        bg_surf = pg.Surface((width, height), pg.SRCALPHA)
        bg_surf.fill((0, 0, 0, 160))
        screen.blit(bg_surf, (x - 6, y - 6))

    for surf in rendered:
        screen.blit(surf, (x, y))
        y += surf.get_height() + line_spacing


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
            "golden_chance": 88,  # 1,100
            "slap_dmg": 1,  # 1,5
            "bonus_kill": 0,  # idk money for each kill
            "wet_multiplier": 1,  # how efficient the water is
        }

    def debug_draw(self, screen):
        u = self.upgrades
        lines = [
            f"Score: {self.score}",
            f"Money: {self.money}",
            f"Grow Speed: {u['grow_speed']:.2f}",
            f"Money Multiplier: {u['money_multiplier']:.2f}",
            f"Golden Chance: {u['golden_chance']:.2f}",
            f"Slap Damage: {u['slap_dmg']:.2f}",
            f"Bonus Kill: {u['bonus_kill']:.2f}",
            f"Wet Multiplier: {u['wet_multiplier']:.2f}",
        ]
        draw_debug_lines(screen, lines, pos=(10, 40))

    def buy(self, item: Item):

        pass


class Button:
    """Static, clickable/hoverable UI element (menu buttons, icons, etc.)"""

    def __init__(
        self,
        pos,
        scale,
        text="",
        path="",
        hover_scale=(1.05, 1.05),
    ):
        # self.rect = pg.Rect(pos[0], pos[1], scale[0], scale[1])
        # self.start_pos = self.rect.center
        self.text = text
        self.path = path
        self.current_scale = (1, 1)
        self.hover_scale = hover_scale

        if len(text) != 0:
            self.surf = font_kiwi.render(self.text, True, (255, 255, 255))
        elif len(path) != 0:
            self.surf = pg.image.load(path)

        self.rect = self.surf.get_rect()
        self.rect.center = pos
        self.start_pos = self.rect.center

        self.surf_rect = self.surf.get_rect(center=self.rect.center)

    def draw(self, surface):
        surface.blit(self.surf, self.surf_rect)

    def debug_draw(self, surface):
        pg.draw.rect(surface, (255, 0, 0), self.rect, 2)
        pg.draw.rect(surface, (0, 255, 0), self.surf_rect, 2)

    def update(self, mouse_pos):
        self.animate(mouse_pos)

    def animate(self, mouse_pos):
        if self.rect.collidepoint(mouse_pos):
            self.current_scale = self.hover_scale
        else:
            self.current_scale = (1, 1)

    def check_click(self, mouse_pos):
        if self.rect.collidepoint(mouse_pos) and pg.mouse.get_pressed()[0]:
            return True
        return False


class DraggableItem(Button):
    """A Button that can be picked up and dragged around with the mouse."""

    def __init__(
        self,
        pos,
        scale,
        text="",
        path="",
        hover_scale=(1.05, 1.05),
        func=None,
    ):
        super().__init__(pos, scale, text, path, hover_scale)
        self.picked_up = False
        self.last_mb0 = False  # edge-detect for pickup/drop clicks
        self.last_mb1 = False  # edge-detect for "use" clicks
        self.func = func

    def update(
        self, mouse_pos, dt, picked_object, mb0_pressed=False, mb1_pressed=False
    ):
        self.animate(mouse_pos)

        # reset edge-detect flags once the button is released
        if self.last_mb0 and not mb0_pressed:
            self.last_mb0 = False
        if self.last_mb1 and not mb1_pressed:
            self.last_mb1 = False

        self.pickup(mouse_pos, picked_object, mb0_pressed)

        if self.picked_up:
            if self.check_click_with_sprite(mouse_pos, mb1_pressed):
                self.func() if self.func else None

            self.surf_rect.center = mouse_pos
            return self
        return None

    def pickup(self, mouse_pos, picked_object, mb0_pressed):
        if not self.picked_up and self.check_click(mouse_pos, mb0_pressed):
            self.start_pickup(mouse_pos)
            if picked_object and picked_object is not self:
                picked_object.stop_pickup()
        elif self.picked_up and self.check_click(mouse_pos, mb0_pressed):
            self.stop_pickup()

    def switch_pickup(self, mouse_pos):
        if self.picked_up:
            self.stop_pickup()
        else:
            self.start_pickup(mouse_pos)

    def start_pickup(self, mouse_pos):
        self.picked_up = True
        self.surf_rect.center = mouse_pos

    def stop_pickup(self):
        self.picked_up = False
        self.surf_rect.center = self.start_pos

    def check_click(self, mouse_pos, mb0_pressed=False):
        if not self.last_mb0 and self.rect.collidepoint(mouse_pos) and mb0_pressed:
            self.last_mb0 = True
            return True
        return False

    def check_click_with_sprite(self, mouse_pos, mb1_pressed=False):
        if not self.last_mb1 and self.surf_rect.collidepoint(mouse_pos) and mb1_pressed:
            print("CLICKED")
            self.last_mb1 = True
            return True
        return False


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
        self.wet = False
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
        super().__init__(self.pos, self.img.get_size(), text="test")

    def get_payout(self, stats: PlayerStats):
        return (
            random.randrange(max(0, self.value - 20), self.value)
            * stats.upgrades["money_multiplier"]
            * (1.5 if self.golden else 1)
        )

    def debug_draw(self, screen, stats: PlayerStats):
        super().debug_draw(screen)
        rate = self.get_grow_rate(stats)
        remaining = max(0, (self.grow_time - self.timer) / rate)
        payout = (
            self.value
            * stats.upgrades["money_multiplier"]
            * (1.5 if self.golden else 1)
        )

        lines = [
            f"Health: {self.health}",
            f"Grow Time: {self.grow_time:.2f}",
            f"Grow Rate: {rate:.2f}",
            f"Remaining Time: {remaining:.2f}s",
            f"Value: {self.value}",
            f"Golden: {self.golden}",
            f"Wet: {self.wet}",
            f"Timer: {self.timer:.2f}",
            f"Collectable: {self.collectable}",
            f"Possible Payout: {payout:.2f}",
        ]
        draw_debug_lines(screen, lines, pos=(225, 40))

    def update(self, dt, mouse_pos, stats):
        self.animate(mouse_pos)
        self.grow(dt, stats)

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
            # golden_overlay = make_wet_overlay(
            #     scaled_img, color=(255, 215, 0), alpha=120
            # )
            # scaled_img.blit(golden_overlay, (0, 0))

        screen.blit(scaled_img, self.rect)

    def get_grow_rate(self, stats: PlayerStats):
        return stats.upgrades["wet_multiplier"] if self.wet else 0.7

    def grow(self, dt, stats: PlayerStats):
        if self.timer <= self.grow_time:
            self.timer += dt * self.get_grow_rate(stats)
            progress = self.timer / self.grow_time
            frame_index = int(progress * len(self.imgs))
            frame_index = min(frame_index, len(self.imgs) - 1)
            self.current_frame = frame_index
            self.img = self.imgs[self.current_frame]
        else:
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


def water_plant(plant: Plant):
    if plant is not None:
        plant.wet = True
        print("WATERED PLANT")


def main():
    background_img = pg.image.load(r"assets\images\background.png").convert()
    player = PlayerStats()

    vase = image_from_spreadsheet(r"assets\images\vase.png", r"assets\images\vase.json")
    wet_vase = image_from_spreadsheet(
        r"assets\images\vase.png",
        r"assets\images\vase.json",
        apply_masks=True,
        masks_to_apply=["wet_soil"],
    )

    plant = None
    money_text = font_kiwi.render(f"MONEY: {player.money}", True, (50, 150, 0))

    # items
    slapper = DraggableItem(
        pos=(WIDTH - 100, HEIGHT - 100),
        scale=(64, 64),
        path=r"assets\images\slapper.png",
    )
    watering_can = DraggableItem(
        pos=(100, HEIGHT - 100),
        scale=(64, 64),
        path=r"assets\images\watering_can.png",
        func=lambda: water_plant(plant) if plant else None,
    )
    items = [slapper, watering_can]

    picked_object = None

    inter_timeout = 0.1
    running = True
    while running:

        for event in pg.event.get():
            if event.type == pg.QUIT:
                running = False

        dt = clock.tick(60) / 1000

        mb0_pressed = pg.mouse.get_pressed()[0]
        mb2_pressed = pg.mouse.get_pressed()[2]
        # print(mb0_pressed, mb2_pressed)
        keys = pg.key.get_pressed()
        inter_timeout -= dt

        if plant is None:
            plant = Plant(
                health=100,
                grow_time=2,
                value=100,
                sprite_path=r"assets\images\plants.png",
                pos=(WIDTH // 2, HEIGHT // 2 - 10),
                sheet_data=r"assets\images\plants.json",
                stats=player,
            )

        mouse_pos = pg.mouse.get_pos()
        screen.fill((0, 0, 0))
        screen.blit(background_img, (0, 0))

        if plant.wet:
            screen.blit(wet_vase, get_center(wet_vase, (WIDTH // 2, HEIGHT // 2 + 100)))
        else:
            screen.blit(vase, get_center(vase, (WIDTH // 2, HEIGHT // 2 + 100)))

        plant.draw(screen)
        clicked = plant.update(dt, mouse_pos, player)

        # if keys[pg.K_1] and inter_timeout <= 0:
        #     inter_timeout = 0.1
        #     watering_can.switch_pickup(mouse_pos)

        for item in items:
            result = item.update(mouse_pos, dt, picked_object, mb0_pressed, mb2_pressed)
            if result is not None:
                picked_object = result
            item.draw(screen)

        if clicked:
            # collect
            value = plant.get_payout(player)
            player.money += value
            # print("Money", player.money)
            money_text = font_kiwi.render(f"MONEY: {player.money}", True, (50, 150, 0))
            plant = None

        if DEBUG or keys[pg.K_d]:
            player.debug_draw(screen)
            if plant is not None:
                plant.debug_draw(screen, player)
            slapper.debug_draw(screen)
            watering_can.debug_draw(screen)
        screen.blit(money_text, (10, 10))
        pg.display.flip()


if __name__ == "__main__":
    main()
