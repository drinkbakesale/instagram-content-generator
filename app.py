import os
import json
import traceback
from flask import Flask, render_template, request, jsonify, send_from_directory
from dotenv import load_dotenv

load_dotenv()

from services.website_scraper import WebsiteScraper
from services.content_strategist import ContentStrategist
from services.copy_generator import CopyGenerator
from services.image_generator import ImageGenerator
from services.text_overlay import TextOverlay
from services.photo_manager import PhotoManager, BrandDocAnalyzer
from config import STYLE_GUIDE, TARGET_WEBSITE

# Initialize photo and brand managers
photo_manager = PhotoManager()
brand_analyzer = BrandDocAnalyzer()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'instagram-content-generator-2024'

# Prompts config file
PROMPTS_FILE = os.path.join(os.path.dirname(__file__), "prompts_config.json")

def load_prompts():
    """Load prompts from config file."""
    if os.path.exists(PROMPTS_FILE):
        with open(PROMPTS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_prompts(prompts):
    """Save prompts to config file."""
    with open(PROMPTS_FILE, 'w') as f:
        json.dump(prompts, f, indent=2)

# Global state to track progress
SESSION_FILE = os.path.join(os.path.dirname(__file__), "session_data.json")

def load_session():
    """Load session data from file."""
    default = {
        "website_content": None,
        "content_strategy": [],
        "approved_concepts": [],
        "copy_options": {},
        "approved_copy": {},
        "generated_images": {},
        "final_images": {},
        "current_step": "start"
    }
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, 'r') as f:
                return json.load(f)
        except:
            return default
    return default

def save_session():
    """Save session data to file."""
    with open(SESSION_FILE, 'w') as f:
        json.dump(session_data, f)

