import os
import json
import pandas as pd
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from PIL import Image
import google.generativeai as genai

# Load environment variables
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# Flask app setup
app = Flask(__name__)
app.secret_key = "supersecretkey"  # required for Flask-Login sessions

# MongoDB setup
app.config["MONGO_URI"] = "mongodb://localhost:27017/w2db"
mongo = PyMongo(app)

# CORS setup to allow React (localhost:5173)
CORS(app, supports_credentials=True, origins=["http://localhost:5173"])

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, username):
        self.id = username

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

# Gemini setup
genai.configure(api_key=api_key)

UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Helper functions
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
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.startswith("json"):
                text = text[4:].strip()
        return json.loads(text)
    except Exception as e:
        print("❌ JSON parsing failed:", e)
        return None

def save_to_csv(data, csv_path="extracted_data.csv"):
    try:
        df = pd.DataFrame([data])
        if not os.path.exists(csv_path):
            df.to_csv(csv_path, index=False)
        else:
            df.to_csv(csv_path, mode='a', header=False, index=False)
    except PermissionError:
        print("❌ Cannot write to extracted_data.csv — file is open or locked.")

# Auth routes
@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json()
    if mongo.db.users.find_one({"username": data["username"]}):
        return jsonify({"error": "User already exists"}), 409

    hashed_pw = generate_password_hash(data["password"])
    mongo.db.users.insert_one({
        "username": data["username"],
        "password": hashed_pw
    })
    return jsonify({"message": "Signup successful"}), 201

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    user = mongo.db.users.find_one({"username": data["username"]})
    if not user or not check_password_hash(user["password"], data["password"]):
        return jsonify({"error": "Invalid credentials"}), 401

    login_user(User(user["username"]))
    return jsonify({"message": "Login successful"})

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return jsonify({"message": "Logged out"})

# Protected W-2 extraction endpoint
@app.route("/extract", methods=["POST"])
@login_required
def extract():
    file = request.files.get("image")
    if not file:
        return jsonify({"error": "No image uploaded"}), 400

    filename = "uploaded_image.png"
    image_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(image_path)

    prompt = get_prompt()
    result_text = extract_fields(image_path, prompt)
    parsed_json = try_parse_json(result_text)

    if parsed_json:
        save_to_csv(parsed_json)
        return jsonify({"parsed_json": parsed_json})
    else:
        return jsonify({
            "error": "Could not parse response as valid JSON.",
            "raw_response": result_text
        }), 422

# Health check
@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "W-2 Extractor API is running"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
