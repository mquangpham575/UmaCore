import io
import os
import logging
import asyncio
import aiohttp
import re
import emoji
import hashlib
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Constants for design
FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")
REGULAR_FONT_PATH = os.path.join(FONT_DIR, "Outfit-Regular.ttf")
BOLD_FONT_PATH = os.path.join(FONT_DIR, "Outfit-Bold.ttf")

FONT_URLS = {
    REGULAR_FONT_PATH: "https://github.com/hoangvu12/kaguya-app/raw/master/assets/fonts/Outfit-Regular.ttf",
    BOLD_FONT_PATH: "https://github.com/hoangvu12/kaguya-app/raw/master/assets/fonts/Outfit-Bold.ttf"
}

CARROT_ICON_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "carrot.png")
CARROT_URL = "https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/72x72/1f955.png"
DEFAULT_AVATAR_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "default_avatar.png")

async def ensure_fonts():
    """Ensure that the premium Outfit font is downloaded and available."""
    os.makedirs(FONT_DIR, exist_ok=True)
    if all(os.path.exists(path) for path in FONT_URLS):
        return
        
    async with aiohttp.ClientSession() as session:
        for path, url in FONT_URLS.items():
            if not os.path.exists(path):
                try:
                    logger.info(f"Downloading premium font from {url}...")
                    async with session.get(url, timeout=30) as resp:
                        if resp.status == 200:
                            content = await resp.read()
                            with open(path, "wb") as f:
                                f.write(content)
                            logger.info(f"Successfully downloaded font: {os.path.basename(path)}")
                        else:
                            logger.warning(f"Failed to download font (status {resp.status}) from {url}")
                except Exception as e:
                    logger.error(f"Error downloading font {url}: {e}", exc_info=True)

async def ensure_carrot_icon():
    """Ensure that the carrot icon PNG is downloaded and available."""
    os.makedirs(os.path.dirname(CARROT_ICON_PATH), exist_ok=True)
    if not os.path.exists(CARROT_ICON_PATH):
        try:
            logger.info("Downloading carrot icon PNG...")
            async with aiohttp.ClientSession() as session:
                async with session.get(CARROT_URL, timeout=15) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        with open(CARROT_ICON_PATH, "wb") as f:
                            f.write(content)
                        logger.info("Successfully downloaded carrot icon.")
                    else:
                        logger.warning(f"Failed to download carrot icon (status {resp.status})")
        except Exception as e:
            logger.error(f"Error downloading carrot icon: {e}", exc_info=True)

_font_cache = {}

def get_font(font_path: str, size: int):
    """Load font or fallback to default if not available."""
    key = (font_path, size)
    if key not in _font_cache:
        try:
            if os.path.exists(font_path):
                _font_cache[key] = ImageFont.truetype(font_path, size)
            else:
                _font_cache[key] = ImageFont.load_default()
        except Exception as e:
            logger.warning(f"Failed to load true font {font_path}: {e}. Falling back to default.")
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]

def make_circular(img: Image.Image) -> Image.Image:
    """Crop an image into a circle with anti-aliasing."""
    # Resize to smooth round circle (super-sampling)
    size = img.size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + size, fill=255)
    
    output = Image.new("RGBA", size, (0, 0, 0, 0))
    output.paste(img, (0, 0), mask=mask)
    return output

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "avatars")
_avatar_memory_cache = {}

async def fetch_avatar(session: aiohttp.ClientSession, url: str) -> Image.Image | None:
    """Asynchronously download avatar image and convert to Pillow Image with caching."""
    # Ensure cache directory exists
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    # Generate unique filename based on URL hash (strip transient query parameters)
    base_url = url.split('?')[0]
    if base_url in _avatar_memory_cache:
        return _avatar_memory_cache[base_url]
        
    url_hash = hashlib.md5(base_url.encode('utf-8')).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"{url_hash}_50.png")
    
    # Return cached image if exists
    if os.path.exists(cache_path):
        try:
            img = Image.open(cache_path).convert("RGBA")
            _avatar_memory_cache[base_url] = img
            return img
        except Exception as e:
            logger.warning(f"Failed to load cached avatar {cache_path}: {e}")
            
    # Fetch from network if not cached
    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.read()
                img = Image.open(io.BytesIO(data))
                img = img.convert("RGBA").resize((50, 50), Image.Resampling.LANCZOS)
                circular_img = make_circular(img)
                # Save to cache
                try:
                    circular_img.save(cache_path, "PNG")
                except Exception as e:
                    logger.warning(f"Failed to cache avatar to {cache_path}: {e}")
                _avatar_memory_cache[base_url] = circular_img
                return circular_img
    except Exception as e:
        logger.error(f"Error fetching avatar from {url}: {e}")
    return None

