import os
import json
import base64
import shutil
from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

class PhotoManager:
    def __init__(self):
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.base_dir = os.path.dirname(os.path.dirname(__file__))
        self.photos_dir = os.path.join(self.base_dir, "imported_photos")
        self.metadata_file = os.path.join(self.base_dir, "photo_metadata.json")
        os.makedirs(self.photos_dir, exist_ok=True)

    def load_metadata(self):
        """Load photo metadata from JSON file."""
        if os.path.exists(self.metadata_file):
            with open(self.metadata_file, 'r') as f:
                return json.load(f)
        return {"photos": []}

    def save_metadata(self, metadata):
        """Save photo metadata to JSON file."""
        with open(self.metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

    def analyze_photo(self, image_path):
        """Use GPT-5.2 Vision to analyze and categorize a photo."""
        try:
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")

            response = self.client.chat.completions.create(
                model="gpt-5.2",
                messages=[
                    {
                        "role": "system",
                        "content": """You are a photo analyst for a social media content system.
Analyze photos and return JSON with:
- category: One of ["People", "Event", "Food", "Location", "Product", "Community", "Education", "Celebration", "Nature", "Other"]
- tags: Array of 5-10 descriptive tags
- description: Brief 1-2 sentence description
- subjects: Array of main subjects in the photo
- mood: The emotional tone (warm, professional, casual, celebratory, etc.)
- suitable_for: Array of content types this photo would work for (e.g., "announcements", "testimonials", "promotions")

Output only valid JSON."""
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Analyze this photo for categorization and tagging:"},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                            }
                        ]
                    }
                ],
                max_completion_tokens=500
            )

            response_text = response.choices[0].message.content
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            if start != -1 and end > start:
                return json.loads(response_text[start:end])
        except Exception as e:
            print(f"Photo analysis error: {e}")

        return {
            "category": "Other",
            "tags": [],
            "description": "",
            "subjects": [],
            "mood": "neutral",
            "suitable_for": []
        }

    def add_photo(self, file_storage, filename):
        """Save an uploaded photo and analyze it."""
        # Generate unique ID
        import uuid
        photo_id = str(uuid.uuid4())[:8]

        # Save file
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.webp']:
            ext = '.jpg'
        new_filename = f"{photo_id}{ext}"
        filepath = os.path.join(self.photos_dir, new_filename)

        file_storage.save(filepath)

        # Resize if too large (keep aspect ratio, max 1500px)
        try:
            img = Image.open(filepath)
            if max(img.size) > 1500:
                img.thumbnail((1500, 1500), Image.Resampling.LANCZOS)
                img.save(filepath, quality=90)
        except Exception as e:
            print(f"Resize error: {e}")

        # Analyze photo
        analysis = self.analyze_photo(filepath)

        # Save metadata
        metadata = self.load_metadata()
        photo_data = {
            "id": photo_id,
            "filename": new_filename,
            "original_name": filename,
            "category": analysis.get("category", "Other"),
            "tags": analysis.get("tags", []),
            "description": analysis.get("description", ""),
            "subjects": analysis.get("subjects", []),
            "mood": analysis.get("mood", "neutral"),
            "suitable_for": analysis.get("suitable_for", [])
        }
        metadata["photos"].append(photo_data)
        self.save_metadata(metadata)

        return photo_data

    def get_all_photos(self):
        """Get all imported photos with metadata."""
        metadata = self.load_metadata()
        return metadata.get("photos", [])

    def remove_photo(self, photo_id):
        """Remove a photo by ID."""
        metadata = self.load_metadata()

        # Find and remove photo
        photos = metadata.get("photos", [])
        photo = next((p for p in photos if p["id"] == photo_id), None)

        if photo:
            # Delete file
            filepath = os.path.join(self.photos_dir, photo["filename"])
            if os.path.exists(filepath):
                os.remove(filepath)

            # Update metadata
            metadata["photos"] = [p for p in photos if p["id"] != photo_id]
            self.save_metadata(metadata)
            return True

        return False

    def find_matching_photos(self, copy_data, concept_data, limit=3):
        """Find photos that match the content of a post."""
        metadata = self.load_metadata()
        photos = metadata.get("photos", [])

        if not photos:
            return []

        # Build search context from copy and concept
        search_text = " ".join([
            copy_data.get("headline", ""),
            copy_data.get("subheadline", ""),
            copy_data.get("caption", ""),
            concept_data.get("title", ""),
            concept_data.get("message", ""),
            concept_data.get("type", "")
        ]).lower()

        # Score each photo
        scored_photos = []
        for photo in photos:
            score = 0

            # Check tags
            for tag in photo.get("tags", []):
                if tag.lower() in search_text:
                    score += 2

            # Check category
            if photo.get("category", "").lower() in search_text:
                score += 3

            # Check subjects
            for subject in photo.get("subjects", []):
                if subject.lower() in search_text:
                    score += 2

            # Check suitable_for
            post_type = concept_data.get("type", "").lower()
            for suitable in photo.get("suitable_for", []):
                if suitable.lower() in post_type or post_type in suitable.lower():
                    score += 3

            # Check mood
            if photo.get("mood", "").lower() in search_text:
                score += 1

            if score > 0:
                scored_photos.append((score, photo))

        # Sort by score and return top matches
        scored_photos.sort(key=lambda x: x[0], reverse=True)
        return [photo for score, photo in scored_photos[:limit] if score >= 2]


