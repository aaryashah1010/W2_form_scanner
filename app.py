import os
from flask import Flask, render_template, request
from dotenv import load_dotenv
import google.generativeai as genai
from PIL import Image
import json
import pandas as pd

# Load environment variable
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# Flask app setup
app = Flask(__name__)
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Gemini setup
genai.configure(api_key=api_key)

def get_prompt():
    return """Please extract all the filled-out fields from the attached W-2 form and return the result in json format.
⚠️ Important Instructions:
- Only include fields that are filled.
- Keep the key names exactly as written on the W-2 form (e.g., "Wages, tips, other compensation", "Federal income tax withheld").
- If any fields appear more than once, pick the most clearly filled instance.
- Skip decorative or empty parts.
- Maintain clear, clean formatting.
📦 Example output format:
{
  "Employee’s social security number": "XXX-XX-XXXX",
  "Employer identification number (EIN)": "12-3456789",
  "Wages, tips, other compensation": "$45,000.00",
  "Federal income tax withheld": "$3,500.00",
  "Social security wages": "$45,000.00",
  "Social security tax withheld": "$2,790.00"
}"""

def extract_fields(image_path, prompt):
    model = genai.GenerativeModel('gemini-1.5-flash')
    image = Image.open(image_path)
    response = model.generate_content([prompt, image], stream=True)
    response.resolve()
    return response.text

def try_parse_json(text):
    try:
        # Remove ```json or ``` wrappers if present
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.startswith("json"):
                text = text[4:].strip()
        return json.loads(text)
    except Exception as e:
        print("❌ JSON parsing failed:", e)
        return None

def save_to_csv(data, csv_path="extracted_data.csv"):
    df = pd.DataFrame([data])  # wrap data in list to get row
    if not os.path.exists(csv_path):
        df.to_csv(csv_path, index=False)
    else:
        df.to_csv(csv_path, mode='a', header=False, index=False)

@app.route("/", methods=["GET", "POST"])
def index():
    result_text = None
    parsed_json = None

    if request.method == "POST":
        file = request.files["image"]
        if file:
            filename = "test2.png"
            image_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(image_path)

            prompt = get_prompt()
            result_text = extract_fields(image_path, prompt)
            parsed_json = try_parse_json(result_text)

            if parsed_json:
                save_to_csv(parsed_json)

    return render_template("index.html", result_text=result_text, parsed_json=parsed_json)

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Render sets the PORT env variable
    app.run(host="0.0.0.0", port=port, debug=True)