def clean_title(text: str) -> str:
    """Strip emojis, Discord custom emojis, and special decorative symbols to prevent tofu boxes in rendering."""
    # Remove Discord custom emojis <:name:id> or <a:name:id>
    text = re.sub(r'<a?:\w+:\d+>', '', text)
    # Remove Unicode emojis
    text = emoji.replace_emoji(text, replace='')
    # Keep only standard alphanumeric (\w), spaces (\s), and common punctuation/symbols
    pattern = r'[^\w\s.,\-_()\[\]{}&|!@#$*%\?\'\"/]'
    text = re.sub(pattern, '', text)
    # Clean up excess spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def draw_default_avatar(username: str) -> Image.Image:
    """Load default_avatar.png and crop to a circular fallback avatar, falling back to letter avatar if file missing."""
    if os.path.exists(DEFAULT_AVATAR_PATH):
        try:
            img = Image.open(DEFAULT_AVATAR_PATH).convert("RGBA")
            img = img.resize((50, 50), Image.Resampling.LANCZOS)
            return make_circular(img)
        except Exception as e:
            logger.warning(f"Failed to load fallback avatar image {DEFAULT_AVATAR_PATH}: {e}")
            
    # Circle background fallback
    img = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, 50, 50), fill=(75, 85, 99, 255)) # Gray-600
    
    font = get_font(BOLD_FONT_PATH, 24)
    letter = username[1].upper() if username.startswith("@") and len(username) > 1 else username[0].upper() if username else "?"
    
    bbox = draw.textbbox((0, 0), letter, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text(((50 - w) // 2, (50 - h) // 2 - 3), letter, fill=(255, 255, 255, 255), font=font)
    return img

def format_fans(v: int) -> str:
    """Format fans into human-readable format (e.g. 54.3M, 150K)."""
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.1f}B"
    elif v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    elif v >= 1_000:
        return f"{v / 1_000:.0f}K"
    return str(v)

async def render_leaderboard_image(
    club_name: str,
    leaderboard_data: list[dict],
    current_date_str: str,
    start_rank: int = 1
) -> bytes:
    """
    Renders the leaderboard image with users, ranks, PFPs, and progress bars.
    Returns PNG bytes.
    """
    await ensure_fonts()
    
    # Calculate height based on entries
    row_height = 65
    header_height = 120
    footer_height = 50
    num_rows = max(1, len(leaderboard_data))
    img_width = 800
    img_height = header_height + (row_height * num_rows) + footer_height
    
    # Create canvas: dark theme background (#0F172A - Slate 900)
    base_color = (15, 23, 42, 255)
    img = Image.new("RGBA", (img_width, img_height), base_color)
    draw = ImageDraw.Draw(img)
    
    # Load fonts
    title_font = get_font(BOLD_FONT_PATH, 32)
    subtitle_font = get_font(REGULAR_FONT_PATH, 16)
    rank_font = get_font(BOLD_FONT_PATH, 24)
    username_font = get_font(BOLD_FONT_PATH, 20)
    details_font = get_font(REGULAR_FONT_PATH, 16)
    stat_font = get_font(BOLD_FONT_PATH, 20)
    footer_font = get_font(REGULAR_FONT_PATH, 14)
    
    # Render Header with Carrot Icons
    await ensure_carrot_icon()
    cleaned_club_name = clean_title(club_name) or club_name
    title_text = f"Leaderboard: {cleaned_club_name}"
    
    # Measure title text size
    bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_w = bbox[2] - bbox[0]
    
    # Load and draw carrot icons
    carrot_drawn = False
    if os.path.exists(CARROT_ICON_PATH):
        try:
            carrot_img = Image.open(CARROT_ICON_PATH).convert("RGBA").resize((32, 32), Image.Resampling.LANCZOS)
            
            # Left carrot
            img.paste(carrot_img, (40, 32), carrot_img)
            
            # Title text (shifted right)
            draw.text((82, 30), title_text, fill=(255, 255, 255, 255), font=title_font)
            
            # Right carrot
            img.paste(carrot_img, (82 + title_w + 12, 32), carrot_img)
            carrot_drawn = True
        except Exception as e:
            logger.error(f"Failed to draw carrot icons: {e}", exc_info=True)
            
    if not carrot_drawn:
        # Fallback to standard text layout
        draw.text((40, 30), title_text, fill=(255, 255, 255, 255), font=title_font)

    draw.text((40, 75), f"Active synced trainers • {current_date_str}", fill=(148, 163, 184, 255), font=subtitle_font) # Slate-400
    
    # Render divider under header
    draw.line((40, 110, img_width - 40, 110), fill=(51, 65, 85, 255), width=1) # Slate-700
    
    # Download all avatars in parallel
    async with aiohttp.ClientSession() as session:
        tasks = []
        for row in leaderboard_data:
            avatar_url = row.get("avatar_url")
            if avatar_url:
                tasks.append(fetch_avatar(session, avatar_url))
            else:
                tasks.append(asyncio.sleep(0, result=None)) # Dummy task
        
        avatars = await asyncio.gather(*tasks)
    
    # Draw Rows
    for idx, row in enumerate(leaderboard_data):
        row_top = header_height + (idx * row_height)
        
        # Zebra striping for visual clarity
        if idx % 2 == 1:
            draw.rectangle(
                (20, row_top, img_width - 20, row_top + row_height),
                fill=(21, 30, 49, 255) # Solid blended color to avoid alpha composite bugs in PIL
            )
            
        # 1. Rank styling
        rank = start_rank + idx
        rank_str = f"#{rank}"
        
        # Color mapping for ranks
        if rank == 1:
            rank_color = (251, 191, 36, 255) # Gold
        elif rank == 2:
            rank_color = (148, 163, 184, 255) # Silver
        elif rank == 3:
            rank_color = (217, 119, 6, 255) # Bronze
        else:
            rank_color = (203, 213, 225, 255) # Whiteish
            
        # Draw Rank
        draw.text((40, row_top + 19), rank_str, fill=rank_color, font=rank_font)
        
        # 2. Avatar
        avatar = avatars[idx]
        if avatar is None:
            avatar = draw_default_avatar(row.get("username", "U"))
        
        # Paste avatar at x = 110, centered vertically (row_height is 65, avatar is 50, so (65-50)/2 = 7.5)
        img.paste(avatar, (110, row_top + 7), avatar)
        
        # 3. User Details
        username = row.get("username", "Unknown User")
        trainer_name = row.get("trainer_name", "Unknown Trainer")
        
        # Clean username and trainer name to prevent tofu boxes
        username = clean_title(username)
        trainer_name = clean_title(trainer_name)
        
        # Clean username format
        if not username.startswith("@"):
            username = f"@{username}"
            
        # Draw Username
        draw.text((180, row_top + 20), username, fill=(255, 255, 255, 255), font=username_font)
        
        # Draw Trainer display name next to username if provided
        if trainer_name and trainer_name.strip():
            bbox = draw.textbbox((180, row_top + 20), username, font=username_font)
            username_w = bbox[2] - bbox[0]
            draw.text((180 + username_w + 10, row_top + 23), f"•  {trainer_name}", fill=(148, 163, 184, 255), font=details_font)
        
        # 4. Stat (Right-aligned)
        fans = row.get("cumulative_fans", 0)
        stat_str = f"{format_fans(fans)} fans"
        stat_bbox = draw.textbbox((0, 0), stat_str, font=stat_font)
        stat_w = stat_bbox[2] - stat_bbox[0]
        draw.text((img_width - 40 - stat_w, row_top + 20), stat_str, fill=(255, 255, 255, 255), font=stat_font)
        
        # Row divider (fine bottom border)
        if idx < num_rows - 1:
            draw.line((40, row_top + row_height, img_width - 40, row_top + row_height), fill=(30, 41, 59, 255), width=1)

    # Render Footer
    footer_y = img_height - footer_height + 10
    draw.line((40, footer_y - 10, img_width - 40, footer_y - 10), fill=(51, 65, 85, 255), width=1)
    draw.text((40, footer_y), "UmaCore Trainer Tracker • Dynamic Rankings", fill=(100, 116, 139, 255), font=footer_font) # Slate-500
    
    # Save image to bytes (using WebP compression for 10x smaller file size and instant upload)
    buffer = io.BytesIO()
    img.save(buffer, format="WEBP", quality=85)
    return buffer.getvalue()