class BrandDocAnalyzer:
    def __init__(self):
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.base_dir = os.path.dirname(os.path.dirname(__file__))
        self.docs_dir = os.path.join(self.base_dir, "brand_docs")
        self.brand_voice_file = os.path.join(self.base_dir, "brand_voice.json")
        os.makedirs(self.docs_dir, exist_ok=True)

    def load_brand_voice(self):
        """Load existing brand voice analysis."""
        if os.path.exists(self.brand_voice_file):
            with open(self.brand_voice_file, 'r') as f:
                return json.load(f)
        return {}

    def save_brand_voice(self, data):
        """Save brand voice analysis."""
        with open(self.brand_voice_file, 'w') as f:
            json.dump(data, f, indent=2)

    def analyze_document(self, file_storage, filename):
        """Analyze a brand document and extract voice/guidelines."""
        import uuid
        doc_id = str(uuid.uuid4())[:8]

        # Save file
        ext = os.path.splitext(filename)[1].lower()
        new_filename = f"{doc_id}{ext}"
        filepath = os.path.join(self.docs_dir, new_filename)
        file_storage.save(filepath)

        # Read text content
        text_content = ""
        try:
            if ext == '.txt':
                with open(filepath, 'r', encoding='utf-8') as f:
                    text_content = f.read()
            elif ext == '.pdf':
                # Basic PDF text extraction (would need PyPDF2 or similar)
                text_content = f"[PDF document: {filename}]"
            else:
                text_content = f"[Document: {filename}]"
        except Exception as e:
            text_content = f"[Could not read document: {e}]"

        # Analyze with GPT
        try:
            response = self.client.chat.completions.create(
                model="gpt-5.2",
                messages=[
                    {
                        "role": "system",
                        "content": """Analyze this brand document and extract:
1. Brand voice characteristics (tone, style, personality)
2. Do's and Don'ts for content creation
3. Key messaging themes
4. Target audience insights
5. Visual style preferences

Output as JSON with keys: voice, dos, donts, themes, audience, visual_style"""
                    },
                    {
                        "role": "user",
                        "content": f"Analyze this brand document:\n\n{text_content[:4000]}"
                    }
                ],
                max_completion_tokens=800
            )

            response_text = response.choices[0].message.content
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            if start != -1 and end > start:
                analysis = json.loads(response_text[start:end])

                # Merge with existing brand voice
                existing = self.load_brand_voice()
                existing["documents"] = existing.get("documents", [])
                existing["documents"].append({
                    "filename": filename,
                    "analysis": analysis
                })

                # Update consolidated voice
                existing["voice"] = analysis.get("voice", existing.get("voice", ""))
                existing["dos"] = list(set(existing.get("dos", []) + analysis.get("dos", [])))
                existing["donts"] = list(set(existing.get("donts", []) + analysis.get("donts", [])))
                existing["themes"] = list(set(existing.get("themes", []) + analysis.get("themes", [])))

                self.save_brand_voice(existing)

                return {
                    "success": True,
                    "analysis": analysis,
                    "brand_voice": self.format_brand_voice(existing)
                }

        except Exception as e:
            print(f"Document analysis error: {e}")

        return {"success": False, "error": str(e)}

    def format_brand_voice(self, data):
        """Format brand voice data for display."""
        lines = []
        if data.get("voice"):
            lines.append(f"VOICE: {data['voice']}")
        if data.get("dos"):
            lines.append(f"\nDO's:\n- " + "\n- ".join(data['dos'][:5]))
        if data.get("donts"):
            lines.append(f"\nDON'Ts:\n- " + "\n- ".join(data['donts'][:5]))
        if data.get("themes"):
            lines.append(f"\nKEY THEMES: {', '.join(data['themes'][:5])}")
        return "\n".join(lines)

    def get_brand_guidelines(self):
        """Get brand guidelines for prompt generation."""
        data = self.load_brand_voice()
        if not data:
            return ""

        guidelines = []
        if data.get("voice"):
            guidelines.append(f"Brand Voice: {data['voice']}")
        if data.get("dos"):
            guidelines.append("Do's: " + "; ".join(data['dos'][:5]))
        if data.get("donts"):
            guidelines.append("Don'ts: " + "; ".join(data['donts'][:5]))

        return "\n".join(guidelines)
