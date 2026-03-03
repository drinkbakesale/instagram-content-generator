import os
import json
import base64
import textwrap
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

PROMPTS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts_config.json")

def load_prompt(key):
    """Load a specific prompt from config."""
    if os.path.exists(PROMPTS_FILE):
        with open(PROMPTS_FILE, 'r') as f:
            prompts = json.load(f)
            return prompts.get(key, {}).get('prompt', '')
    return ''


class TextOverlay:
    # Available templates for Instagram posts
    TEMPLATES = [
        "top_bar",          # Horizontal bar at top 20%
        "bottom_bar",       # Horizontal bar at bottom 20%
        "left_sidebar",     # Vertical sidebar on left 30%
        "center_circle",    # Circular overlay in center
        "full_text",        # Full image with gradient overlay and centered text
    ]

    def __init__(self):
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
        self.static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
        self.logo_path = os.path.join(self.static_dir, "project_ruth_logo.webp")
        os.makedirs(self.output_dir, exist_ok=True)

        # Brand colors (RGB tuples for Pillow)
        self.colors = {
            "white": (255, 255, 255),
            "off_white": (250, 250, 250),
            "light_gray": (245, 245, 245),
            "teal": (27, 77, 92),
            "dark_teal": (13, 59, 76),
            "warm_orange": (230, 126, 34),
            "black": (0, 0, 0),
            "brand_brown": (122, 57, 33),  # #7a3921
        }

        # Extended font paths for better quality text
        self.font_paths = [
            # macOS Premium fonts
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Futura.ttc",
            "/Library/Fonts/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/Library/Fonts/Arial.ttf",
            # Linux
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            # Windows
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]

    def get_font(self, size, bold=False):
        """Get a font with fallback support."""
        for path in self.font_paths:
            try:
                if os.path.exists(path):
                    return ImageFont.truetype(path, size=size)
            except Exception:
                continue
        # Fallback to default
        return ImageFont.load_default()

    def add_logo(self, img, text_position="top"):
        """Add Project Ruth logo - top right when text is top, bottom right when text is bottom."""
        if not os.path.exists(self.logo_path):
            print(f"Logo not found at {self.logo_path}")
            return img

        try:
            logo = Image.open(self.logo_path).convert("RGBA")
            img_width, img_height = img.size

            # Scale logo to ~20% of image width (larger)
            logo_target_width = int(img_width * 0.20)
            logo_aspect = logo.height / logo.width
            logo_target_height = int(logo_target_width * logo_aspect)
            logo = logo.resize((logo_target_width, logo_target_height), Image.Resampling.LANCZOS)

            # Recolor logo to white and orange
            logo = self.recolor_logo(logo)

            # Position based on text placement
            padding = int(img_width * 0.03)
            logo_x = img_width - logo_target_width - padding

            if text_position == "top":
                # Logo in top right, inside the text bar area
                logo_y = padding
            else:
                # Logo in bottom right
                logo_y = img_height - logo_target_height - padding

            # Composite logo onto image
            img.paste(logo, (logo_x, logo_y), logo)
            return img
        except Exception as e:
            print(f"Error adding logo: {e}")
            return img

    def recolor_logo(self, logo):
        """Recolor logo to white text with orange accent."""
        # Convert to RGBA if not already
        logo = logo.convert("RGBA")
        pixels = logo.load()
        width, height = logo.size

        # Orange color for accent: #E67E22
        orange = (230, 126, 34)
        white = (255, 255, 255)

        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]
                if a > 50:  # Only modify non-transparent pixels
                    # Calculate luminance
                    lum = (r * 0.299 + g * 0.587 + b * 0.114)
                    if lum < 100:
                        # Dark pixels (text) -> white
                        pixels[x, y] = (*white, a)
                    elif 50 < r < 200 and 30 < g < 150 and b < 100:
                        # Brownish/orange pixels -> bright orange
                        pixels[x, y] = (*orange, a)
                    else:
                        # Other dark/medium pixels -> white
                        pixels[x, y] = (*white, min(255, a + 50))

        return logo

    def get_text_placement_suggestion(self, image_path, headline, subheadline):
        """Use GPT-5.2 Vision to analyze image and provide detailed creative direction."""
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # Smart placement prompt - find lowest contrast zone avoiding all people/focal points
        enhanced_prompt = f"""Analyze this image to find the SAFEST zone for a text overlay bar.

The bar will cover 20% of the image height (either top 20% OR bottom 20%).

ANALYZE BOTH ZONES:
1. TOP 20%: What is there? Any faces, heads, hair, people, hands, focal points?
2. BOTTOM 20%: What is there? Any faces, heads, hair, people, hands, focal points?

ABSOLUTE RULES - The text bar must NEVER cover:
- Faces (even partially - no foreheads, eyes, noses, mouths, chins)
- Heads or hair
- Hands or arms
- Any part of a person's body
- The main focal point or subject of the image
- Important objects that tell the story

CHOOSE THE ZONE WITH:
- LOWEST contrast (most uniform colors, like plain walls, sky, solid backgrounds)
- LOWEST visual complexity (fewer details, textures, or objects)
- ZERO people or body parts

RETURN JSON:
{{
    "headline_position": "top" or "bottom",
    "headline_alignment": "center",
    "headline_color": "white",
    "subheadline_color": "white",
    "use_overlay": true,
    "overlay_opacity": 0.95,
    "headline_font_size": 0.055,
    "subheadline_font_size": 0.035,
    "text_effect": "clean",
    "top_zone_contents": "Describe what's in top 20%",
    "bottom_zone_contents": "Describe what's in bottom 20%",
    "reasoning": "Why you chose this zone (must mention what you're avoiding)"
}}

If BOTH zones contain people/faces, choose the one with LESS of the person visible."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-5.2",
                messages=[
                    {
                        "role": "system",
                        "content": """You are analyzing images to find the safest zone for text placement.

