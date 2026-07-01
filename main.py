import pygame as pg
import os
import json
from spritesheet import SpriteSheet
import random
import numpy as np
import lerp

DEBUG = False

SCREEN = WIDTH, HEIGHT = 640, 360
SCALE_FACTOR = WIDTH / HEIGHT

pg.init()
clock = pg.time.Clock()
screen = pg.display.set_mode(SCREEN, pg.RESIZABLE)
# need to use a separate surface for scaling, otherwise the game will look blurry when scaled up
game_surface = pg.Surface(SCREEN)

font_kiwi = pg.font.Font(r"assets\fonts\Minecraft.ttf", 24)
font_kiwi_tiny = pg.font.Font(r"assets\fonts\Minecraft.ttf", 16)
font_arial = pg.font.SysFont("Arial", 24)
golden_mask = pg.image.load(r"assets\images\golden_mask.png")

modification_types = {
    "grow_speed",
    "money_multiplier",
    "golden_chance",
    "slap_dmg",
    "bonus_kill",
}


def apply_mask(target, mask, alpha=255, scale=True):
    target = target.convert_alpha()
    mask = mask.convert_alpha()

    if scale and mask.get_size() != target.get_size():
        mask = pg.transform.smoothscale(mask, target.get_size())

    mask.set_alpha(alpha)
    result = target.copy()
    result.blit(mask, (0, 0))

    target_alpha = pg.surfarray.pixels_alpha(target)
    result_alpha = pg.surfarray.pixels_alpha(result)
    np.minimum(result_alpha, target_alpha, out=result_alpha)
    del target_alpha, result_alpha

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
    """
    masks to apply should look like this:
    [
        (name,level),
        ...
    ]
    """

    ss = SpriteSheet(path)
    with open(data_path, "r") as f:
        data = json.load(f)

    w, h = data["meta"]["frame"]["w"], data["meta"]["frame"]["h"]
    layers = len(data["meta"]["layers"]) - 1
    images = ss.load_strip((0, 0, w, h), layers)

    if apply_masks and data["meta"]["masks"]:
        for i in range(len(images)):
            img = images[i]
            for mask_to_apply in masks_to_apply:
                for mask_info in data["meta"]["masks"]:
                    if (
                        mask_info["name"] == mask_to_apply[0]
                        and mask_info["layer"] == data["meta"]["layers"][i + 1]["name"]
                    ):
                        mask_path = mask_info["path"]
                        if mask_info.get("sprite_sheet_data"):

                            mask_data_sheet = None
                            with open(mask_info["sprite_sheet_data"], "r") as f:
                                mask_data_sheet = json.load(f)
                            if mask_data_sheet is None:
                                exit(
                                    f"Failed to load sprite sheet data for mask: {mask_info['sprite_sheet_data']}"
                                )

                            ss_mask = SpriteSheet(mask_path)
                            imgs = ss_mask.load_strip(
                                (
                                    0,
                                    0,
                                    mask_data_sheet["meta"]["frame"]["w"],
                                    mask_data_sheet["meta"]["frame"]["h"],
                                ),
                                len(mask_data_sheet["meta"]["layers"]) - 1,
                            )
                            mask = imgs[mask_to_apply[1]]
                        else:
                            mask = pg.image.load(mask_path).convert_alpha()
                        img = apply_mask(
                            img, mask, alpha=mask_info.get("opacity", 255), scale=False
                        )
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
    def __init__(self, price, modifiers, level):
        """
        modifiers = {
            'name1':mod_val_int,
            'mod2':...,
            ...
        }
        """
        self.level = level
        self.price = price

        self.modifiers = modifiers


class ShopItem(Item):
    def __init__(
        self,
        name,
        description,
        image_path,
        price,
        modifiers,
        level=0,
        max_level=-1,
    ):
        super().__init__(price, modifiers, level)
        self.name = name
        self.description = description
        self.image = pg.image.load(image_path).convert_alpha()
        self.purchased = False
        self.max_level = max_level

    def is_maxed(self) -> bool:
        return self.max_level != -1 and self.level >= self.max_level


