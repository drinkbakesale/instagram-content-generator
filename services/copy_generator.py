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

class CopyGenerator:
    def __init__(self):
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def generate_copy_options(self, post_concept, brand_info, num_options=3):
        """Generate copy options for a single post concept."""

        # Load prompt from config
        prompt_template = load_prompt('copy_generator')

        # Fill in the template
        prompt = prompt_template.format(
            num_options=num_options,
            post_type=post_concept.get('type', 'Educational'),
            post_title=post_concept.get('title', ''),
            post_visual=post_concept.get('visual', ''),
            post_message=post_concept.get('message', ''),
            post_hashtags=post_concept.get('hashtags', ''),
            brand_info=brand_info
        )

        response = self.client.chat.completions.create(
            model="gpt-5.2",
            messages=[
                {"role": "system", "content": "You are an expert social media copywriter who creates engaging, inclusive content."},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=1500,
            temperature=0.9
        )

        return self._parse_copy_options(response.choices[0].message.content)

    def _parse_copy_options(self, raw_response):
        """Parse copy options from response."""
        options = []
        current_option = {}

        lines = raw_response.split('\n')

        for line in lines:
            line = line.strip()

            if line.startswith('OPTION') or line.startswith('**OPTION'):
                if current_option and 'headline' in current_option:
                    options.append(current_option)
                current_option = {"id": len(options) + 1}
            elif line.startswith('Headline:'):
                current_option['headline'] = line.replace('Headline:', '').strip().strip('*"')
            elif line.startswith('Subheadline:'):
                current_option['subheadline'] = line.replace('Subheadline:', '').strip().strip('*"')
            elif line.startswith('Caption:'):
                current_option['caption'] = line.replace('Caption:', '').strip().strip('*"')
            elif line.startswith('Hashtags:'):
                current_option['hashtags'] = line.replace('Hashtags:', '').strip().strip('*')

        if current_option and 'headline' in current_option:
            options.append(current_option)

        # Ensure minimum fields
        for i, opt in enumerate(options):
            opt['id'] = i + 1
            opt.setdefault('headline', 'Your Message Here')
            opt.setdefault('subheadline', 'Supporting text')
            opt.setdefault('caption', 'Learn more about our community.')
            opt.setdefault('hashtags', '#community')

        return options

    def generate_batch_copy(self, approved_concepts, brand_info):
        """Generate copy for multiple approved concepts."""
        results = []
        for concept in approved_concepts:
            options = self.generate_copy_options(concept, brand_info)
            results.append({
                "concept": concept,
                "copy_options": options
            })
        return results


if __name__ == "__main__":
    generator = CopyGenerator()
    test_concept = {
        "type": "Educational",
        "title": "Community Support Guide",
        "visual": "Infographic with helpful tips",
        "message": "We're here to help",
        "hashtags": "#community #support"
    }
    options = generator.generate_copy_options(test_concept, "Community nonprofit organization")
    for opt in options:
        print(opt)
