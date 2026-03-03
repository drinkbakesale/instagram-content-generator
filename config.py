import os

# API Keys
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Target website
TARGET_WEBSITE = "https://projectruth.net/"

# Style guide based on 18doors Instagram analysis
STYLE_GUIDE = """
VISUAL STYLE (based on @18doorsorg Instagram):
- Primary colors: Deep teal/navy (#1B4D5C, #0D3B4C), warm accents
- Clean, modern sans-serif typography (bold headers, light body text)
- White or light text on dark backgrounds for graphics
- Mix of content types: photos with text overlay, pure graphics, lifestyle shots
- Branded corner logo placement (bottom right typically)
- Square format (1080x1080) for feed posts

CONTENT TYPES:
1. Holiday/Event announcements - Bold text, festive imagery
2. Educational infographics - Clean layouts, icons, bullet points
3. Personal stories/testimonials - Photo with name/title overlay
4. Recipe/How-to posts - Food photography with text overlay
5. Program promotions - Professional graphics with CTA
6. Inspirational quotes - Minimal design, impactful typography
7. Community photos - Candid shots with subtle branding

TONE:
- Warm, inclusive, welcoming
- Educational but accessible
- Community-focused
- Celebratory of diversity
- Supportive and empowering

TEXT OVERLAY STYLE:
- Headlines: Bold, large, often in brand teal or white
- Subheadlines: Lighter weight, smaller
- Always include organization branding
- CTAs when appropriate ("Learn more", "Join us", etc.)
"""

# Output settings
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
IMAGE_SIZE = (1080, 1440)  # 3:4 aspect ratio (portrait)