session_data = load_session()

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/scrape', methods=['POST'])
def scrape_website():
    """Step 1: Scrape the target website."""
    data = request.json
    url = data.get('url', TARGET_WEBSITE)

    try:
        scraper = WebsiteScraper(url)
        content = scraper.scrape(max_pages=25)
        summary = scraper.get_summary()

        session_data["website_content"] = {
            "raw": content,
            "summary": summary
        }
        session_data["current_step"] = "scraped"
        save_session()

        return jsonify({
            "success": True,
            "summary": summary,
            "pages_scraped": len(content["pages"])
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/generate-strategy', methods=['POST'])
def generate_strategy():
    """Step 2: Generate content strategy with 30 post concepts."""
    if not session_data["website_content"]:
        return jsonify({"success": False, "error": "Please scrape website first"})

    try:
        data = request.json
        num_posts = data.get('num_posts', 30)

        strategist = ContentStrategist()
        posts = strategist.generate_content_strategy(
            session_data["website_content"]["summary"],
            STYLE_GUIDE,
            num_posts=num_posts
        )

        session_data["content_strategy"] = posts
        session_data["current_step"] = "strategy_generated"
        save_session()

        return jsonify({
            "success": True,
            "posts": posts,
            "count": len(posts)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/approve-concepts', methods=['POST'])
def approve_concepts():
    """Step 3: Approve selected post concepts."""
    data = request.json
    approved_ids = data.get('approved_ids', [])

    # Convert all IDs to strings for consistent comparison
    approved_ids_str = [str(i) for i in approved_ids]
    approved = [p for p in session_data["content_strategy"] if str(p["id"]) in approved_ids_str]
    session_data["approved_concepts"] = approved
    session_data["current_step"] = "concepts_approved"
    save_session()

    return jsonify({
        "success": True,
        "approved_count": len(approved),
        "approved_concepts": approved
    })


@app.route('/api/generate-copy', methods=['POST'])
def generate_copy():
    """Step 4: Generate copy options for approved concepts."""
    if not session_data["approved_concepts"]:
        return jsonify({"success": False, "error": "Please approve concepts first"})

    try:
        data = request.json
        concept_id = data.get('concept_id')

        # Find the concept (handle string/int mismatch)
        concept = find_concept(concept_id)
        if not concept:
            return jsonify({"success": False, "error": "Concept not found"})

        generator = CopyGenerator()
        brand_info = session_data["website_content"]["summary"][:1500]
        options = generator.generate_copy_options(concept, brand_info)

        session_data["copy_options"][concept_id] = options
        save_session()

        return jsonify({
            "success": True,
            "concept_id": concept_id,
            "options": options
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/generate-all-copy', methods=['POST'])
def generate_all_copy():
    """Generate copy for all approved concepts at once."""
    if not session_data["approved_concepts"]:
        return jsonify({"success": False, "error": "Please approve concepts first"})

    try:
        generator = CopyGenerator()
        brand_info = session_data["website_content"]["summary"][:1500]

        all_copy = {}
        for concept in session_data["approved_concepts"]:
            options = generator.generate_copy_options(concept, brand_info)
            all_copy[concept["id"]] = options

        session_data["copy_options"] = all_copy
        session_data["current_step"] = "copy_generated"
        save_session()

        return jsonify({
            "success": True,
            "copy_options": all_copy
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/approve-copy', methods=['POST'])
def approve_copy():
    """Step 5: Approve copy for a concept."""
    data = request.json
    concept_id = data.get('concept_id')
    copy_option = data.get('copy_option')

    session_data["approved_copy"][concept_id] = copy_option
    session_data["current_step"] = "copy_approved"
    save_session()

    return jsonify({
        "success": True,
        "concept_id": concept_id,
        "approved_copy": copy_option
    })


@app.route('/api/generate-image', methods=['POST'])
def generate_image():
    """Step 6: Generate image for a post."""
    data = request.json
    concept_id = data.get('concept_id')
    concept_id_str = str(concept_id)
    template = data.get('template')  # Optional template for composition guidance

    concept = find_concept(concept_id)
    copy_data = get_copy_data(concept_id)

    if not concept:
        return jsonify({"success": False, "error": "Concept not found"})
    if not copy_data:
        return jsonify({"success": False, "error": "Please approve copy first"})

    try:
        generator = ImageGenerator()
        result = generator.generate_image(
            concept,
            copy_data,
            STYLE_GUIDE,
            concept_id_str,  # Use string for consistent filenames
            use_gemini=False,  # Default to DALL-E for reliability
            template=template  # Pass template for composition guidance
        )

        if result["success"]:
            session_data["generated_images"][concept_id_str] = result
            save_session()

        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/templates', methods=['GET'])
def get_templates():
    """Get available overlay templates."""
    return jsonify({
        "success": True,
        "templates": TextOverlay.TEMPLATES,
        "descriptions": {
            "top_bar": "Horizontal bar at top 20% of image",
            "bottom_bar": "Horizontal bar at bottom 20% of image",
            "left_sidebar": "Vertical sidebar on left 30% of image",
            "center_circle": "Circular overlay in center of image",
            "split_horizontal": "Top 55% image, bottom 45% solid with text",
            "full_text": "Full image with radial gradient and centered text",
            "diagonal_accent": "Diagonal band across image"
        }
    })


@app.route('/api/apply-overlay', methods=['POST'])
def apply_overlay():
    """Step 7: Apply text overlay to generated image."""
    data = request.json
    concept_id = data.get('concept_id')
    concept_id_str = str(concept_id)
    template = data.get('template')  # Optional template name

    # Check for generated image with string key handling
    image_info = session_data["generated_images"].get(concept_id_str) or session_data["generated_images"].get(concept_id)

    if not image_info:
        return jsonify({"success": False, "error": "Please generate image first"})

    copy_data = get_copy_data(concept_id)

    try:
        overlay_service = TextOverlay()
        result = overlay_service.apply_text_overlay(
            image_info["filepath"],
            copy_data.get("headline", "") if copy_data else "",
            copy_data.get("subheadline", "") if copy_data else "",
            concept_id_str,
            template=template
        )

        if result["success"]:
            session_data["final_images"][concept_id_str] = result
            save_session()

        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


def find_concept(concept_id):
    """Find concept by ID, handling string/int mismatches."""
    # First check approved concepts
    for c in session_data["approved_concepts"]:
        if str(c["id"]) == str(concept_id):
            return c
    # Fallback to full content strategy
    for c in session_data.get("content_strategy", []):
        if str(c["id"]) == str(concept_id):
            return c
    return None

def get_copy_data(concept_id):
    """Get copy data by ID, handling string/int mismatches."""
    # Try as-is first
    if concept_id in session_data["approved_copy"]:
        return session_data["approved_copy"][concept_id]
    # Try as string
    if str(concept_id) in session_data["approved_copy"]:
        return session_data["approved_copy"][str(concept_id)]
    # Try as int
    try:
        int_id = int(concept_id)
        if int_id in session_data["approved_copy"]:
            return session_data["approved_copy"][int_id]
    except (ValueError, TypeError):
        pass
    return None


@app.route('/api/generate-full-post', methods=['POST'])
def generate_full_post():
    """Generate complete post (image + overlay) for a concept."""
    data = request.json
    concept_id = data.get('concept_id')
    template = data.get('template')  # Optional template name

    # Normalize concept_id to string for consistent storage
    concept_id_str = str(concept_id)

    concept = find_concept(concept_id)
    copy_data = get_copy_data(concept_id)

    if not concept:
        return jsonify({"success": False, "error": f"Concept not found for id {concept_id}. Available concepts: {[c.get('id') for c in session_data.get('approved_concepts', [])]}"})
    if not copy_data:
        return jsonify({"success": False, "error": f"Please approve copy first. Approved copy keys: {list(session_data.get('approved_copy', {}).keys())}"})

    try:
        # Step 1: Generate base image with template-aware composition
        print(f"Step 1: Generating base image for concept {concept_id_str} with template: {template or 'default'}...")
        img_generator = ImageGenerator()
        img_result = img_generator.generate_image(
            concept,
            copy_data,
            STYLE_GUIDE,
            concept_id_str,  # Use string ID for consistent filenames
            use_gemini=False,
            template=template  # Pass template for composition guidance
        )

        if not img_result["success"]:
            return jsonify(img_result)

        # Store with string key for consistency
        session_data["generated_images"][concept_id_str] = img_result

        # Step 2: Apply text overlay (template or AI-directed)
        template_info = f" using template '{template}'" if template else " with AI-directed placement"
        print(f"Step 2: Applying text overlay for concept {concept_id_str}{template_info}...")
        overlay_service = TextOverlay()
        overlay_result = overlay_service.apply_text_overlay(
            img_result["filepath"],
            copy_data.get("headline", ""),
            copy_data.get("subheadline", ""),
            concept_id_str,  # Use string ID for consistent filenames
            template=template
        )

        if overlay_result["success"]:
            # Store with string key for consistency
            session_data["final_images"][concept_id_str] = overlay_result
            session_data["final_images"][concept_id_str]["copy"] = copy_data
            session_data["final_images"][concept_id_str]["concept"] = concept
            save_session()
            print(f"Successfully generated post {concept_id_str}")

        return jsonify({
            "success": True,
            "concept_id": concept_id_str,
            "base_image": img_result,
            "final_image": overlay_result
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/get-final-grid', methods=['GET'])
def get_final_grid():
    """Get all final images for grid display."""
    grid_data = []

    for concept_id, image_info in session_data["final_images"].items():
        # Handle string/int key mismatches for approved_copy and approved_concepts
        copy_data = get_copy_data(concept_id)
        concept_data = find_concept(concept_id)

        filepath = image_info.get("filepath", "")
        filename = os.path.basename(filepath) if filepath else ""

        # Only add if we have a valid filepath
        if filename:
            grid_data.append({
                "concept_id": concept_id,
                "filepath": filepath,
                "filename": filename,
                "copy": copy_data or {},
                "concept": concept_data or {}
            })

    return jsonify({
        "success": True,
        "images": grid_data,
        "count": len(grid_data)
    })


@app.route('/api/session-state', methods=['GET'])
def get_session_state():
    """Get current session state."""
    return jsonify({
        "current_step": session_data["current_step"],
        "has_website_content": session_data["website_content"] is not None,
        "strategy_count": len(session_data["content_strategy"]),
        "approved_concepts_count": len(session_data["approved_concepts"]),
        "copy_options_count": len(session_data["copy_options"]),
        "approved_copy_count": len(session_data["approved_copy"]),
        "generated_images_count": len(session_data["generated_images"]),
        "final_images_count": len(session_data["final_images"])
    })


@app.route('/api/reset', methods=['POST'])
def reset_session():
    """Reset all session data."""
    global session_data
    session_data = {
        "website_content": None,
        "content_strategy": [],
        "approved_concepts": [],
        "copy_options": {},
        "approved_copy": {},
        "generated_images": {},
        "final_images": {},
        "current_step": "start"
    }
    save_session()
    return jsonify({"success": True})


@app.route('/api/prompts', methods=['GET'])
def get_prompts():
    """Get all editable prompts."""
    prompts = load_prompts()
    return jsonify({"success": True, "prompts": prompts})


@app.route('/api/prompts/<prompt_key>', methods=['GET'])
def get_prompt(prompt_key):
    """Get a specific prompt."""
    prompts = load_prompts()
    if prompt_key in prompts:
        return jsonify({"success": True, "prompt": prompts[prompt_key]})
    return jsonify({"success": False, "error": "Prompt not found"})


@app.route('/api/prompts/<prompt_key>', methods=['POST'])
def update_prompt(prompt_key):
    """Update a specific prompt."""
    data = request.json
    new_prompt_text = data.get('prompt')

    if not new_prompt_text:
        return jsonify({"success": False, "error": "No prompt provided"})

    prompts = load_prompts()
    if prompt_key in prompts:
        prompts[prompt_key]['prompt'] = new_prompt_text
        save_prompts(prompts)
        return jsonify({"success": True, "message": "Prompt updated"})

    return jsonify({"success": False, "error": "Prompt not found"})


@app.route('/api/full-state', methods=['GET'])
def get_full_state():
    """Get complete session state for tab persistence."""
    return jsonify({
        "success": True,
        "data": {
            "website_content": session_data.get("website_content"),
            "content_strategy": session_data.get("content_strategy", []),
            "approved_concepts": session_data.get("approved_concepts", []),
            "copy_options": session_data.get("copy_options", {}),
            "approved_copy": session_data.get("approved_copy", {}),
            "generated_images": session_data.get("generated_images", {}),
            "final_images": session_data.get("final_images", {}),
            "current_step": session_data.get("current_step", "start")
        }
    })


@app.route('/output/<filename>')
def serve_output(filename):
    """Serve generated images."""
    return send_from_directory(OUTPUT_DIR, filename)


@app.route('/imported-photos/<filename>')
def serve_imported_photo(filename):
    """Serve imported photos."""
    photos_dir = os.path.join(os.path.dirname(__file__), "imported_photos")
    return send_from_directory(photos_dir, filename)


@app.route('/api/upload-photo', methods=['POST'])
def upload_photo():
    """Upload and analyze a photo."""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file provided"})

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"})

    try:
        photo_data = photo_manager.add_photo(file, file.filename)
        return jsonify({
            "success": True,
            "photo_id": photo_data["id"],
            "category": photo_data["category"],
            "tags": photo_data["tags"]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/get-imported-photos', methods=['GET'])
def get_imported_photos():
    """Get all imported photos."""
    photos = photo_manager.get_all_photos()
    return jsonify({"success": True, "photos": photos})


@app.route('/api/remove-photo', methods=['POST'])
def remove_photo():
    """Remove an imported photo."""
    data = request.json
    photo_id = data.get('photo_id')
    success = photo_manager.remove_photo(photo_id)
    return jsonify({"success": success})


@app.route('/api/upload-brand-doc', methods=['POST'])
def upload_brand_doc():
    """Upload and analyze a brand document."""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file provided"})

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"})

    try:
        result = brand_analyzer.analyze_document(file, file.filename)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'

    print("\n" + "="*60)
    print("Instagram Content Generator")
    print("="*60)
    print(f"Target website: {TARGET_WEBSITE}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"\nStarting server on port {port}")
    print("="*60 + "\n")

    app.run(debug=debug, host='0.0.0.0', port=port)
