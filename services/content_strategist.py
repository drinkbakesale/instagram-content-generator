import os
import json
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

class ContentStrategist:
    def __init__(self):
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def generate_content_strategy(self, website_summary, style_guide, num_posts=30):
        """Generate a content strategy with post concepts."""

        # Load prompt from config
        prompt_template = load_prompt('content_strategy')

        # Fill in the template
        prompt = prompt_template.format(
            num_posts=num_posts,
            website_summary=website_summary,
            style_guide=style_guide
        )

        response = self.client.chat.completions.create(
            model="gpt-5.2",
            messages=[
                {"role": "system", "content": "You are an expert social media content strategist specializing in nonprofit and community organizations."},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=6000,
            temperature=0.8
        )

        return self._parse_strategy(response.choices[0].message.content)

    def _parse_strategy(self, raw_response):
        """Parse the strategy response into structured data."""
        posts = []
        current_post = {}

        lines = raw_response.split('\n')

        for line in lines:
            line = line.strip()

            if line.startswith('POST ') or line.startswith('**POST'):
                if current_post:
                    posts.append(current_post)
                current_post = {"id": len(posts) + 1}
            elif line.startswith('Type:'):
                current_post['type'] = line.replace('Type:', '').strip().strip('*')
            elif line.startswith('Title:'):
                current_post['title'] = line.replace('Title:', '').strip().strip('*')
            elif line.startswith('Visual:'):
                current_post['visual'] = line.replace('Visual:', '').strip().strip('*')
            elif line.startswith('Message:'):
                current_post['message'] = line.replace('Message:', '').strip().strip('*')
            elif line.startswith('Hashtags:'):
                current_post['hashtags'] = line.replace('Hashtags:', '').strip().strip('*')

        if current_post and 'title' in current_post:
            posts.append(current_post)

        # Ensure all posts have required fields
        for i, post in enumerate(posts):
            post['id'] = i + 1
            post.setdefault('type', 'Educational')
            post.setdefault('title', f'Post {i+1}')
            post.setdefault('visual', 'Professional branded graphic')
            post.setdefault('message', 'Community focused message')
            post.setdefault('hashtags', '#community #nonprofit')
            post['status'] = 'pending'

        return posts


if __name__ == "__main__":
    strategist = ContentStrategist()
    # Test with sample data
    sample_summary = "Project Ruth is a community organization..."
    sample_style = "Professional, warm, inclusive style..."
    posts = strategist.generate_content_strategy(sample_summary, sample_style, num_posts=5)
    for post in posts:
        print(post)