Your #1 PRIORITY: Never let text cover faces, heads, hands, or any part of people.

Look at the TOP 20% and BOTTOM 20% of the image. Describe what's in each zone, then pick the zone that has:
1. NO faces, heads, hair, hands, or body parts
2. The LOWEST contrast / most uniform background
3. The LEAST visual complexity

Output only valid JSON."""
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": enhanced_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{image_data}"}
                            }
                        ]
                    }
                ],
                max_completion_tokens=600
            )

            response_text = response.choices[0].message.content
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            if start != -1 and end > start:
                result = json.loads(response_text[start:end])
                print(f"AI Creative Direction: {json.dumps(result, indent=2)}")
                return result
        except Exception as e:
            print(f"Vision analysis failed: {e}")

        # Smart defaults - solid brown bar style
        return {
            "headline_position": "bottom",
            "headline_alignment": "center",
            "headline_color": "white",
            "subheadline_color": "white",
            "use_overlay": True,
            "overlay_color": "brand_brown",
            "overlay_opacity": 0.9,
            "add_logo": False,
            "headline_font_size": 0.07,
            "subheadline_font_size": 0.04,
            "text_shadow_strength": "none",
            "gradient_style": "solid_bar",
            "text_effect": "clean",
            "vertical_offset": 0,
            "reasoning": "Default placement at bottom"
        }

    def try_ai_image_edit(self, image_path, headline, subheadline, post_id):
        """
        Attempt to use AI image editing to add text overlay.
        This is experimental - AI image models may not render text perfectly.
        Returns None if it fails, so caller can fall back to programmatic rendering.
        """
        try:
            # Create a mask for the bottom third of the image where text will go
            img = Image.open(image_path)
            width, height = img.size

            # Create mask (transparent where we want to edit - bottom 35%)
            mask = Image.new("RGBA", (width, height), (0, 0, 0, 255))  # Black = keep
            mask_draw = ImageDraw.Draw(mask)
            # Make bottom portion transparent (white = edit)
            mask_draw.rectangle([0, int(height * 0.65), width, height], fill=(255, 255, 255, 255))

            # Save mask temporarily
            mask_path = os.path.join(self.output_dir, f"mask_{post_id}.png")
            mask.save(mask_path)

            # Prepare image as RGBA PNG
            img_rgba = img.convert("RGBA")
            img_bytes = BytesIO()
            img_rgba.save(img_bytes, format='PNG')
            img_bytes.seek(0)

            mask_bytes = BytesIO()
            mask.save(mask_bytes, format='PNG')
            mask_bytes.seek(0)

            # Use OpenAI image edit
            edit_prompt = f"""Add elegant text overlay to this social media image:
Headline (large, bold, white text with shadow): "{headline}"
Subheadline (smaller, white text below): "{subheadline}"
Place text in the bottom third with professional typography.
Add subtle gradient overlay for readability.
Keep brand mark "PROJECT RUTH" small in corner."""

            response = self.client.images.edit(
                model="dall-e-2",  # dall-e-2 supports editing
                image=img_bytes,
                mask=mask_bytes,
                prompt=edit_prompt,
                size="1024x1024",
                n=1
            )

            # Download result
            result_url = response.data[0].url
            result_response = requests.get(result_url)

            if result_response.status_code == 200:
                output_path = os.path.join(self.output_dir, f"post_{post_id}_ai_overlay.png")
                with open(output_path, "wb") as f:
                    f.write(result_response.content)

                # Clean up mask
                if os.path.exists(mask_path):
                    os.remove(mask_path)

                return output_path

        except Exception as e:
            print(f"AI image edit failed: {e}")
            # Clean up mask if it exists
            mask_path = os.path.join(self.output_dir, f"mask_{post_id}.png")
            if os.path.exists(mask_path):
                os.remove(mask_path)

        return None

    def wrap_text(self, text, font, max_width, draw):
        """Wrap text to fit within max_width."""
        words = text.split()
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]

        if current_line:
            lines.append(' '.join(current_line))

        return lines

    def calculate_font_size(self, text, max_width, max_height, draw, base_size, min_size=24):
        """Calculate optimal font size to fit text in given dimensions."""
        size = base_size
        while size > min_size:
            font = self.get_font(size)
            lines = self.wrap_text(text, font, max_width, draw)
            total_height = len(lines) * (size * 1.2)  # 1.2 line spacing

            if total_height <= max_height:
                # Check if any line is still too wide
                all_fit = True
                for line in lines:
                    bbox = draw.textbbox((0, 0), line, font=font)
                    if bbox[2] - bbox[0] > max_width:
                        all_fit = False
                        break
                if all_fit:
                    return size, font, lines

            size -= 2

        # Return minimum size
        font = self.get_font(min_size)
        lines = self.wrap_text(text, font, max_width, draw)
        return min_size, font, lines

    def draw_text_with_effects(self, draw, text, position, font, color, effects=None):
        """Draw text with professional effects (shadow, outline, glow)."""
        x, y = position
        effects = effects or {}

        # Convert hex color to RGB if needed
        if isinstance(color, str):
            color = self.colors.get(color, self.colors["white"])

        # Draw glow effect (soft shadow)
        if effects.get("glow", False):
            glow_color = (*self.colors["black"], 60)
            for offset in range(4, 0, -1):
                for dx in range(-offset, offset + 1):
                    for dy in range(-offset, offset + 1):
                        draw.text((x + dx, y + dy), text, font=font, fill=glow_color)

        # Draw outline
        if effects.get("outline", True):
            outline_color = self.colors["black"]
            outline_width = effects.get("outline_width", 2)
            for dx in range(-outline_width, outline_width + 1):
                for dy in range(-outline_width, outline_width + 1):
                    if dx != 0 or dy != 0:
                        draw.text((x + dx, y + dy), text, font=font, fill=(*outline_color, 180))

        # Draw drop shadow
        if effects.get("shadow", True):
            shadow_offset = effects.get("shadow_offset", 3)
            shadow_color = (*self.colors["black"], 120)
            draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow_color)

        # Draw main text
        draw.text((x, y), text, font=font, fill=(*color, 255))

    def create_gradient_overlay(self, width, height, position="bottom", color="dark", opacity=0.7, gradient_style="linear"):
        """Create a professional overlay for text readability.

        Args:
            gradient_style: "solid_bar" (recommended), "linear", "radial", or "none"
        """
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))

        if gradient_style == "none":
            return overlay

        if color == "dark" or color == "brand_brown":
            base_color = self.colors["brand_brown"]  # Use brand brown #7a3921
        else:
            base_color = self.colors["white"]

        # Solid bar style - clean, professional look with white border inset
        if gradient_style == "solid_bar":
            draw = ImageDraw.Draw(overlay)
            alpha = int(opacity * 255)

            # Border settings
            border_inset = int(min(width, height) * 0.02)  # 2% inset from bar edges
            border_width = max(2, int(min(width, height) * 0.003))  # Thin white border
            white_color = (255, 255, 255, 255)

            if position == "bottom":
                # Solid bar covering bottom 20%
                bar_top = int(height * 0.80)
                draw.rectangle([0, bar_top, width, height], fill=(*base_color, alpha))
                # White border inset
                draw.rectangle(
                    [border_inset, bar_top + border_inset, width - border_inset, height - border_inset],
                    outline=white_color, width=border_width
                )
            elif position == "top":
                # Solid bar covering top 20%
                bar_bottom = int(height * 0.20)
                draw.rectangle([0, 0, width, bar_bottom], fill=(*base_color, alpha))
                # White border inset
                draw.rectangle(
                    [border_inset, border_inset, width - border_inset, bar_bottom - border_inset],
                    outline=white_color, width=border_width
                )
            else:  # middle
                bar_top = int(height * 0.42)
                bar_bottom = int(height * 0.58)
                draw.rectangle([0, bar_top, width, bar_bottom], fill=(*base_color, alpha))
                # White border inset
                draw.rectangle(
                    [border_inset, bar_top + border_inset, width - border_inset, bar_bottom - border_inset],
                    outline=white_color, width=border_width
                )

            return overlay

        if gradient_style == "radial":
            # Radial gradient - darkest at edges, lighter toward center
            center_x, center_y = width // 2, height // 2
            max_dist = ((width/2)**2 + (height/2)**2) ** 0.5

            for i in range(height):
                for j in range(width):
                    dist = ((j - center_x)**2 + (i - center_y)**2) ** 0.5
                    # More opacity toward bottom
                    y_factor = i / height
                    radial_factor = dist / max_dist
                    combined = (radial_factor * 0.3 + y_factor * 0.7)
                    if combined > 0.4:
                        alpha = int(((combined - 0.4) / 0.6) ** 1.3 * opacity * 255)
                    else:
                        alpha = 0
                    overlay.putpixel((j, i), (*base_color, min(255, alpha)))
        else:
            # Linear gradient (default)
            for i in range(height):
                if position == "bottom":
                    # Gradient from transparent at top to opaque at bottom
                    progress = i / height
                    if progress < 0.5:
                        alpha = 0
                    else:
                        alpha = int(((progress - 0.5) * 2) ** 1.5 * opacity * 255)
                elif position == "top":
                    progress = 1 - (i / height)
                    if progress < 0.5:
                        alpha = 0
                    else:
                        alpha = int(((progress - 0.5) * 2) ** 1.5 * opacity * 255)
                else:  # middle
                    center = height / 2
                    distance = abs(i - center) / center
                    alpha = int((1 - distance) * opacity * 255)

                for j in range(width):
                    overlay.putpixel((j, i), (*base_color, alpha))

        return overlay

    # ========== TEMPLATE RENDERING METHODS ==========

    def render_top_bar(self, img, headline, subheadline, post_id):
        """Template: Horizontal bar at top 20% of image."""
        return self._render_horizontal_bar(img, headline, subheadline, post_id, position="top")

    def render_bottom_bar(self, img, headline, subheadline, post_id):
        """Template: Horizontal bar at bottom 20% of image."""
        return self._render_horizontal_bar(img, headline, subheadline, post_id, position="bottom")

    def _render_horizontal_bar(self, img, headline, subheadline, post_id, position="bottom"):
        """Shared logic for top_bar and bottom_bar templates."""
        width, height = img.size
        img = img.convert("RGBA")

        # Create overlay
        overlay = self.create_gradient_overlay(width, height, position, "brand_brown", 0.9, "solid_bar")
        img = Image.alpha_composite(img, overlay)

        # Create text layer
        text_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_layer)

        # Calculate text area with buffer from border
        border_inset = int(min(width, height) * 0.02)  # Match border inset
        text_buffer = int(min(width, height) * 0.025)  # Additional buffer from border
        margin_x = border_inset + text_buffer + int(width * 0.02)  # Total left margin
        margin_y = border_inset + text_buffer  # Total vertical margin from border
        max_text_width = width - (margin_x * 2) - int(width * 0.22)  # Leave space for logo

        if position == "bottom":
            bar_top = int(height * 0.80)
            text_area_top = bar_top + margin_y
            text_area_bottom = height - margin_y
        else:
            bar_bottom = int(height * 0.20)
            text_area_top = margin_y
            text_area_bottom = bar_bottom - margin_y

        text_area_height = text_area_bottom - text_area_top

        # Calculate font sizes
        headline_size, headline_font, headline_lines = self.calculate_font_size(
            headline, max_text_width, text_area_height * 0.6, draw, int(height * 0.055), min_size=28
        )
        subhead_size, subhead_font, subhead_lines = self.calculate_font_size(
            subheadline, max_text_width, text_area_height * 0.35, draw, int(height * 0.035), min_size=18
        )

        # Calculate vertical centering
        line_spacing_headline = headline_size * 1.15
        line_spacing_subhead = subhead_size * 1.2
        gap = int(height * 0.015)
        total_height = len(headline_lines) * line_spacing_headline + gap + len(subhead_lines) * line_spacing_subhead
        start_y = text_area_top + (text_area_height - total_height) // 2

        # Draw headline
        current_y = start_y
        for line in headline_lines:
            bbox = draw.textbbox((0, 0), line, font=headline_font)
            x = margin_x
            self.draw_text_with_effects(draw, line, (x, current_y), headline_font, self.colors["white"], {"shadow": True, "outline": False})
            current_y += line_spacing_headline

        current_y += gap

        # Draw subheadline
        for line in subhead_lines:
            self.draw_text_with_effects(draw, line, (margin_x, current_y), subhead_font, self.colors["white"], {"shadow": True, "outline": False})
            current_y += line_spacing_subhead

        final_img = Image.alpha_composite(img, text_layer)
        final_img = self.add_logo(final_img, text_position=position)
        return final_img

    def render_left_sidebar(self, img, headline, subheadline, post_id):
        """Template: Vertical sidebar on left 30% of image."""
        width, height = img.size
        img = img.convert("RGBA")

        # Create sidebar overlay
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw_overlay = ImageDraw.Draw(overlay)
        sidebar_width = int(width * 0.32)
        border_inset = int(min(width, height) * 0.02)
        border_width = max(2, int(min(width, height) * 0.003))

        # Draw sidebar background
        draw_overlay.rectangle([0, 0, sidebar_width, height], fill=(*self.colors["brand_brown"], 230))
        # White border inset
        draw_overlay.rectangle(
            [border_inset, border_inset, sidebar_width - border_inset, height - border_inset],
            outline=(255, 255, 255, 255), width=border_width
        )
        img = Image.alpha_composite(img, overlay)

        # Create text layer
        text_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_layer)

        # Text area within sidebar with buffer from border
        text_buffer = int(min(width, height) * 0.025)  # Buffer from border to text
        text_margin = border_inset + text_buffer
        text_width = sidebar_width - (text_margin * 2)
        text_area_top = border_inset + text_buffer + int(height * 0.08)
        text_area_bottom = height - border_inset - text_buffer - int(height * 0.15)  # Leave room for logo
        text_area_height = text_area_bottom - text_area_top

        # Calculate font sizes
        headline_size, headline_font, headline_lines = self.calculate_font_size(
            headline, text_width, text_area_height * 0.5, draw, int(height * 0.045), min_size=24
        )
        subhead_size, subhead_font, subhead_lines = self.calculate_font_size(
            subheadline, text_width, text_area_height * 0.35, draw, int(height * 0.028), min_size=16
        )

        # Draw text centered in sidebar
        line_spacing_headline = headline_size * 1.2
        line_spacing_subhead = subhead_size * 1.25
        gap = int(height * 0.03)
        total_height = len(headline_lines) * line_spacing_headline + gap + len(subhead_lines) * line_spacing_subhead
        current_y = text_area_top + (text_area_height - total_height) // 2

        for line in headline_lines:
            bbox = draw.textbbox((0, 0), line, font=headline_font)
            line_width = bbox[2] - bbox[0]
            x = (sidebar_width - line_width) // 2
            self.draw_text_with_effects(draw, line, (x, current_y), headline_font, self.colors["white"], {"shadow": True, "outline": False})
            current_y += line_spacing_headline

        current_y += gap

        for line in subhead_lines:
            bbox = draw.textbbox((0, 0), line, font=subhead_font)
            line_width = bbox[2] - bbox[0]
            x = (sidebar_width - line_width) // 2
            self.draw_text_with_effects(draw, line, (x, current_y), subhead_font, self.colors["off_white"], {"shadow": True, "outline": False})
            current_y += line_spacing_subhead

        final_img = Image.alpha_composite(img, text_layer)

        # Add logo at bottom of sidebar (inside border)
        if os.path.exists(self.logo_path):
            try:
                logo = Image.open(self.logo_path).convert("RGBA")
                logo_width = int(sidebar_width * 0.55)
                logo_aspect = logo.height / logo.width
                logo_height = int(logo_width * logo_aspect)
                logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
                logo = self.recolor_logo(logo)
                logo_x = (sidebar_width - logo_width) // 2
                logo_y = height - logo_height - border_inset - text_buffer
                final_img.paste(logo, (logo_x, logo_y), logo)
            except Exception as e:
                print(f"Logo error: {e}")

        return final_img

    def render_center_circle(self, img, headline, subheadline, post_id):
        """Template: Circular overlay in center of image."""
        width, height = img.size
        img = img.convert("RGBA")

        # Create circular overlay
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw_overlay = ImageDraw.Draw(overlay)

        # Circle parameters
        circle_radius = int(min(width, height) * 0.38)
        center_x, center_y = width // 2, height // 2

        # Draw filled circle with brand color
        draw_overlay.ellipse(
            [center_x - circle_radius, center_y - circle_radius,
             center_x + circle_radius, center_y + circle_radius],
            fill=(*self.colors["brand_brown"], 235)
        )
        # White border
        border_width = max(3, int(circle_radius * 0.02))
        border_inset = int(circle_radius * 0.08)  # Inset for border
        draw_overlay.ellipse(
            [center_x - circle_radius + border_inset, center_y - circle_radius + border_inset,
             center_x + circle_radius - border_inset, center_y + circle_radius - border_inset],
            outline=(255, 255, 255, 255), width=border_width
        )
        img = Image.alpha_composite(img, overlay)

        # Create text layer
        text_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_layer)

        # Text area within circle with buffer from border
        text_buffer = int(circle_radius * 0.15)  # Buffer from border to text
        text_width = int(circle_radius * 1.2)  # Slightly smaller for padding
        text_height = int(circle_radius * 0.9)  # Leave room for logo at bottom

        # Calculate font sizes
        headline_size, headline_font, headline_lines = self.calculate_font_size(
            headline, text_width, text_height * 0.5, draw, int(height * 0.05), min_size=24
        )
        subhead_size, subhead_font, subhead_lines = self.calculate_font_size(
            subheadline, text_width, text_height * 0.35, draw, int(height * 0.03), min_size=16
        )

        # Center text in circle (shifted up to leave room for logo)
        line_spacing_headline = headline_size * 1.15
        line_spacing_subhead = subhead_size * 1.2
        gap = int(height * 0.025)
        total_height = len(headline_lines) * line_spacing_headline + gap + len(subhead_lines) * line_spacing_subhead
        current_y = center_y - total_height // 2 - int(circle_radius * 0.1)  # Shift up for logo

        for line in headline_lines:
            bbox = draw.textbbox((0, 0), line, font=headline_font)
            line_width = bbox[2] - bbox[0]
            x = center_x - line_width // 2
            self.draw_text_with_effects(draw, line, (x, current_y), headline_font, self.colors["white"], {"shadow": True, "outline": False})
            current_y += line_spacing_headline

        current_y += gap

        for line in subhead_lines:
            bbox = draw.textbbox((0, 0), line, font=subhead_font)
            line_width = bbox[2] - bbox[0]
            x = center_x - line_width // 2
            self.draw_text_with_effects(draw, line, (x, current_y), subhead_font, self.colors["off_white"], {"shadow": True, "outline": False})
            current_y += line_spacing_subhead

        final_img = Image.alpha_composite(img, text_layer)

        # Add logo at bottom center of circle
        if os.path.exists(self.logo_path):
            try:
                logo = Image.open(self.logo_path).convert("RGBA")
                logo_width = int(circle_radius * 0.5)
                logo_aspect = logo.height / logo.width
                logo_height = int(logo_width * logo_aspect)
                logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
                logo = self.recolor_logo(logo)
                # Center horizontally, position at bottom of circle
                logo_x = center_x - logo_width // 2
                logo_y = center_y + circle_radius - logo_height - int(circle_radius * 0.15)
                final_img.paste(logo, (logo_x, logo_y), logo)
            except Exception as e:
                print(f"Logo error: {e}")
        return final_img

    def render_split_horizontal(self, img, headline, subheadline, post_id):
        """Template: Top 55% image, bottom 45% solid color with text."""
        width, height = img.size
        img = img.convert("RGBA")

        # Create split overlay - solid bottom section
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw_overlay = ImageDraw.Draw(overlay)
        split_y = int(height * 0.55)

        # Fill bottom section with brand color
        draw_overlay.rectangle([0, split_y, width, height], fill=(*self.colors["brand_brown"], 255))
        # White border at split line
        border_width = max(3, int(height * 0.004))
        draw_overlay.rectangle([0, split_y, width, split_y + border_width], fill=(255, 255, 255, 255))
        # Inset border in text area
        border_inset = int(min(width, height) * 0.025)
        draw_overlay.rectangle(
            [border_inset, split_y + border_inset + border_width, width - border_inset, height - border_inset],
            outline=(255, 255, 255, 255), width=max(2, border_width // 2)
        )
        img = Image.alpha_composite(img, overlay)

        # Create text layer
        text_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_layer)

        # Text area in bottom section
        margin_x = int(width * 0.06)
        text_area_top = split_y + int(height * 0.04)
        text_area_bottom = height - int(height * 0.04)
        text_area_height = text_area_bottom - text_area_top
        max_text_width = width - (margin_x * 2) - int(width * 0.22)  # Space for logo

        # Calculate font sizes
        headline_size, headline_font, headline_lines = self.calculate_font_size(
            headline, max_text_width, text_area_height * 0.55, draw, int(height * 0.055), min_size=26
        )
        subhead_size, subhead_font, subhead_lines = self.calculate_font_size(
            subheadline, max_text_width, text_area_height * 0.35, draw, int(height * 0.032), min_size=16
        )

        # Vertical centering
        line_spacing_headline = headline_size * 1.15
        line_spacing_subhead = subhead_size * 1.2
        gap = int(height * 0.02)
        total_height = len(headline_lines) * line_spacing_headline + gap + len(subhead_lines) * line_spacing_subhead
        current_y = text_area_top + (text_area_height - total_height) // 2

        for line in headline_lines:
            self.draw_text_with_effects(draw, line, (margin_x, current_y), headline_font, self.colors["white"], {"shadow": True, "outline": False})
            current_y += line_spacing_headline

        current_y += gap

        for line in subhead_lines:
            self.draw_text_with_effects(draw, line, (margin_x, current_y), subhead_font, self.colors["off_white"], {"shadow": True, "outline": False})
            current_y += line_spacing_subhead

        final_img = Image.alpha_composite(img, text_layer)
        # Logo in bottom right of text area
        final_img = self.add_logo(final_img, text_position="bottom")
        return final_img

    def render_full_text(self, img, headline, subheadline, post_id):
        """Template: Full image with radial gradient overlay and large centered text."""
        width, height = img.size
        img = img.convert("RGBA")

        # Create radial gradient overlay (darker at edges)
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        center_x, center_y = width // 2, height // 2
        max_dist = ((width/2)**2 + (height/2)**2) ** 0.5

        for y in range(height):
            for x in range(width):
                dist = ((x - center_x)**2 + (y - center_y)**2) ** 0.5
                factor = dist / max_dist
                alpha = int(factor * 0.65 * 255)  # Darker at edges
                overlay.putpixel((x, y), (*self.colors["brand_brown"], alpha))

        img = Image.alpha_composite(img, overlay)

        # Create text layer
        text_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_layer)

        # Large centered text
        margin = int(width * 0.1)
        max_text_width = width - (margin * 2)
        text_height = int(height * 0.5)

        # Calculate font sizes - larger for this template
        headline_size, headline_font, headline_lines = self.calculate_font_size(
            headline, max_text_width, text_height * 0.6, draw, int(height * 0.08), min_size=32
        )
        subhead_size, subhead_font, subhead_lines = self.calculate_font_size(
            subheadline, max_text_width, text_height * 0.3, draw, int(height * 0.04), min_size=18
        )

        # Center everything
        line_spacing_headline = headline_size * 1.15
        line_spacing_subhead = subhead_size * 1.2
        gap = int(height * 0.03)
        total_height = len(headline_lines) * line_spacing_headline + gap + len(subhead_lines) * line_spacing_subhead
        current_y = (height - total_height) // 2

        for line in headline_lines:
            bbox = draw.textbbox((0, 0), line, font=headline_font)
            line_width = bbox[2] - bbox[0]
            x = (width - line_width) // 2
            self.draw_text_with_effects(draw, line, (x, current_y), headline_font, self.colors["white"], {"shadow": True, "shadow_offset": 4, "outline": True, "outline_width": 2})
            current_y += line_spacing_headline

        current_y += gap

        for line in subhead_lines:
            bbox = draw.textbbox((0, 0), line, font=subhead_font)
            line_width = bbox[2] - bbox[0]
            x = (width - line_width) // 2
            self.draw_text_with_effects(draw, line, (x, current_y), subhead_font, self.colors["off_white"], {"shadow": True, "shadow_offset": 3, "outline": True, "outline_width": 1})
            current_y += line_spacing_subhead

        final_img = Image.alpha_composite(img, text_layer)
        final_img = self.add_logo(final_img, text_position="bottom")
        return final_img

    def render_diagonal_accent(self, img, headline, subheadline, post_id):
        """Template: Diagonal band across image from bottom-left to top-right."""
        width, height = img.size
        img = img.convert("RGBA")

        # Create diagonal band overlay
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw_overlay = ImageDraw.Draw(overlay)

        # Diagonal band parameters
        band_width = int(height * 0.28)
        # Points for diagonal parallelogram (bottom-left to top-right)
        angle_offset = int(width * 0.3)
        points = [
            (0, height - band_width),                    # bottom-left top
            (0, height),                                  # bottom-left bottom
            (width, band_width - angle_offset),          # bottom-right bottom
            (width, -angle_offset),                       # top-right top
        ]

        draw_overlay.polygon(points, fill=(*self.colors["brand_brown"], 235))

        # White border lines
        border_width = max(2, int(height * 0.003))
        # Top edge of band
        draw_overlay.line([(0, height - band_width), (width, -angle_offset)], fill=(255, 255, 255, 255), width=border_width)
        # Bottom edge of band
        draw_overlay.line([(0, height), (width, band_width - angle_offset)], fill=(255, 255, 255, 255), width=border_width)

        img = Image.alpha_composite(img, overlay)

        # Create text layer
        text_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_layer)

        # Text positioned in center of diagonal band
        text_width = int(width * 0.7)
        text_height = int(band_width * 0.7)

        # Calculate font sizes
        headline_size, headline_font, headline_lines = self.calculate_font_size(
            headline, text_width, text_height * 0.55, draw, int(height * 0.045), min_size=22
        )
        subhead_size, subhead_font, subhead_lines = self.calculate_font_size(
            subheadline, text_width, text_height * 0.35, draw, int(height * 0.028), min_size=14
        )

        # Position text in center of the band
        center_x = width // 2
        center_y = int(height * 0.62)  # Adjusted for diagonal

        line_spacing_headline = headline_size * 1.1
        line_spacing_subhead = subhead_size * 1.15
        gap = int(height * 0.015)
        total_height = len(headline_lines) * line_spacing_headline + gap + len(subhead_lines) * line_spacing_subhead
        current_y = center_y - total_height // 2

        for line in headline_lines:
            bbox = draw.textbbox((0, 0), line, font=headline_font)
            line_width = bbox[2] - bbox[0]
            x = center_x - line_width // 2
            self.draw_text_with_effects(draw, line, (x, current_y), headline_font, self.colors["white"], {"shadow": True, "outline": False})
            current_y += line_spacing_headline

        current_y += gap

        for line in subhead_lines:
            bbox = draw.textbbox((0, 0), line, font=subhead_font)
            line_width = bbox[2] - bbox[0]
            x = center_x - line_width // 2
            self.draw_text_with_effects(draw, line, (x, current_y), subhead_font, self.colors["off_white"], {"shadow": True, "outline": False})
            current_y += line_spacing_subhead

        final_img = Image.alpha_composite(img, text_layer)
        # Logo in top right (outside the band)
        final_img = self.add_logo(final_img, text_position="top")
        return final_img

    # ========== END TEMPLATE METHODS ==========

    def apply_text_overlay(self, image_path, headline, subheadline, post_id, placement=None, try_ai_edit=False, template=None):
        """
        Apply professional text overlay to image using templates or AI-driven process.

        Args:
            image_path: Path to the base image
            headline: Main text to overlay
            subheadline: Secondary text
            post_id: Identifier for output filename
            placement: Pre-computed placement dict (optional, ignored if template specified)
            try_ai_edit: If True, attempt AI image editing first (experimental)
            template: Template name (top_bar, bottom_bar, left_sidebar, center_circle,
                      split_horizontal, full_text, diagonal_accent). If None, uses AI placement.
        """

        # Optional: Try AI image editing first (experimental)
        if try_ai_edit:
            ai_result = self.try_ai_image_edit(image_path, headline, subheadline, post_id)
            if ai_result:
                print(f"AI image edit succeeded for post {post_id}")
                return {
                    "success": True,
                    "filepath": ai_result,
                    "method": "ai_edit",
                    "placement_used": {"method": "ai_image_edit"}
                }
            print(f"AI edit failed, falling back to programmatic rendering")

        # Open image
        img = Image.open(image_path).convert("RGBA")

        # ========== TEMPLATE-BASED RENDERING ==========
        if template and template in self.TEMPLATES:
            print(f"Using template: {template}")

            # Dispatch to template renderer
            template_methods = {
                "top_bar": self.render_top_bar,
                "bottom_bar": self.render_bottom_bar,
                "left_sidebar": self.render_left_sidebar,
                "center_circle": self.render_center_circle,
                "split_horizontal": self.render_split_horizontal,
                "full_text": self.render_full_text,
                "diagonal_accent": self.render_diagonal_accent,
            }

            render_method = template_methods.get(template)
            if render_method:
                final_img = render_method(img, headline, subheadline, post_id)

                # Convert to RGB for saving
                final_rgb = final_img.convert("RGB")
                output_path = os.path.join(self.output_dir, f"post_{post_id}_final.png")
                final_rgb.save(output_path, "PNG", quality=95, optimize=True)

                print(f"Template overlay complete for post {post_id}: {output_path}")

                return {
                    "success": True,
                    "filepath": output_path,
                    "method": "template",
                    "template": template,
                    "placement_used": {"template": template},
                    "details": {
                        "template": template,
                        "headline": headline,
                        "subheadline": subheadline
                    }
                }
        elif template:
            print(f"Warning: Unknown template '{template}', falling back to AI placement")

        # ========== AI-DIRECTED RENDERING (fallback) ==========
        width, height = img.size

        # STEP 1: Get AI creative direction for text placement
        if placement is None:
            print(f"Step 1: Analyzing image for optimal text placement...")
            placement = self.get_text_placement_suggestion(image_path, headline, subheadline)
            print(f"AI chose: {placement.get('headline_position')} - {placement.get('reasoning', '')[:100]}")

        # Create working layers
        text_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_layer)

        # Determine text area and positioning
        pos = placement.get("headline_position", "bottom")
        align = placement.get("headline_alignment", "center")

        # Calculate margins and text area
        margin_x = int(width * 0.06)
        margin_y = int(height * 0.04)
        max_text_width = width - (margin_x * 2)

        # Determine Y positioning based on placement (matches 20% bar height)
        if pos == "bottom":
            text_area_top = int(height * 0.81)
            text_area_bottom = height - margin_y
        elif pos == "top":
            text_area_top = margin_y
            text_area_bottom = int(height * 0.19)
        else:  # middle
            text_area_top = int(height * 0.42)
            text_area_bottom = int(height * 0.58)

        text_area_height = text_area_bottom - text_area_top

        # STEP 2: Apply AI-recommended font sizes or use intelligent defaults
        ai_headline_size = placement.get("headline_font_size", 0.08)
        ai_subhead_size = placement.get("subheadline_font_size", 0.045)

        # Calculate optimal headline font size using AI recommendation
        headline_base_size = int(height * ai_headline_size)
        headline_size, headline_font, headline_lines = self.calculate_font_size(
            headline, max_text_width, text_area_height * 0.6, draw, headline_base_size, min_size=32
        )

        # Calculate subheadline font size using AI recommendation
        subhead_base_size = int(height * ai_subhead_size)
        subhead_size, subhead_font, subhead_lines = self.calculate_font_size(
            subheadline, max_text_width, text_area_height * 0.3, draw, subhead_base_size, min_size=20
        )

        # Apply vertical offset if AI recommended
        vertical_offset = placement.get("vertical_offset", 0)
        if vertical_offset:
            text_area_top = int(text_area_top + (height * vertical_offset))
            text_area_bottom = int(text_area_bottom + (height * vertical_offset))

        # Get colors
        headline_color = placement.get("headline_color", "white")
        if headline_color == "white":
            h_color = self.colors["white"]
        elif headline_color == "teal":
            h_color = self.colors["teal"]
        else:
            h_color = self.colors["dark_teal"]

        subhead_color = placement.get("subheadline_color", "white")
        s_color = self.colors["white"] if subhead_color == "white" else self.colors["light_gray"]

        # Calculate total text block height
        line_spacing_headline = headline_size * 1.15
        line_spacing_subhead = subhead_size * 1.2
        gap_between = int(height * 0.02)

        total_headline_height = len(headline_lines) * line_spacing_headline
        total_subhead_height = len(subhead_lines) * line_spacing_subhead
        total_text_height = total_headline_height + gap_between + total_subhead_height

        # Center text block vertically in text area
        text_block_start_y = text_area_top + (text_area_height - total_text_height) // 2

        # Add solid bar overlay for readability (brand brown #7a3921)
        # ALWAYS use solid_bar style - don't let AI override this
        overlay_color = "brand_brown"
        overlay_opacity = placement.get("overlay_opacity", 0.9)
        gradient_style = "solid_bar"  # Force solid bar style
        gradient = self.create_gradient_overlay(width, height, pos, overlay_color, overlay_opacity, gradient_style)
        img = Image.alpha_composite(img, gradient)

        # Recreate draw object on text layer
        draw = ImageDraw.Draw(text_layer)

        # Determine text effects based on AI recommendations
        text_effect = placement.get("text_effect", "outlined")
        shadow_strength = placement.get("text_shadow_strength", "medium")

        # Map shadow strength to offset values
        shadow_offsets = {"none": 0, "subtle": 2, "medium": 3, "strong": 5}
        headline_shadow_offset = shadow_offsets.get(shadow_strength, 3)
        subhead_shadow_offset = max(1, headline_shadow_offset - 1)

        # Configure effects based on AI recommendations
        headline_effects = {
            "shadow": shadow_strength != "none",
            "shadow_offset": headline_shadow_offset,
            "outline": text_effect in ["outlined", "embossed"],
            "outline_width": 3 if text_effect == "embossed" else 2,
            "glow": text_effect == "glow"
        }

        subhead_effects = {
            "shadow": shadow_strength != "none",
            "shadow_offset": subhead_shadow_offset,
            "outline": text_effect in ["outlined", "embossed"],
            "outline_width": 2 if text_effect == "embossed" else 1,
            "glow": text_effect == "glow"
        }

        print(f"Step 2: Rendering text with effects: {text_effect}, shadow: {shadow_strength}")

        # Draw headline lines
        current_y = text_block_start_y
        for line in headline_lines:
            bbox = draw.textbbox((0, 0), line, font=headline_font)
            line_width = bbox[2] - bbox[0]

            # Calculate X based on alignment
            if align == "center":
                x = (width - line_width) // 2
            elif align == "left":
                x = margin_x
            else:  # right
                x = width - line_width - margin_x

            # Draw with AI-recommended effects
            self.draw_text_with_effects(
                draw, line, (x, current_y), headline_font, h_color, headline_effects
            )
            current_y += line_spacing_headline

        # Add gap
        current_y += gap_between

        # Draw subheadline lines
        for line in subhead_lines:
            bbox = draw.textbbox((0, 0), line, font=subhead_font)
            line_width = bbox[2] - bbox[0]

            if align == "center":
                x = (width - line_width) // 2
            elif align == "left":
                x = margin_x
            else:
                x = width - line_width - margin_x

            self.draw_text_with_effects(
                draw, line, (x, current_y), subhead_font, s_color, subhead_effects
            )
            current_y += line_spacing_subhead

        # Composite layers
        final_img = Image.alpha_composite(img, text_layer)

        # Add Project Ruth logo (top right if text is top, bottom right if text is bottom)
        final_img = self.add_logo(final_img, text_position=pos)

        # Convert to RGB for saving
        final_rgb = final_img.convert("RGB")

        # Save with high quality
        output_path = os.path.join(self.output_dir, f"post_{post_id}_final.png")
        final_rgb.save(output_path, "PNG", quality=95, optimize=True)

        print(f"Text overlay complete for post {post_id}: {output_path}")

        return {
            "success": True,
            "filepath": output_path,
            "method": "ai_directed_programmatic",
            "placement_used": placement,
            "details": {
                "headline_size": headline_size,
                "subheadline_size": subhead_size,
                "text_effect": text_effect,
                "shadow_strength": shadow_strength,
                "overlay_style": gradient_style if placement.get("use_overlay") else "none",
                "position": pos,
                "reasoning": placement.get("reasoning", "")
            }
        }


if __name__ == "__main__":
    overlay = TextOverlay()
    result = overlay.apply_text_overlay(
        "output/post_1_base.png",
        "Together We Grow Stronger",
        "Building community through meaningful connection",
        1
    )
    print(result)