class PlayerStats:
    def __init__(self):
        self.score = 0
        self.money = 0
        self.upgrades = {
            "grow_speed": 0,  # (0,1) ------ 0 is worst ////  1 is best
            "money_multiplier": 1,
            "golden_chance": 0.1,  # 0,1
            "slap_dmg": 1,  # 1,5
            "bonus_kill": 0,  # idk money for each kill
            "wet_multiplier": 1,  # how efficient the water is
            "wet_soil_chance": 0,  # 0,1chance for wet soil when the plant is collected
            "wet_soil_duration": 0,  # how long the wet soil lasts
            "auto_collect": False,  # automatically collect the plant when it's ready
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

    def buy(self, item: ShopItem) -> bool:
        if item.is_maxed() and item.purchased:
            return False
        if item.max_level != -1 and item.level >= item.max_level:
            return False
        if self.money < item.price:
            return False

        self.money -= item.price
        for key, val in item.modifiers.items():
            if key in self.upgrades:
                if isinstance(val, bool):
                    self.upgrades[key] = val
                else:
                    self.upgrades[key] += val

        if item.is_maxed():
            item.purchased = True
        return True


# facut cu ajutorul lui claude
class ScrollRect:
    """A scrollable, rounded-corner panel for displaying purchasable items (a shop)."""

    def __init__(
        self,
        rect,
        pos,
        items,  # list of ShopItem
        stats: PlayerStats,
        radius=12,
        item_height=90,
        padding=10,
        bg_color=(30, 30, 40, 230),
        entry_color=(50, 50, 65, 255),
        stroke_color=(255, 255, 255, 255),
        text_color=(0, 0, 0, 255),
        buy_button_color=(60, 140, 60),
        buy_button_color_disabled=(140, 60, 60),
        buy_button_color_unlocked=(60, 60, 140),
        scroll_speed=30,
    ):
        self.rect = pg.Rect(rect)
        self.rect.center = pos
        self.items = items
        self.stats = stats
        self.radius = radius
        self.item_height = item_height
        self.padding = padding
        self.bg_color = bg_color
        self.entry_color = entry_color
        self.stroke_color = stroke_color
        self.text_color = text_color
        self.buy_button_color = buy_button_color
        self.buy_button_color_disabled = buy_button_color_disabled
        self.buy_button_color_unlocked = buy_button_color_unlocked
        self.scroll_speed = scroll_speed
        self.scroll_y = 0

        calc_height = 0
        for item in items:
            calc_height += item_height + padding * (len(item.modifiers) + 3)

        self.content_height = max(
            self.rect.height,
            calc_height,
        )

        # rounded-rect alpha mask, precomputed once at panel size
        self.mask = pg.Surface(self.rect.size, pg.SRCALPHA)
        pg.draw.rect(
            self.mask,
            (255, 255, 255, 255),
            self.mask.get_rect(),
            border_radius=self.radius,
        )

        # (item, content-space rect) for buy buttons, rebuilt each draw()
        self._buy_rects = []

    def handle_event(self, event):
        """Call this from your event loop for scroll support."""
        if event.type == pg.MOUSEWHEEL and self.rect.collidepoint(
            get_scaled_position(
                pg.mouse.get_pos(),
                (
                    game_surface.get_width() / screen.get_width(),
                    game_surface.get_height() / screen.get_height(),
                ),
            )
        ):
            self.scroll_y -= event.y * self.scroll_speed
            max_scroll = max(0, self.content_height - self.rect.height)
            self.scroll_y = max(0, min(self.scroll_y, max_scroll))

    def handle_click(self, mouse_pos, clicked):
        """Call once per frame with the current mouse pos and a one-frame click flag.
        Returns the ShopItem that was successfully purchased, or None."""
        if not clicked or not self.rect.collidepoint(mouse_pos):
            return None

        local_pos = (
            mouse_pos[0] - self.rect.x,
            mouse_pos[1] - self.rect.y + self.scroll_y,
        )
        for item, btn_rect in self._buy_rects:
            if btn_rect.collidepoint(local_pos):
                return item if self.stats.buy(item) else None
        return None

    def draw(self, screen):
        content_surf = pg.Surface((self.rect.width, self.content_height), pg.SRCALPHA)
        content_surf.fill(self.bg_color)

        self._buy_rects = []
        y = self.padding
        for item in self.items:
            custom_height = self.item_height + self.padding * (len(item.modifiers) + 1)
            entry_rect = pg.Rect(
                self.padding,
                y,
                self.rect.width - self.padding * 2,
                custom_height,
            )
            self.draw_item(content_surf, item, entry_rect)
            y += custom_height + self.padding

        # slice the visible window out of the full content
        view = pg.Surface(self.rect.size, pg.SRCALPHA)
        view.blit(content_surf, (0, -self.scroll_y))

        # clip corners: alpha becomes min(content_alpha, mask_alpha) per pixel
        view.blit(self.mask, (0, 0), special_flags=pg.BLEND_RGBA_MIN)

        screen.blit(view, self.rect.topleft)
        pg.draw.rect(screen, self.stroke_color, self.rect, 2, border_radius=self.radius)

    def draw_item(self, surf, item: ShopItem, entry_rect):
        pg.draw.rect(surf, self.entry_color, entry_rect, border_radius=8)

        img_rect = item.image.get_rect(midleft=(entry_rect.x + 10, entry_rect.centery))
        surf.blit(item.image, img_rect)

        text_x = img_rect.right + 10
        name_surf = font_kiwi.render(item.name, True, self.text_color)
        surf.blit(name_surf, (text_x, entry_rect.y + 8))

        desc_surf = font_kiwi_tiny.render(item.description, True, self.text_color)
        surf.blit(desc_surf, (text_x, entry_rect.y + 36))

        modifiers = []
        for key, val in item.modifiers.items():
            if isinstance(val, bool):
                modifiers.append(
                    {
                        "text": f"{key}: {'Active' if val else 'Disabled'} | (current: {'Active' if self.stats.upgrades.get(key, False) else 'Disabled'})",
                        "color": (
                            self.buy_button_color
                            if val
                            else self.buy_button_color_disabled
                        ),
                    }
                )
            else:
                modifiers.append(
                    {
                        "text": f"{key}: {val} | (current: {self.stats.upgrades.get(key, 0)})",
                        "color": (
                            self.buy_button_color
                            if val > 0
                            else self.buy_button_color_disabled
                        ),
                    }
                )

        for i, mod_text in enumerate(modifiers):
            mod_surf = font_kiwi_tiny.render(mod_text["text"], True, mod_text["color"])
            surf.blit(mod_surf, (text_x, entry_rect.y + 60 + i * 20))

        btn_w, btn_h = 80, 30
        btn_rect = pg.Rect(
            entry_rect.right - btn_w - 10, entry_rect.centery - btn_h // 2, btn_w, btn_h
        )

        level_text = (
            f"{item.level}/{item.max_level}"
            if item.max_level != -1
            else f"{item.level}/inf"
        )

        level_surf = font_kiwi_tiny.render(level_text, True, self.text_color)

        if item.is_maxed() and item.purchased:
            label, color = "MAX", self.buy_button_color_unlocked
        else:
            label = format_money(item.price)
            color = (
                self.buy_button_color
                if self.stats.money >= item.price
                else self.buy_button_color_disabled
            )

        pg.draw.rect(surf, color, btn_rect, border_radius=6)
        label_surf = font_kiwi_tiny.render(label, True, self.text_color)
        surf.blit(label_surf, label_surf.get_rect(center=btn_rect.center))
        surf.blit(
            level_surf,
            level_surf.get_rect(center=(btn_rect.centerx, btn_rect.bottom + 12)),
        )

        self._buy_rects.append((item, btn_rect))


class Button:
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
        self.last_mb0 = False
        self.last_mb1 = False
        self.func = func

    def update(
        self, mouse_pos, dt, picked_object, mb0_pressed=False, mb1_pressed=False
    ):
        self.animate(mouse_pos)

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
        self.golden = random.uniform(0, 1) <= stats.upgrades["golden_chance"]
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
            random.uniform(max(0, self.value - 20), self.value)
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


# ------------------------------functions for items
def water_plant(plant: Plant):
    if plant is not None:
        plant.wet = True
        print("WATERED PLANT")


# ------------------------------


def get_scaled_position(pos, scale_factor):
    return (int(pos[0] * scale_factor[0]), int(pos[1] * scale_factor[1]))


def blit_scaled(screen, game_surface, integer_scale=True):
    win_w, win_h = screen.get_size()
    game_w, game_h = game_surface.get_size()

    scale = min(win_w / game_w, win_h / game_h)
    if integer_scale:
        scale = max(1, int(scale))

    new_w, new_h = int(game_w * scale), int(game_h * scale)
    x = (win_w - new_w) // 2
    y = (win_h - new_h) // 2

    scaled = pg.transform.scale(game_surface, (new_w, new_h))
    # black bars to keep aspect ratio
    screen.fill((0, 0, 0))
    screen.blit(scaled, (x, y))
    return pg.Rect(x, y, new_w, new_h)


def format_money(value: float) -> str:
    if value >= 1_000:
        return f"${value/1_000:.2f}K"
    elif value >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    elif value >= 1_000_000_000:
        return f"${value/1_000_000_000:.2f}B"
    return f"${value:.2f}"


def main():
    # -------------------------------global
    global screen
    global font_kiwi
    global font_arial
    cur_money = 0

    background_img = pg.image.load(r"assets\images\background.png").convert()
    player = PlayerStats()

    # vase = image_from_spreadsheet(r"assets\images\vase.png", r"assets\images\vase.json")
    # wet_vase = image_from_spreadsheet(
    #     r"assets\images\vase.png",
    #     r"assets\images\vase.json",
    #     apply_masks=True,
    #     masks_to_apply=[("wet_soil", -1)],
    # )

    plant = None
    money_text = font_kiwi.render(f"MONEY: {player.money:.2f}", True, (50, 150, 0))

    # ------------------------------shop
    shop_items = [
        ShopItem(
            name="Golden Soil",
            description="Increases the chance of a golden plant appearing",
            image_path=r"assets\images\blood.png",
            price=600,
            modifiers={"golden_chance": 0.05},
            max_level=5,
        ),
        ShopItem(
            name="Shower Head",
            description="Increases the chance for wet soil on plant",
            image_path=r"assets\images\blood.png",
            price=1500,
            modifiers={"wet_soil_chance": 0.05},
            max_level=20,
        ),
        ShopItem(
            name="Fertilizer",
            description="Increases the growth speed of the plant",
            image_path=r"assets\images\blood.png",
            price=500,
            modifiers={"grow_speed": 0.05},
            max_level=20,
        ),
        ShopItem(
            name="Heavy Water",
            description="The soil stays wet for the next plant",
            image_path=r"assets\images\blood.png",
            price=5000,
            modifiers={"wet_soil_duration": 1},
            max_level=1,
        ),
        ShopItem(
            name="Plant Picker",
            description="Automatically collects the plant when it's ready",
            image_path=r"assets\images\blood.png",
            price=12500,
            modifiers={"auto_collect": True, "money_multiplier": -0.1},
            max_level=1,
        ),
        ShopItem(
            name="Blood Jar",
            description="Gives you money for each bug you kill",
            image_path=r"assets\images\blood.png",
            price=150,
            modifiers={"bonus_kill": 5},
        ),
        ShopItem(
            name="Slap Upgrade",
            description="Increases your slap damage",
            image_path=r"assets\images\blood.png",
            price=100,
            modifiers={"slap_dmg": 1},
        ),
    ]
    shop_items.sort(key=lambda x: x.price)

    shop = ScrollRect(
        rect=(0, 0, 600, 280),
        pos=(WIDTH // 2, HEIGHT // 2),
        items=shop_items,
        stats=player,
        radius=12,
        # paleta generata cu AI
        bg_color=(
            35,
            28,
            32,
            230,
        ),  # Deep charcoal/brown from the spatula & pot shadows
        entry_color=(86, 62, 53, 255),  # Rich dark brown from the soil pot
        stroke_color=(235, 210, 175, 255),  # Light cream from the seed sack
        text_color=(
            245,
            220,
            200,
            255,
        ),  # Soft peach from the wallpaper (high contrast for dark BG)
        buy_button_color=(60, 190, 85, 255),  # Vibrant green from the leaf sprout
        buy_button_color_disabled=(
            175,
            45,
            45,
            255,
        ),  # Muted crimson red from the wall splatter
        buy_button_color_unlocked=(
            115,
            125,
            135,
            255,
        ),  # Slate blue-grey from the fly's body
    )

    # ---------------------------items
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

    shop_active = False
    last_shop_toggle = False

    last_mb0_pressed = False
    last_mb2_pressed = False

    inter_timeout = 0.1
    running = True
    while running:

        # resized_this_frame = False
        for event in pg.event.get():
            if event.type == pg.QUIT:
                running = False
            # elif event.type == (pg.VIDEORESIZE or pg.WINDOWRESIZED):
            #     print(f"Resized to {event.w}x{event.h}")
            #     print(f"Scale factor: {event.w / WIDTH:.2f}")
            #     font_kiwi = pg.font.Font(
            #         r"assets\fonts\KiwiSoda.ttf", int(24 * (event.w / WIDTH))
            #     )
            #     font_arial = pg.font.SysFont("Arial", int(16 * (event.w / WIDTH)))

            shop.handle_event(event)

        dt = clock.tick(60) / 1000
        cur_money = lerp.fast_lerp(cur_money, player.money, dt * 10, 0.01)

        mb0_pressed = pg.mouse.get_pressed()[0]
        mb0_clicked = mb0_pressed and not last_mb0_pressed
        last_mb0_pressed = mb0_pressed

        mb2_pressed = pg.mouse.get_pressed()[2]
        mb2_clicked = mb2_pressed and not last_mb2_pressed
        last_mb2_pressed = mb2_pressed

        # print(mb0_pressed, mb2_pressed)
        keys = pg.key.get_pressed()
        inter_timeout -= dt

        if keys[pg.K_s] and not last_shop_toggle:
            shop_active = not shop_active
        last_shop_toggle = keys[pg.K_s]

        if plant is None:
            plant = Plant(
                health=100,
                grow_time=2,
                value=99999,
                sprite_path=r"assets\images\plants.png",
                pos=(WIDTH // 2, HEIGHT // 2 - 10),
                sheet_data=r"assets\images\plants.json",
                stats=player,
            )

        mouse_pos = get_scaled_position(
            pg.mouse.get_pos(),
            (WIDTH / screen.get_width(), HEIGHT / screen.get_height()),
        )
        game_surface.fill((0, 0, 0))
        game_surface.blit(background_img, (0, 0))
        masks_to_apply = []

        if player.upgrades["golden_chance"] > 0:
            masks_to_apply.append(
                (
                    "gold_soil",
                    int(
                        lerp.lerp(
                            0, 4, lerp.inv_lerp(0, 1, player.upgrades["golden_chance"])
                        )
                    ),
                )
            )
        if plant.wet:
            masks_to_apply.append(("wet_soil", -1))

        """
        mai trb lucrat la image_from_spreadsheet, pt ca trece peste nr de layere
        """

        vase = image_from_spreadsheet(
            r"assets\images\vase.png",
            r"assets\images\vase.json",
            apply_masks=True,
            masks_to_apply=masks_to_apply,
        )
        game_surface.blit(vase, get_center(vase, (WIDTH // 2, HEIGHT // 2 + 100)))

        plant.draw(game_surface)
        clicked = plant.update(dt, mouse_pos, player)

        # if keys[pg.K_1] and inter_timeout <= 0:
        #     inter_timeout = 0.1
        #     watering_can.switch_pickup(mouse_pos)

        for item in items:
            result = item.update(mouse_pos, dt, picked_object, mb0_clicked, mb2_clicked)
            if result is not None:
                picked_object = result
            item.draw(game_surface)

        if clicked:
            # collect
            value = plant.get_payout(player)
            player.money += value
            # print("Money", player.money)
            # money_text = font_kiwi.render(
            #     f"MONEY: {cur_money:.2f}", True, (50, 150, 0)
            # )
            plant = None

        if shop_active:
            purchased = shop.handle_click(mouse_pos, mb0_clicked)
            if purchased:
                # money_text = font_kiwi.render(
                #     f"MONEY: {cur_money:.2f}", True, (50, 150, 0)
                # )
                print(f"Bought {purchased.name}")

        money_text = font_kiwi.render(
            f"MONEY: {format_money(cur_money)}", True, (50, 150, 0)
        )

        if shop_active:
            shop.draw(game_surface)

        if DEBUG or keys[pg.K_d]:
            player.debug_draw(game_surface)
            if plant is not None:
                plant.debug_draw(game_surface, player)
            slapper.debug_draw(game_surface)
            watering_can.debug_draw(game_surface)

        game_surface.blit(money_text, (10, 10))
        blit_scaled(screen, game_surface, integer_scale=False)
        pg.display.flip()


if __name__ == "__main__":
    main()
