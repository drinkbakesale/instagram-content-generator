import os
import json
import base64
import requests
from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image
import numpy as np

load_dotenv()

PROMPTS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts_config.json")

def load_prompt(key):
    """Load a specific prompt from config."""
    if os.path.exists(PROMPTS_FILE):
        with open(PROMPTS_FILE, 'r') as f:
            prompts = json.load(f)
            return prompts.get(key, {}).get('prompt', '')
    return ''

class ImageGenerator:
    # Template-specific composition instructions for clear text zones
    TEMPLATE_COMPOSITION = {
        "top_bar": {
            "clear_zone": "TOP 20%",
            "instruction": "Leave the TOP 20% of the image as clear sky, wall, or simple low-detail background. Position all people, faces, and key subjects in the lower 80% of the frame.",
            "subject_position": "center-bottom"
        },
        "bottom_bar": {
            "clear_zone": "BOTTOM 20%",
            "instruction": "Leave the BOTTOM 20% of the image as simple floor, ground, table, or low-detail background. Position all people, faces, and key subjects in the upper 80% of the frame.",
            "subject_position": "center-top"
        },
        "left_sidebar": {
            "clear_zone": "LEFT 35%",
            "instruction": "Leave the LEFT 35% of the image as a simple wall, sky, or solid-colored low-detail background. Position all people, faces, and key subjects on the RIGHT side of the frame.",
            "subject_position": "right"
        },
        "center_circle": {
            "clear_zone": "CENTER",
            "instruction": "Position subjects around the EDGES of the frame, leaving the CENTER of the image relatively simple or low-detail (like a wall, sky, or blurred background) for a circular text overlay.",
            "subject_position": "edges"
        },
        "full_text": {
            "clear_zone": "CENTER",
            "instruction": "Create an image with good contrast between foreground and background. The center will have large text overlaid, so avoid complex patterns in the middle. Subjects can be positioned anywhere but ensure there's tonal variation for text readability.",
            "subject_position": "any"
        },
    }

    def __init__(self):
        self.openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
        self.output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_image_prompt(self, post_concept, copy_data, style_guide, template=None):
        """Generate an optimized image prompt based on the post concept and template."""

        # Load prompt from config
        prompt_template = load_prompt('image_prompt')

        # Fill in the template
        prompt = prompt_template.format(
            post_type=post_concept.get('type', ''),
            post_title=post_concept.get('title', ''),
            post_visual=post_concept.get('visual', ''),
            headline=copy_data.get('headline', '')
        )

        # Get template-specific composition instructions
        template_info = self.TEMPLATE_COMPOSITION.get(template, self.TEMPLATE_COMPOSITION["top_bar"])
        composition_instruction = template_info["instruction"]
        clear_zone = template_info["clear_zone"]

        system_prompt = f"""You are an expert at creating image generation prompts optimized for AI image generation.

STYLE REQUIREMENTS - VERY IMPORTANT:
- Modern, casual, everyday people in contemporary clothing (no religious head coverings, no traditional/formal attire)
- Candid, natural moments - NOT posed stock photos. Think documentary-style, lifestyle photography
- Imperfect and authentic - slight motion blur okay, natural expressions, real moments
- Modern diverse people who look relatable and approachable
- Natural lighting preferred (window light, outdoor shade, golden hour)
- Warm, inviting atmosphere but not overly polished or staged

Key principles:
- Be highly specific and descriptive about composition, lighting, colors, and mood
- Use natural language descriptions rather than technical camera terms
- Specify "candid lifestyle photography" or "documentary-style" NOT "stock photo" or "professional portrait"
- Include emotional tone and atmosphere descriptors
- Describe spatial relationships clearly (foreground, background, center)
- Always specify "no text, no words, no letters, no writing" to avoid text artifacts
- Quality boosters: "authentic", "natural", "candid", "real moment"

CRITICAL COMPOSITION REQUIREMENT FOR THIS IMAGE:
{composition_instruction}

The {clear_zone} area must be kept simple/low-detail because text will be overlaid there.
Include this composition requirement naturally in your prompt."""

        response = self.openai_client.chat.completions.create(
            model="gpt-5.2",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=600,
            temperature=0.7
        )

        return response.choices[0].message.content.strip()

    def generate_with_gpt_image(self, prompt, post_id, template=None):
        """Generate image using GPT Image 1.5 (latest OpenAI image model)."""
        try:
            # Get template-specific composition instructions
            template_info = self.TEMPLATE_COMPOSITION.get(template, self.TEMPLATE_COMPOSITION["top_bar"])
            style_instruction = "Modern casual people in contemporary clothing, candid natural moment, documentary-style lifestyle photo, authentic and relatable, NOT a posed stock photo."
            composition_suffix = f" No text, words, letters, or writing in the image. STYLE: {style_instruction} COMPOSITION: {template_info['instruction']} Portrait orientation, 3:4 aspect ratio."

            response = self.openai_client.images.generate(
                model="gpt-image-1.5",
                prompt=prompt + composition_suffix,
                size="1024x1536",  # 3:4 aspect ratio (portrait)
                quality="high",
                n=1
            )

            # GPT Image returns base64 by default
            image_base64 = response.data[0].b64_json
            image_bytes = base64.b64decode(image_base64)

            filepath = os.path.join(self.output_dir, f"post_{post_id}_base.png")
            with open(filepath, "wb") as f:
                f.write(image_bytes)

            # Smart crop to zoom in if too much blank space
            self.smart_crop(filepath)

            return {
                "success": True,
                "filepath": filepath,
                "prompt_used": prompt
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def smart_crop(self, filepath, target_aspect=3/4):
        """
        Analyze image and zoom/crop if there's too much blank space.
        Keeps the focal point centered and maintains 3:4 aspect ratio.
        """
        try:
            img = Image.open(filepath)
            width, height = img.size

            # Analyze image for focal point using edge detection
            # Convert to grayscale and find areas of high detail
            gray = img.convert('L')
            pixels = np.array(gray)

            # Calculate variance in sliding windows to find busy areas
            window_size = height // 10
            detail_map = np.zeros((height // window_size, width // window_size))

            for i in range(detail_map.shape[0]):
                for j in range(detail_map.shape[1]):
                    window = pixels[
                        i * window_size:(i + 1) * window_size,
                        j * window_size:(j + 1) * window_size
                    ]
                    detail_map[i, j] = np.std(window)  # Higher std = more detail

            # Find the center of mass of detail (focal point)
            total_detail = np.sum(detail_map)
            if total_detail == 0:
                return  # No clear focal point

            y_indices, x_indices = np.indices(detail_map.shape)
            focal_y = int(np.sum(y_indices * detail_map) / total_detail * window_size + window_size / 2)
            focal_x = int(np.sum(x_indices * detail_map) / total_detail * window_size + window_size / 2)

            # Check if there's significant blank space (low detail in edges)
            edge_detail = np.mean([
                np.mean(detail_map[0, :]),  # Top edge
                np.mean(detail_map[-1, :]),  # Bottom edge
                np.mean(detail_map[:, 0]),  # Left edge
                np.mean(detail_map[:, -1])  # Right edge
            ])
            center_detail = np.mean(detail_map[1:-1, 1:-1])

            # If edges have much less detail than center, zoom in
            if center_detail > edge_detail * 1.5:
                # Zoom in by 15%
                zoom_factor = 0.85

                new_width = int(width * zoom_factor)
                new_height = int(height * zoom_factor)

                # Calculate crop box centered on focal point
                left = max(0, min(focal_x - new_width // 2, width - new_width))
                top = max(0, min(focal_y - new_height // 2, height - new_height))
                right = left + new_width
                bottom = top + new_height

                # Crop and resize back to original dimensions
                cropped = img.crop((left, top, right, bottom))
                resized = cropped.resize((width, height), Image.Resampling.LANCZOS)

                # Save
                resized.save(filepath, quality=95)
                print(f"Smart cropped image - zoomed to focal point at ({focal_x}, {focal_y})")

        except Exception as e:
            print(f"Smart crop error (non-fatal): {e}")

    def generate_with_gemini(self, prompt, post_id, template=None):
        """Generate image using Gemini Imagen API."""
        # Note: Gemini's image generation API structure
        # This is a placeholder - actual implementation depends on Google's API
        try:
            import google.generativeai as genai

            genai.configure(api_key=self.gemini_api_key)

            # Get template-specific composition instructions
            template_info = self.TEMPLATE_COMPOSITION.get(template, self.TEMPLATE_COMPOSITION["top_bar"])
            composition_suffix = f" No text in image. {template_info['instruction']}"

            # Gemini Imagen endpoint
            response = genai.ImageGenerationModel("imagen-3.0-generate-001").generate_images(
                prompt=prompt + composition_suffix,
                number_of_images=1,
                aspect_ratio="3:4"  # Portrait
            )

            if response.images:
                filepath = os.path.join(self.output_dir, f"post_{post_id}_base.png")
                response.images[0].save(filepath)
                return {
                    "success": True,
                    "filepath": filepath,
                    "prompt_used": prompt
                }
            else:
                return {"success": False, "error": "No images generated"}

        except Exception as e:
            # Fall back to GPT Image if Gemini fails
            print(f"Gemini failed ({e}), falling back to GPT Image")
            return self.generate_with_gpt_image(prompt, post_id, template=template)

    def generate_image(self, post_concept, copy_data, style_guide, post_id, use_gemini=True, template=None):
        """Generate an image for a post with template-aware composition.

        Args:
            post_concept: Dict with post type, title, visual description
            copy_data: Dict with headline, subheadline
            style_guide: Brand style guidelines
            post_id: Unique identifier for the post
            use_gemini: Whether to try Gemini first (falls back to GPT Image)
            template: Template name for composition guidance (top_bar, bottom_bar,
                      left_sidebar, center_circle, split_horizontal, full_text, diagonal_accent)
        """
        # First, create an optimized prompt with template-specific composition
        image_prompt = self.generate_image_prompt(post_concept, copy_data, style_guide, template=template)

        print(f"Generating image with template composition: {template or 'top_bar (default)'}")

        # Try Gemini first, fall back to GPT Image
        if use_gemini and self.gemini_api_key:
            result = self.generate_with_gemini(image_prompt, post_id, template=template)
        else:
            result = self.generate_with_gpt_image(image_prompt, post_id, template=template)

        result["image_prompt"] = image_prompt
        result["template"] = template
        return result


if __name__ == "__main__":
    generator = ImageGenerator()
    test_concept = {
        "type": "Educational",
        "title": "Community Support",
        "visual": "Diverse group of people in warm setting"
    }
    test_copy = {"headline": "Together We Grow"}

    result = generator.generate_image(test_concept, test_copy, "Professional style", 1, use_gemini=False)
    print(result)  # Uses GPT Image 1.5
