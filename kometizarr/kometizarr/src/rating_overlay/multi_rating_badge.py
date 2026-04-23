"""
Multi-Rating Badge Generator - Create Kometa-style rating overlays with multiple sources

Supports TMDB, IMDb, Rotten Tomatoes ratings with logos, plus VideoManager quality
score (vmgr_score) and 4K resolution chip (resolution_4k).
MIT License - Copyright (c) 2026 Kometizarr Contributors
"""

import numpy as np
from collections import deque
from PIL import Image, ImageDraw, ImageFont
from typing import Tuple, Dict, Optional, List, Any
from pathlib import Path


class MultiRatingBadge:
    """Generate rating badges with multiple sources (TMDB, IMDb, RT, VMGR, 4K)"""

    # Custom badge sources that are not powered by rating APIs
    CUSTOM_SOURCES = {'vmgr_score', 'resolution_4k'}

    # Color for the "VM" text label in the logo area of the vmgr_score badge
    VMGR_LABEL_COLOR = (0, 200, 220, 255)   # Cyan-teal

    # Background colour for the 4K chip (vivid blue)
    UHD_BADGE_BG = (0, 100, 220, 200)       # Semi-transparent blue

    # Font family to file path mapping
    FONT_PATHS = {
        'DejaVu Sans Bold': '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        'DejaVu Sans': '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        'DejaVu Sans Bold Oblique': '/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf',
        'DejaVu Sans Oblique': '/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf',
        'DejaVu Serif Bold': '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf',
        'DejaVu Serif': '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf',
        'DejaVu Serif Bold Italic': '/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf',
        'DejaVu Serif Italic': '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf',
        'DejaVu Sans Mono Bold': '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf',
        'DejaVu Sans Mono': '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
        'DejaVu Sans Mono Oblique': '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Oblique.ttf',
    }

    def __init__(self, assets_dir: str = None):
        """
        Initialize multi-rating badge generator

        Args:
            assets_dir: Path to assets directory with logos
        """
        if assets_dir:
            self.assets_dir = Path(assets_dir)
        else:
            # Try Docker mount path first, fall back to local development path
            docker_path = Path('/app/kometizarr/assets/logos')
            if docker_path.exists():
                self.assets_dir = docker_path
            else:
                # Local development - relative to this file
                self.assets_dir = Path(__file__).parent.parent.parent / 'assets' / 'logos'

        # Load logos
        self.logos = self._load_logos()

    def _load_logos(self) -> Dict[str, Optional[Image.Image]]:
        """Load rating source logos"""
        logos = {}

        logo_files = {
            'tmdb': 'tmdb.png',
            'imdb': 'imdb.png',
            'rt_fresh': 'rt_fresh.png',
            'rt_rotten': 'rt_rotten.png',
            'rt_audience_fresh': 'rt_audience_fresh.png',
            'rt_audience_rotten': 'rt_audience_rotten.png',
            'vmgr': 'vmgr.png',
            'quality_notthere': 'quality_notthere.png',
            'quality_average':  'quality_average.png',
            'quality_approved': 'quality_approved.png',
        }

        for source, filename in logo_files.items():
            logo_path = self.assets_dir / filename
            if logo_path.exists():
                try:
                    img = Image.open(logo_path).convert('RGBA')
                    logos[source] = self._strip_background(img)
                except Exception as e:
                    print(f"Failed to load {source} logo: {e}")
                    logos[source] = None
            else:
                logos[source] = None

        return logos

    def _draw_text_with_shadow(
        self,
        draw: ImageDraw.Draw,
        position: Tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont,
        color: Tuple[int, int, int, int],
        shadow_offset: int = 6,
        anchor: str = "lm",
        stroke_width: int = None
    ):
        """Draw text with drop shadow for better visibility"""
        x, y = position

        # Auto-scale stroke width if not provided
        if stroke_width is None:
            stroke_width = max(2, shadow_offset // 2)

        # Draw shadow (slightly offset, darker)
        draw.text(
            (x + shadow_offset, y + shadow_offset),
            text,
            font=font,
            fill=(0, 0, 0, 200),  # Dark shadow
            anchor=anchor,
            stroke_width=stroke_width + 1,
            stroke_fill=(0, 0, 0, 255)
        )

        # Draw main text
        draw.text(
            (x, y),
            text,
            font=font,
            fill=color,
            anchor=anchor,
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 200)  # Outline for extra visibility
        )

    def _strip_background(self, img: Image.Image) -> Image.Image:
        """
        Remove the connected opaque light background from a logo PNG.

        Seeds the BFS from every pixel on the entire outer border (not just
        the 4 corners) so logos like rt_fresh — whose right/bottom borders are
        a mix of background-grey and logo-content — are stripped completely.

        Any pixel that is:
          • fully or mostly opaque  (alpha > 200)
          • light in colour         (R > 180 AND G > 180 AND B > 180)
          • 4-connected to the border region
        is made fully transparent.  Interior light pixels not reachable from
        the border are preserved (e.g. white text inside a logo).

        If no border pixel qualifies the image is returned unchanged
        (logos that already have a transparent background are untouched).
        """
        arr = np.array(img, dtype=np.uint8)   # H × W × 4
        h, w = arr.shape[:2]

        def is_bg(y: int, x: int) -> bool:
            r, g, b, a = int(arr[y, x, 0]), int(arr[y, x, 1]), int(arr[y, x, 2]), int(arr[y, x, 3])
            return a > 200 and r > 180 and g > 180 and b > 180

        # Seed from the full border, not just 4 corners
        border = (
            [(0, x) for x in range(w)] +
            [(h - 1, x) for x in range(w)] +
            [(y, 0) for y in range(1, h - 1)] +
            [(y, w - 1) for y in range(1, h - 1)]
        )
        seeds = [(y, x) for y, x in border if is_bg(y, x)]
        if not seeds:
            return img

        visited = np.zeros((h, w), dtype=bool)
        queue: deque = deque()
        for s in seeds:
            if not visited[s]:
                visited[s] = True
                queue.append(s)

        while queue:
            y, x = queue.popleft()
            arr[y, x, 3] = 0  # make transparent
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and is_bg(ny, nx):
                    visited[ny, nx] = True
                    queue.append((ny, nx))

        return Image.fromarray(arr, 'RGBA')

    def _resize_logo(self, logo: Image.Image, size: Tuple[int, int]) -> Image.Image:
        """
        Resize an RGBA logo using premultiplied-alpha so no colour fringe appears.

        PIL's LANCZOS resamples every channel independently.  Transparent pixels
        often store a colour (white, black, …) in their RGB even though alpha=0
        makes them invisible.  When the kernel mixes those invisible-but-coloured
        pixels with opaque neighbours it manufactures semi-transparent edge pixels
        whose colour is tinted by that stored RGB, producing a halo.

        Premultiplied-alpha resize:
          1. Multiply every R/G/B value by alpha/255 so transparent pixels become
             (0,0,0) and contribute nothing to neighbouring samples.
          2. Resize.
          3. Divide R/G/B back by the resized alpha (straight-alpha restore).
        Result: opaque pixels keep their exact colour; alpha=0 pixels contribute
        nothing; edge pixels fade cleanly with the correct colour.
        """
        arr = np.array(logo, dtype=np.float32)       # H × W × 4
        a = arr[:, :, 3] / 255.0
        arr[:, :, 0] *= a
        arr[:, :, 1] *= a
        arr[:, :, 2] *= a
        premult = Image.fromarray(arr.clip(0, 255).astype(np.uint8), 'RGBA')
        resized = premult.resize(size, Image.Resampling.LANCZOS)
        arr2 = np.array(resized, dtype=np.float32)
        a2 = arr2[:, :, 3] / 255.0
        # Safe un-premultiply: avoid divide-by-zero for fully-transparent pixels
        safe_a2 = np.where(a2 > 0, a2, 1.0)
        arr2[:, :, 0] = np.where(a2 > 0, arr2[:, :, 0] / safe_a2, 0)
        arr2[:, :, 1] = np.where(a2 > 0, arr2[:, :, 1] / safe_a2, 0)
        arr2[:, :, 2] = np.where(a2 > 0, arr2[:, :, 2] / safe_a2, 0)
        return Image.fromarray(arr2.clip(0, 255).astype(np.uint8), 'RGBA')

    def create_multi_rating_badge(
        self,
        ratings: Dict[str, float],
        poster_size: Tuple[int, int],
        position: str = 'northeast',
        badge_style: Optional[Dict[str, Any]] = None
    ) -> Image.Image:
        """
        Create a badge with multiple rating sources

        Args:
            ratings: Dict like {'tmdb': 7.2, 'imdb': 7.5, 'rt': 85}
            poster_size: (width, height) of poster
            position: Badge position
            badge_style: Optional styling options (badge_width_percent, font_size_multiplier, rating_color, background_opacity)

        Returns:
            PIL Image with transparent background
        """
        poster_width, poster_height = poster_size

        # Apply custom styling or use defaults
        style = badge_style or {}
        badge_width_percent = style.get('badge_width_percent', 35) / 100  # Convert percentage to decimal
        font_multiplier = style.get('font_size_multiplier', 1.0)
        rating_color_hex = style.get('rating_color', '#FFD700')  # Gold
        background_opacity = style.get('background_opacity', 128)

        # Convert hex color to RGB tuple
        rating_color = tuple(int(rating_color_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + (255,)

        # Badge size scales with poster width (customizable)
        badge_width = int(poster_width * badge_width_percent)

        # Calculate height based on number of ratings
        # Scale row height proportionally with badge width
        num_ratings = len(ratings)
        row_height = int(badge_width * 0.27)  # Proportional to width
        padding = int(badge_width * 0.03)
        badge_height = (num_ratings * row_height) + (padding * 2)

        # Create badge with transparent background
        badge = Image.new('RGBA', (badge_width, badge_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(badge)

        # Draw semi-transparent black rounded rectangle background
        corner_radius = int(badge_width * 0.05)  # 5% of badge width
        draw.rounded_rectangle(
            [(0, 0), (badge_width, badge_height)],
            radius=corner_radius,
            fill=(0, 0, 0, background_opacity)  # Customizable opacity
        )

        # Load fonts - scale with badge size and custom multiplier
        font_large_size = int(badge_width * 0.20 * font_multiplier)  # 20% of badge width * multiplier
        font_small_size = int(badge_width * 0.10 * font_multiplier)  # 10% of badge width * multiplier

        # Use custom font family if specified (unified badge mode)
        font_family = style.get('font_family', 'DejaVu Sans Bold')
        font_path = self.FONT_PATHS.get(font_family, self.FONT_PATHS['DejaVu Sans Bold'])

        try:
            font_large = ImageFont.truetype(font_path, font_large_size)
            # Use regular for small text
            font_small = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_small_size
            )
        except:
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

        # Draw each rating
        y_offset = padding
        for source, rating in ratings.items():
            self._draw_rating_row(
                badge, draw, source, rating,
                y_offset, badge_width, row_height,
                font_large, font_small, badge_width,  # Pass badge_width for scaling
                rating_color  # Pass custom rating color
            )
            y_offset += row_height

        return badge

    def create_individual_badge(
        self,
        source: str,
        rating: float,
        poster_size: Tuple[int, int],
        badge_style: Optional[Dict[str, Any]] = None
    ) -> Image.Image:
        """
        Create a single compact badge with logo on top, rating underneath.

        Handles standard rating sources (tmdb, imdb, rt_critic, rt_audience)
        as well as custom sources (vmgr_score, resolution_4k).

        Args:
            source: Rating source ('tmdb', 'imdb', 'rt_critic', 'rt_audience',
                    'vmgr_score', 'resolution_4k')
            rating: Rating value (ignored for resolution_4k)
            poster_size: (width, height) of poster for scaling
            badge_style: Optional styling options

        Returns:
            PIL Image with transparent background
        """
        # Dispatch to specialised renderers for custom badge types
        if source == 'vmgr_score':
            return self._create_vmgr_score_badge(rating, poster_size, badge_style)
        if source == 'resolution_4k':
            return self._create_4k_chip(poster_size, badge_style)

        poster_width, poster_height = poster_size

        # Apply custom styling or use defaults
        style = badge_style or {}
        badge_size_percent = style.get('individual_badge_size', 12) / 100  # 12% of poster width by default
        font_multiplier = style.get('font_size_multiplier', 1.0)
        logo_multiplier = style.get('logo_size_multiplier', 1.0)
        rating_color_hex = style.get('rating_color', '#FFD700')  # Gold
        background_opacity = style.get('background_opacity', 128)

        # Per-source overrides dict
        source_colors = style.get('source_colors') or {}
        source_va_overrides = style.get('source_text_va') or {}       # per-source label VA
        source_logo_x_offsets = style.get('source_logo_x_offset') or {}  # per-source logo X%
        source_logo_sizes = style.get('source_logo_size') or {}           # per-source logo size multiplier

        # text_va: per-source override > global slider (both 0-100)
        global_text_va = style.get('text_vertical_align', 50)
        text_va = source_va_overrides.get(source, global_text_va) / 100
        # Mapping: slider [0,100] → effective_va [-0.6, 1.0]
        # 0% → text just above center (close to logo), 50% → centered, 100% → near bottom
        effective_text_va = -0.60 + text_va * 1.60  # linear map

        # Per-source color override (falls back to global rating_color if not set)
        source_color_hex = source_colors.get(source) or rating_color_hex

        # Convert hex color to RGB tuple
        rating_color = tuple(int(source_color_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + (255,)

        # Badge size - compact square-ish badge
        badge_width = int(poster_width * badge_size_percent)
        badge_height = int(badge_width * 1.4)  # Slightly taller than wide (logo + number)

        # Create badge with transparent background
        badge = Image.new('RGBA', (badge_width, badge_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(badge)

        # Draw semi-transparent black rounded rectangle background
        corner_radius = int(badge_width * 0.1)  # 10% of badge width
        draw.rounded_rectangle(
            [(0, 0), (badge_width, badge_height)],
            radius=corner_radius,
            fill=(0, 0, 0, background_opacity)
        )

        # For RT scores, dynamically select logo based on score
        logo_key = source
        if source == 'rt_critic':
            logo_key = 'rt_fresh' if rating >= 60 else 'rt_rotten'
        elif source == 'rt_audience':
            logo_key = 'rt_audience_fresh' if rating >= 60 else 'rt_audience_rotten'

        # Draw logo in top 60% of badge
        logo = self.logos.get(logo_key)
        logo_section_height = int(badge_height * 0.6)
        padding = int(badge_width * 0.1)

        if logo:
            # RT logos are bold graphic icons that appear much larger than TMDB/IMDb wordmarks
            # at the same pixel size — normalize so they feel visually equal at 1x
            LOGO_BASE_SCALE = {
                'tmdb': 1.00,
                'imdb': 1.00,
                'rt_fresh': 0.72,
                'rt_rotten': 0.72,
                'rt_audience_fresh': 0.72,
                'rt_audience_rotten': 0.72,
            }
            base_scale = LOGO_BASE_SCALE.get(logo_key, 1.0)
            # Calculate logo size to fit in top section, scaled by per-source or global logo_size_multiplier.
            # Hard-cap to logo_section_height so logo_y never goes negative (negative paste
            # coords silently clip the top of the image in PIL).
            src_logo_mult = source_logo_sizes.get(source, logo_multiplier)
            max_logo_size = int(min(badge_width - (padding * 2), logo_section_height - padding) * src_logo_mult * base_scale)
            max_logo_size = min(max_logo_size, logo_section_height)

            # Resize logo maintaining aspect ratio
            orig_width, orig_height = logo.size
            aspect_ratio = orig_width / orig_height

            if aspect_ratio > 1:
                # Wider than tall
                logo_width = max_logo_size
                logo_height = int(max_logo_size / aspect_ratio)
            else:
                # Taller than wide or square
                logo_height = max_logo_size
                logo_width = int(max_logo_size * aspect_ratio)

            logo_resized = self._resize_logo(logo, (logo_width, logo_height))

            # Center logo horizontally, then apply per-source X offset (% of badge width)
            logo_x_pct = source_logo_x_offsets.get(source, 0)  # -50..+50
            logo_x = (badge_width - logo_width) // 2 + int(badge_width * logo_x_pct / 100)
            logo_y = (logo_section_height - logo_height) // 2

            logo_layer = Image.new('RGBA', badge.size, (0, 0, 0, 0))
            logo_layer.paste(logo_resized, (logo_x, logo_y))
            # Copy result back in-place so the existing `draw` reference stays valid
            badge.paste(Image.alpha_composite(badge, logo_layer))

        # Draw rating in bottom 40% of badge
        number_section_top = logo_section_height
        number_section_height = badge_height - logo_section_height

        # Load font - use custom font family if specified
        font_size = int(badge_width * 0.35 * font_multiplier)  # 35% of badge width
        font_family = style.get('font_family', 'DejaVu Sans Bold')
        font_path = self.FONT_PATHS.get(font_family, self.FONT_PATHS['DejaVu Sans Bold'])

        try:
            font_rating = ImageFont.truetype(font_path, font_size)
            # Use regular variant for percent symbol (always DejaVu Sans for consistency)
            font_percent = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", int(font_size * 0.6)
            )
        except:
            font_rating = ImageFont.load_default()
            font_percent = ImageFont.load_default()

        # Format rating
        if source in ['rt_critic', 'rt_audience']:
            rating_text = f"{int(rating)}"
            percent_text = "%"
        else:
            rating_text = f"{rating:.1f}"
            percent_text = ""

        # Center position in bottom section
        center_x = badge_width // 2
        # Use effective_text_va over the full badge height for a wider positional range
        center_y = int(badge_height * (0.6 + 0.4 * effective_text_va))

        # Calculate total text width if there's a percent sign
        if percent_text:
            rating_bbox = draw.textbbox((0, 0), rating_text, font=font_rating)
            percent_bbox = draw.textbbox((0, 0), percent_text, font=font_percent)
            total_width = (rating_bbox[2] - rating_bbox[0]) + (percent_bbox[2] - percent_bbox[0]) + 2

            # Draw number (left side)
            self._draw_text_with_shadow(
                draw,
                (center_x - total_width // 2, center_y),
                rating_text,
                font_rating,
                rating_color,
                shadow_offset=max(2, int(badge_width * 0.02)),
                anchor="lm"
            )

            # Draw % (right side)
            self._draw_text_with_shadow(
                draw,
                (center_x + total_width // 2 - (percent_bbox[2] - percent_bbox[0]), center_y + int(font_size * 0.1)),
                percent_text,
                font_percent,
                (255, 255, 255, 255),
                shadow_offset=max(1, int(badge_width * 0.01)),
                anchor="lm"
            )
        else:
            # Just center the number
            self._draw_text_with_shadow(
                draw,
                (center_x, center_y),
                rating_text,
                font_rating,
                rating_color,
                shadow_offset=max(2, int(badge_width * 0.02)),
                anchor="mm"  # Middle-middle anchor
            )

        return badge

    # ------------------------------------------------------------------
    # Custom badge renderers
    # ------------------------------------------------------------------

    def _create_vmgr_score_badge(
        self,
        score: float,
        poster_size: Tuple[int, int],
        badge_style: Optional[Dict[str, Any]] = None
    ) -> Image.Image:
        """
        Badge showing the VideoManager quality score (0–10).
        Top section: VM logo image (falls back to 'VM' text if logo not found).
        Bottom section: score value colour-coded green/orange/red.
        """
        poster_width, _ = poster_size
        style = badge_style or {}
        badge_size_percent = style.get('individual_badge_size', 12) / 100
        font_multiplier = style.get('font_size_multiplier', 1.0)
        logo_multiplier = style.get('logo_size_multiplier', 1.0)
        background_opacity = style.get('background_opacity', 128)
        source_colors = style.get('source_colors') or {}
        source_va_overrides = style.get('source_text_va') or {}
        source_logo_x_offsets = style.get('source_logo_x_offset') or {}
        source_logo_sizes = style.get('source_logo_size') or {}
        override_color_hex = source_colors.get('vmgr_score')
        global_text_va = style.get('text_vertical_align', 50)
        text_va = source_va_overrides.get('vmgr_score', global_text_va) / 100
        effective_text_va = -0.60 + text_va * 1.60  # same extended range as standard badges

        badge_width = int(poster_width * badge_size_percent)
        badge_height = int(badge_width * 1.4)

        badge = Image.new('RGBA', (badge_width, badge_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(badge)

        corner_radius = int(badge_width * 0.1)
        draw.rounded_rectangle(
            [(0, 0), (badge_width, badge_height)],
            radius=corner_radius,
            fill=(0, 0, 0, background_opacity)
        )

        # ---- Top section: quality logo (switches on score) or fallback text ----
        font_path = self.FONT_PATHS.get(
            style.get('font_family', 'DejaVu Sans Bold'),
            self.FONT_PATHS['DejaVu Sans Bold']
        )
        logo_section_height = int(badge_height * 0.55)
        # Pick logo by score threshold: quality_notthere < 5, quality_average 5-7.9, quality_approved >= 8
        # Fall back to 'vmgr' generic logo, then None.
        if score >= 8 and self.logos.get('quality_approved'):
            vmgr_logo = self.logos['quality_approved']
        elif score >= 5 and self.logos.get('quality_average'):
            vmgr_logo = self.logos['quality_average']
        elif score < 5 and self.logos.get('quality_notthere'):
            vmgr_logo = self.logos['quality_notthere']
        else:
            vmgr_logo = self.logos.get('vmgr')
        if vmgr_logo:
            padding = int(badge_width * 0.1)
            # Hard-cap to logo_section_height so ly never goes negative.
            src_logo_mult = source_logo_sizes.get('vmgr_score', logo_multiplier)
            max_size = int((min(badge_width - padding * 2, logo_section_height - padding)) * src_logo_mult)
            max_size = min(max_size, logo_section_height)
            lw, lh = vmgr_logo.size
            ar = lw / lh
            if ar >= 1:
                logo_w = max_size
                logo_h = int(max_size / ar)
            else:
                logo_h = max_size
                logo_w = int(max_size * ar)
            logo_resized = self._resize_logo(vmgr_logo, (logo_w, logo_h))
            lx_offset = source_logo_x_offsets.get('vmgr_score', 0)  # -50..+50 % of badge width
            lx = (badge_width - logo_w) // 2 + int(badge_width * lx_offset / 100)
            ly = (logo_section_height - logo_h) // 2
            logo_layer = Image.new('RGBA', badge.size, (0, 0, 0, 0))
            logo_layer.paste(logo_resized, (lx, ly))
            # Copy result back in-place so the existing `draw` reference stays valid
            badge.paste(Image.alpha_composite(badge, logo_layer))
        else:
            # Fallback: draw 'VM' text in cyan
            label_font_size = int(badge_width * 0.30 * font_multiplier)
            try:
                label_font = ImageFont.truetype(font_path, label_font_size)
            except Exception:
                label_font = ImageFont.load_default()
            self._draw_text_with_shadow(
                draw,
                (badge_width // 2, logo_section_height // 2),
                'VM',
                label_font,
                self.VMGR_LABEL_COLOR,
                shadow_offset=max(1, int(badge_width * 0.02)),
                anchor='mm'
            )

        # ---- Bottom section: score value colour-coded ----
        if override_color_hex:
            # User-defined per-source color overrides the automatic green/orange/red scale
            score_color = tuple(int(override_color_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + (255,)
        elif score >= 8:
            score_color = (100, 220, 100, 255)   # green
        elif score >= 5:
            score_color = (230, 165, 60, 255)    # orange
        else:
            score_color = (240, 90, 90, 255)     # red

        number_section_top = logo_section_height
        number_section_height = badge_height - logo_section_height
        center_x = badge_width // 2
        center_y = int(badge_height * (0.6 + 0.4 * effective_text_va))

        score_font_size = int(badge_width * 0.34 * font_multiplier)
        try:
            score_font = ImageFont.truetype(font_path, score_font_size)
        except Exception:
            score_font = ImageFont.load_default()

        self._draw_text_with_shadow(
            draw,
            (center_x, center_y),
            f'{score:.1f}',
            score_font,
            score_color,
            shadow_offset=max(2, int(badge_width * 0.02)),
            anchor='mm'
        )

        return badge

    def _create_4k_chip(
        self,
        poster_size: Tuple[int, int],
        badge_style: Optional[Dict[str, Any]] = None
    ) -> Image.Image:
        """
        A flat chip displaying '4K' in bold white text on a vivid blue background.
        Wider than it is tall to resemble a classic resolution badge.
        """
        poster_width, _ = poster_size
        style = badge_style or {}
        badge_size_percent = style.get('individual_badge_size', 12) / 100
        font_multiplier = style.get('font_size_multiplier', 1.0)
        source_colors = style.get('source_colors') or {}
        text_color_hex = source_colors.get('resolution_4k')
        text_color = (
            tuple(int(text_color_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + (255,)
            if text_color_hex else (255, 255, 255, 255)
        )

        chip_width = int(poster_width * badge_size_percent)
        chip_height = int(chip_width * 0.65)   # Wide and flat

        chip = Image.new('RGBA', (chip_width, chip_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(chip)

        # Background color with reduced opacity (120/255 ≈ 47%) and narrower left margin
        bg_left = int(chip_width * 0.08)   # small left inset so bg doesn't bleed left
        corner_radius = int(chip_height * 0.30)
        draw.rounded_rectangle(
            [(bg_left, 0), (chip_width, chip_height)],
            radius=corner_radius,
            fill=(self.UHD_BADGE_BG[0], self.UHD_BADGE_BG[1], self.UHD_BADGE_BG[2], 120)
        )

        font_size = int(chip_height * 0.65 * font_multiplier)
        font_path = self.FONT_PATHS.get(
            style.get('font_family', 'DejaVu Sans Bold'),
            self.FONT_PATHS['DejaVu Sans Bold']
        )
        try:
            font = ImageFont.truetype(font_path, font_size)
        except Exception:
            font = ImageFont.load_default()

        self._draw_text_with_shadow(
            draw,
            (chip_width // 2, chip_height // 2),
            '4K',
            font,
            text_color,
            shadow_offset=max(2, int(chip_width * 0.03)),
            anchor='mm'
        )

        return chip

    # ------------------------------------------------------------------

    def _draw_rating_row(
        self,
        badge: Image.Image,
        draw: ImageDraw.Draw,
        source: str,
        rating: float,
        y_offset: int,
        badge_width: int,
        row_height: int,
        font_large: ImageFont.FreeTypeFont,
        font_small: ImageFont.FreeTypeFont,
        scale_width: int,  # Badge width for scaling
        rating_color: Tuple[int, int, int, int] = (255, 215, 0, 255)  # Default gold
    ):
        """Draw a single rating row with logo and score"""
        x_padding = int(scale_width * 0.03)  # Scale padding

        # For RT scores, dynamically select logo based on score AND source
        logo_key = source
        if source in ['rt', 'rt_critic']:
            # RT Critic uses tomato logos
            if rating >= 60:
                logo_key = 'rt_fresh'
            else:
                logo_key = 'rt_rotten'
        elif source == 'rt_audience':
            # RT Audience uses popcorn logos
            if rating >= 60:
                logo_key = 'rt_audience_fresh'
            else:
                logo_key = 'rt_audience_rotten'

        # Draw logo - scale with badge size for consistency
        logo = self.logos.get(logo_key)
        max_logo_width = int(scale_width * 0.40)   # 40% of badge width max
        max_logo_height = int(scale_width * 0.20)  # 20% of badge width max

        # Make RT audience logos bigger (popcorn has more negative space)
        if source == 'rt_audience':
            # Spilled popcorn (rotten) needs to be bigger, standing (fresh) slightly bigger
            if logo_key == 'rt_audience_rotten':
                max_logo_width = int(max_logo_width * 1.3)
                max_logo_height = int(max_logo_height * 1.3)
            else:  # rt_audience_fresh
                max_logo_width = int(max_logo_width * 1.2)
                max_logo_height = int(max_logo_height * 1.2)

        if logo:
            # Calculate resize keeping aspect ratio
            orig_width, orig_height = logo.size
            aspect_ratio = orig_width / orig_height

            # Fit within max dimensions while maintaining aspect ratio
            if aspect_ratio > (max_logo_width / max_logo_height):
                # Width is the limiting factor
                logo_width = max_logo_width
                logo_height = int(max_logo_width / aspect_ratio)
            else:
                # Height is the limiting factor
                logo_height = max_logo_height
                logo_width = int(max_logo_height * aspect_ratio)

            # Resize logo maintaining aspect ratio (premultiplied-alpha to avoid white fringe)
            logo_resized = self._resize_logo(logo, (logo_width, logo_height))

            # Left-align all logos for consistency (only center vertically).
            # Clamp so the logo never starts above the row's y_offset.
            logo_x = x_padding
            logo_y = max(y_offset, y_offset + (row_height - logo_height) // 2)

            logo_layer = Image.new('RGBA', badge.size, (0, 0, 0, 0))
            logo_layer.paste(logo_resized, (logo_x, logo_y))
            badge.paste(Image.alpha_composite(badge, logo_layer))
        else:
            # Fallback: draw source name if no logo
            self._draw_text_with_shadow(
                draw,
                (x_padding, y_offset + row_height // 2),
                source.upper(),
                font_small,
                (255, 255, 255, 255)
            )

        # Draw rating score with drop shadow (no background!)
        # Scale shadow based on badge width
        shadow_large = int(scale_width * 0.01)  # 1% of width
        shadow_small = int(scale_width * 0.005)  # 0.5% of width

        if source in ['rt', 'rt_critic', 'rt_audience']:
            # Rotten Tomatoes is percentage - split number and % symbol
            rating_number = f"{int(rating)}"
            percent_symbol = "%"

            # Position to align with TMDB/IMDb scores
            rating_x = int(badge_width * 0.80)  # 80% across badge for better alignment
            rating_y = y_offset + (row_height // 2)

            # Get text sizes for alignment
            number_bbox = draw.textbbox((0, 0), rating_number, font=font_large)
            percent_bbox = draw.textbbox((0, 0), percent_symbol, font=font_small)

            total_width = (number_bbox[2] - number_bbox[0]) + (percent_bbox[2] - percent_bbox[0]) + int(scale_width * 0.01)

            # Draw rating number with shadow (GOLD text, large)
            self._draw_text_with_shadow(
                draw,
                (rating_x - total_width, rating_y),
                rating_number,
                font_large,
                rating_color,  # Custom rating color
                shadow_offset=shadow_large,
                anchor="lm"
            )

            # Draw % symbol with shadow (WHITE text, small)
            self._draw_text_with_shadow(
                draw,
                (rating_x - (percent_bbox[2] - percent_bbox[0]), rating_y + int(scale_width * 0.02)),
                percent_symbol,
                font_small,
                (255, 255, 255, 255),  # White
                shadow_offset=shadow_small,
                anchor="lm"
            )
        else:
            # TMDB and IMDb - just show the number (cleaner design)
            rating_text = f"{rating:.1f}"

            # Position at right edge (align with RT percentages)
            rating_x = badge_width - x_padding
            rating_y = y_offset + (row_height // 2)

            # Get text size for right alignment
            rating_bbox = draw.textbbox((0, 0), rating_text, font=font_large)
            text_width = rating_bbox[2] - rating_bbox[0]

            # Draw rating number with shadow (GOLD text) - right aligned
            self._draw_text_with_shadow(
                draw,
                (rating_x - text_width, rating_y),
                rating_text,
                font_large,
                rating_color,  # Custom rating color
                shadow_offset=shadow_large,
                anchor="lm"
            )

    def apply_to_poster(
        self,
        poster_path: str,
        ratings: Dict[str, float],
        output_path: str,
        position: str = 'northeast',
        badge_style: Optional[Dict[str, Any]] = None,
        badge_positions: Optional[Dict[str, Dict[str, float]]] = None
    ) -> Image.Image:
        """
        Apply rating badge(s) to poster

        Supports two modes:
        1. Unified badge mode (legacy): Single badge with all ratings
        2. Individual badge mode (new): Separate badge for each rating source

        Args:
            poster_path: Path to poster image
            ratings: Dict of ratings {'tmdb': 7.2, 'imdb': 7.5, 'rt_critic': 85, 'rt_audience': 92}
            output_path: Output path
            position: Badge position for unified mode (legacy)
            badge_style: Optional styling options
            badge_positions: Optional dict for individual mode. Format:
                            {'tmdb': {'x': 5, 'y': 5}, 'imdb': {'x': 20, 'y': 5}, ...}
                            If source key exists, that badge is enabled at that position.
                            X/Y are percentages (0-100) of poster dimensions.

        Returns:
            PIL Image
        """
        # Open poster
        poster = Image.open(poster_path).convert('RGBA')
        poster_width, poster_height = poster.size

        # MODE 1: Individual badges (new 4-badge system)
        if badge_positions:
            for source, rating in ratings.items():
                # Check if this source is enabled (key exists in badge_positions)
                if source not in badge_positions:
                    continue

                pos = badge_positions[source]
                x_percent = pos.get('x', 5)
                y_percent = pos.get('y', 5)

                # Create individual badge
                badge = self.create_individual_badge(
                    source=source,
                    rating=rating,
                    poster_size=(poster_width, poster_height),
                    badge_style=badge_style
                )

                # Convert percentage to pixels
                badge_x = int((x_percent / 100) * poster_width)
                badge_y = int((y_percent / 100) * poster_height)

                # Composite badge onto poster using alpha_composite so poster
                # alpha stays 255 and convert('RGB') doesn't flatten against white
                badge_layer = Image.new('RGBA', poster.size, (0, 0, 0, 0))
                badge_layer.paste(badge, (badge_x, badge_y))
                poster = Image.alpha_composite(poster, badge_layer)

            # Save
            poster_rgb = poster.convert('RGB')
            poster_rgb.save(output_path, 'JPEG', quality=95)

            enabled_sources = ', '.join([f'{k.upper()}: {v}' for k, v in ratings.items() if k in badge_positions])
            print(f"✓ Applied individual rating badges: {output_path}")
            print(f"  Enabled badges: {enabled_sources}")

            return poster

        # MODE 2: Unified badge (legacy - backward compatible)
        else:
            # Create unified badge with all ratings
            badge = self.create_multi_rating_badge(
                ratings=ratings,
                poster_size=(poster_width, poster_height),
                position=position,
                badge_style=badge_style
            )

            badge_width, badge_height = badge.size

            # Calculate position - handle both string positions and dict coordinates
            if isinstance(position, dict):
                # Free positioning with percentage coordinates
                x_percent = position.get('x', 2)
                y_percent = position.get('y', 2)
                badge_x = int((x_percent / 100) * poster_width)
                badge_y = int((y_percent / 100) * poster_height)
            else:
                # Named corner positions (string)
                offset_x = int(poster_width * 0.02)  # 2% from edges (close to edge)
                offset_y = int(poster_height * 0.02)

                positions = {
                    'northeast': (poster_width - badge_width - offset_x, offset_y),
                    'northwest': (offset_x, offset_y),
                    'southeast': (poster_width - badge_width - offset_x, poster_height - badge_height - offset_y),
                    'southwest': (offset_x, poster_height - badge_height - offset_y)
                }

                badge_x, badge_y = positions.get(position, positions['northwest'])

            # Composite badge onto poster using alpha_composite so poster
            # alpha stays 255 and convert('RGB') doesn't flatten against white
            badge_layer = Image.new('RGBA', poster.size, (0, 0, 0, 0))
            badge_layer.paste(badge, (badge_x, badge_y))
            poster = Image.alpha_composite(poster, badge_layer)

            # Save
            poster_rgb = poster.convert('RGB')
            poster_rgb.save(output_path, 'JPEG', quality=95)

            print(f"✓ Applied multi-rating overlay: {output_path}")
            print(f"  Position: {position} ({badge_x}, {badge_y})")
            print(f"  Ratings: {', '.join([f'{k.upper()}: {v}' for k, v in ratings.items()])}")

            return poster
