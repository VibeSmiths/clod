#!/home/mack3y/interpreter-venv/bin/python3
"""Generate OmniAI icon — MACK3Y-inspired style.

Visual: dark space background inside a silver gear ring,
robot figure with cyan hoodie sitting inside, 'OmniAI' banner.
"""
import math
from PIL import Image, ImageDraw, ImageFilter

SIZE   = 256
CX, CY = SIZE // 2, SIZE // 2

# ── Palette ────────────────────────────────────────────────────────────────────
BG          = (5, 5, 12, 255)
GEAR_OUTER  = (185, 192, 205, 255)
GEAR_MID    = (145, 152, 165, 255)
GEAR_INNER  = (110, 115, 130, 255)
SPACE_DARK  = (8, 8, 25, 255)
SPACE_MID   = (18, 18, 55, 255)
SPACE_LIGHT = (30, 25, 80, 255)
CYAN        = (100, 220, 195, 255)
CYAN_DK     = (60, 160, 140, 255)
ROBOT_BODY  = (150, 158, 172, 255)
ROBOT_DK    = (100, 108, 122, 255)
ROBOT_LT    = (190, 198, 212, 255)
FACE_DARK   = (20, 22, 30, 255)
WHITE       = (240, 245, 255, 255)
BANNER_BG   = (140, 148, 162, 255)
BANNER_LT   = (185, 193, 207, 255)
BANNER_EDGE = (80, 85, 95, 255)
TEXT_DARK   = (20, 22, 30, 255)

img  = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)


def circle(cx, cy, r, **kw):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], **kw)


def poly(*pts, **kw):
    draw.polygon(list(pts), **kw)


# ── 1. Gear (outer ring with teeth) ───────────────────────────────────────────
GEAR_R      = 120
TOOTH_OUT   = 128
TOOTH_IN    = 112
GEAR_HOLE_R = 96
TEETH       = 14

points = []
for i in range(TEETH * 4):
    seg   = i // 4
    phase = i % 4
    base_angle  = (2 * math.pi * seg / TEETH) - math.pi / 2
    tooth_w     = math.pi / TEETH * 0.55

    if   phase == 0: angle, r = base_angle - tooth_w * 0.8, GEAR_R
    elif phase == 1: angle, r = base_angle - tooth_w * 0.5, TOOTH_OUT
    elif phase == 2: angle, r = base_angle + tooth_w * 0.5, TOOTH_OUT
    else:            angle, r = base_angle + tooth_w * 0.8, GEAR_R

    points.append((CX + r * math.cos(angle), CY + r * math.sin(angle)))

# Gear fill (mid → outer)
draw.polygon(points, fill=GEAR_MID)

# Outer edge highlight
for i in range(len(points)):
    a = points[i]; b = points[(i + 1) % len(points)]
    draw.line([a, b], fill=GEAR_OUTER, width=2)

# Gear inner bevel ring
for r, clr in [(GEAR_HOLE_R + 5, GEAR_INNER), (GEAR_HOLE_R + 2, GEAR_MID)]:
    circle(CX, CY, r, outline=clr, width=2)

# ── 2. Space background inside gear ───────────────────────────────────────────
circle(CX, CY, GEAR_HOLE_R - 1, fill=SPACE_DARK)

# Swirl of nebula blobs
for cx2, cy2, r2, clr in [
    (CX - 20, CY - 25, 55, SPACE_LIGHT),
    (CX + 15, CY + 10, 45, SPACE_MID),
    (CX - 10, CY + 20, 38, SPACE_LIGHT),
    (CX + 20, CY - 30, 32, SPACE_MID),
]:
    nebula = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    nd     = ImageDraw.Draw(nebula)
    nd.ellipse([cx2 - r2, cy2 - r2, cx2 + r2, cy2 + r2], fill=clr)
    nebula = nebula.filter(ImageFilter.GaussianBlur(r2 // 2))
    img.alpha_composite(nebula)

draw = ImageDraw.Draw(img)  # refresh after compositing

# Re-mask to gear circle (clip out anything outside)
mask = Image.new("L", (SIZE, SIZE), 0)
md   = ImageDraw.Draw(mask)
md.ellipse([CX - GEAR_HOLE_R, CY - GEAR_HOLE_R, CX + GEAR_HOLE_R, CY + GEAR_HOLE_R], fill=255)
# Apply: outside mask stays transparent (we already drew on img, mask only for nebula layer handled above)

# Stars
import random; rng = random.Random(42)
for _ in range(55):
    sx = rng.randint(CX - GEAR_HOLE_R + 5, CX + GEAR_HOLE_R - 5)
    sy = rng.randint(CY - GEAR_HOLE_R + 5, CY + GEAR_HOLE_R - 5)
    if (sx - CX) ** 2 + (sy - CY) ** 2 < (GEAR_HOLE_R - 4) ** 2:
        alpha = rng.randint(100, 255)
        sz    = rng.choice([1, 1, 1, 2])
        draw.ellipse([sx, sy, sx + sz, sy + sz],
                     fill=(255, 255, 255, alpha))

# ── 3. Robot figure ────────────────────────────────────────────────────────────
# Layout (from top): HEAD_CY=92, BODY_CY=138, banner at y≈195

BODY_CX = CX          # 128
BODY_CY = CY + 18     # 146  — torso/lap center (slightly lower)
HEAD_CX = CX          # 128
HEAD_CY = CY - 16     # 112  — head lower, close to shoulders
HEAD_R  = 33          # 50% bigger head

# ── Legs (sitting) ──────────────────────────────────────────────────────────
# Lap/base
draw.ellipse([BODY_CX - 32, BODY_CY + 18, BODY_CX + 32, BODY_CY + 48],
             fill=ROBOT_BODY)
# Left leg
draw.ellipse([BODY_CX - 40, BODY_CY + 24, BODY_CX - 6,  BODY_CY + 54],
             fill=ROBOT_DK)
# Right leg
draw.ellipse([BODY_CX + 6,  BODY_CY + 24, BODY_CX + 40, BODY_CY + 54],
             fill=ROBOT_DK)
# Knee highlights
circle(BODY_CX - 24, BODY_CY + 46, 8, fill=ROBOT_LT)
circle(BODY_CX + 24, BODY_CY + 46, 8, fill=ROBOT_LT)

# ── Torso ────────────────────────────────────────────────────────────────────
draw.rounded_rectangle(
    [BODY_CX - 24, BODY_CY - 10, BODY_CX + 24, BODY_CY + 28],
    radius=9, fill=ROBOT_BODY,
)
# Chest plate highlight
draw.rounded_rectangle(
    [BODY_CX - 19, BODY_CY - 6, BODY_CX + 5, BODY_CY + 12],
    radius=5, fill=ROBOT_LT,
)

# ── Hoodie shoulders/body (drawn OVER torso) ─────────────────────────────────
hoodie_body = [
    (BODY_CX - 35, BODY_CY - 4),
    (BODY_CX - 28, BODY_CY + 28),
    (BODY_CX + 28, BODY_CY + 28),
    (BODY_CX + 35, BODY_CY - 4),
    (BODY_CX + 26, BODY_CY - 22),
    (BODY_CX - 26, BODY_CY - 22),
]
draw.polygon(hoodie_body, fill=(*CYAN[:3], 220))

# ── Arms hugging knees ────────────────────────────────────────────────────────
# Left arm upper
draw.ellipse([BODY_CX - 46, BODY_CY + 4,  BODY_CX - 20, BODY_CY + 30], fill=CYAN_DK)
# Left arm lower / wrapping
draw.ellipse([BODY_CX - 44, BODY_CY + 24, BODY_CX - 16, BODY_CY + 46], fill=CYAN)
# Right arm upper
draw.ellipse([BODY_CX + 20, BODY_CY + 4,  BODY_CX + 46, BODY_CY + 30], fill=CYAN_DK)
# Right arm lower / wrapping
draw.ellipse([BODY_CX + 16, BODY_CY + 24, BODY_CX + 44, BODY_CY + 46], fill=CYAN)
# Sleeve cuffs
draw.ellipse([BODY_CX - 44, BODY_CY + 42, BODY_CX - 18, BODY_CY + 54], fill=(*CYAN[:3], 255))
draw.ellipse([BODY_CX + 18, BODY_CY + 42, BODY_CX + 44, BODY_CY + 54], fill=(*CYAN[:3], 255))
# Hands (metallic nubs)
circle(BODY_CX - 12, BODY_CY + 48, 8, fill=ROBOT_LT)
circle(BODY_CX + 12, BODY_CY + 48, 8, fill=ROBOT_LT)

# ── Hood ─────────────────────────────────────────────────────────────────────
# Step 1: big hood back (dark cyan dome behind the head)
circle(HEAD_CX, HEAD_CY + 4, HEAD_R + 14, fill=CYAN_DK)
# Step 2: hood outer rim (bright cyan, slightly smaller = visible rim edge)
circle(HEAD_CX, HEAD_CY + 2, HEAD_R + 11, fill=CYAN)
# Step 3: the actual ROBOT HEAD in the middle (silver/gray, clearly round)
circle(HEAD_CX, HEAD_CY, HEAD_R, fill=ROBOT_BODY)
# Step 4: subtle head highlight (top-left)
circle(HEAD_CX - 10, HEAD_CY - 10, HEAD_R - 14, fill=ROBOT_LT)

# ── Face features ─────────────────────────────────────────────────────────────
# BIG dark oval eyes — key to the MACK3Y look (scaled for larger head)
EYE_W, EYE_H = 14, 17
EYE_Y = HEAD_CY - 4
# Left eye
draw.ellipse([HEAD_CX - 22, EYE_Y - EYE_H//2,
              HEAD_CX - 22 + EYE_W, EYE_Y + EYE_H//2], fill=FACE_DARK)
# Right eye
draw.ellipse([HEAD_CX + 8,  EYE_Y - EYE_H//2,
              HEAD_CX + 8 + EYE_W,  EYE_Y + EYE_H//2], fill=FACE_DARK)
# Eye glints
draw.ellipse([HEAD_CX - 21, EYE_Y - EYE_H//2 + 1,
              HEAD_CX - 17, EYE_Y - EYE_H//2 + 5], fill=(80, 130, 220, 220))
draw.ellipse([HEAD_CX + 9,  EYE_Y - EYE_H//2 + 1,
              HEAD_CX + 13, EYE_Y - EYE_H//2 + 5], fill=(80, 130, 220, 220))
# Sad/neutral mouth
mouth_y = HEAD_CY + 13
draw.arc([HEAD_CX - 10, mouth_y, HEAD_CX + 10, mouth_y + 8],
         start=10, end=170, fill=FACE_DARK, width=2)

# ── 4. Banner ──────────────────────────────────────────────────────────────────
BAN_Y1 = CY + 68
BAN_Y2 = CY + 90
BAN_W  = 88

# Banner body
draw.polygon([
    (CX - BAN_W,     BAN_Y1 + 4),
    (CX - BAN_W - 8, BAN_Y1 + 14),
    (CX - BAN_W,     BAN_Y2),
    (CX + BAN_W,     BAN_Y2),
    (CX + BAN_W + 8, BAN_Y1 + 14),
    (CX + BAN_W,     BAN_Y1 + 4),
], fill=BANNER_BG)

# Banner highlight strip
draw.polygon([
    (CX - BAN_W,     BAN_Y1 + 4),
    (CX + BAN_W,     BAN_Y1 + 4),
    (CX + BAN_W,     BAN_Y1 + 10),
    (CX - BAN_W,     BAN_Y1 + 10),
], fill=BANNER_LT)

# Banner edge lines
for dy in [0, 1]:
    draw.line([
        (CX - BAN_W - 8, BAN_Y1 + 14 + dy),
        (CX - BAN_W,     BAN_Y1 + 4 + dy),
        (CX + BAN_W,     BAN_Y1 + 4 + dy),
        (CX + BAN_W + 8, BAN_Y1 + 14 + dy),
        (CX + BAN_W + 8, BAN_Y2 + dy),
        (CX - BAN_W - 8, BAN_Y2 + dy),
        (CX - BAN_W - 8, BAN_Y1 + 14 + dy),
    ], fill=BANNER_EDGE, width=1)

# Banner text "OmniAI"
try:
    from PIL import ImageFont
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
except Exception:
    font = None

txt    = "OmniAI"
txt_y  = BAN_Y1 + 10
if font:
    bbox = draw.textbbox((0, 0), txt, font=font)
    tw   = bbox[2] - bbox[0]
    draw.text((CX - tw // 2, txt_y), txt, fill=TEXT_DARK, font=font)
else:
    draw.text((CX - 22, txt_y), txt, fill=TEXT_DARK)

# ── 5. Re-apply gear (so it sits on top of everything) ────────────────────────
draw.polygon(points, outline=GEAR_OUTER, width=2)
circle(CX, CY, TOOTH_IN - 1, outline=GEAR_INNER, width=3)

# ── 6. Subtle outer glow ──────────────────────────────────────────────────────
glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
gd   = ImageDraw.Draw(glow)
gd.ellipse([CX - 122, CY - 122, CX + 122, CY + 122],
           outline=(100, 220, 195, 80), width=4)
glow = glow.filter(ImageFilter.GaussianBlur(4))
img.alpha_composite(glow)

# ── Save ───────────────────────────────────────────────────────────────────────
out = "/home/mack3y/omni-stack/omni-icon.png"
img.save(out, "PNG")
print(f"Saved {out}  ({SIZE}x{SIZE})")
