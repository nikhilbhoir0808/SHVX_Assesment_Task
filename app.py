from flask import Flask, request, render_template, jsonify, session
import requests
import re
import random
from datetime import datetime
from dotenv import load_dotenv
import os
import math

load_dotenv()

# --- Gemini Setup ---
try:
    import google.generativeai as genai
except ImportError:
    genai = None

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "mysecret123")

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

model = None
if genai and GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-flash-lite-latest")
        print("Gemini ready!")
    except:
        model = None

JOKES = [
    "Why don't scientists trust atoms? Because they make up everything!",
    "What do you call a fake noodle? An impasta!",
    "Why did the scarecrow win an award? Because he was outstanding in his field!",
    "What do you call a bear with no teeth? A gummy bear!"
]

def get_history():
    if "history" not in session:
        session["history"] = [{"role": "assistant", "text": "Hi! Ask me weather, math, jokes, or anything!"}]
    return session["history"]

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json.get("message", "").strip()
    if not user_message:
        return jsonify({"response": "What would you like to know?"})

    history = get_history()
    history.append({"role": "user", "text": user_message})
    lower = user_message.lower()
    response = ""

    # ==================== WEATHER - IMPROVED DETECTION ====================
    weather_keywords = ["weather", "temperature", "temp", "forecast", "rain", "sunny", "cloud", "hot", "cold", "degree", "climate"]
    
    if any(word in lower for word in weather_keywords):
        city = extract_city_improved(user_message)
        if city:
            response = get_weather(city)
        else:
            response = "Which city would you like the weather for? (e.g., 'weather in Mumbai')"
    # ========================================================================

    # ==================== MATH - IMPROVED DETECTION ====================
    elif is_math_query(lower):
        response = handle_math(user_message)
    # ===================================================================

    # Joke
    elif any(w in lower for w in ["joke", "funny", "laugh", "make me laugh"]):
        response = random.choice(JOKES)

    # Time
    elif any(w in lower for w in ["time", "date", "what day"]):
        response = datetime.now().strftime("%B %d, %Y — %I:%M %p")

    # Everything else → Gemini
    else:
        if model:
            try:
                context = "\n".join([f"{m['role'].title()}: {m['text']}" for m in history[-8:]])
                prompt = f"You are a friendly, helpful assistant. Be concise but warm.\n{context}\nUser: {user_message}\nAssistant:"
                resp = model.generate_content(prompt)
                response = resp.text.strip() if hasattr(resp, "text") else "Got a weird reply..."
            except Exception as e:
                response = "I'm having trouble thinking right now. Try again?"
        else:
            response = "I can do weather, math, jokes, and time. Add a Gemini API key for more!"

    history.append({"role": "assistant", "text": response})
    if len(history) > 30:
        session["history"] = history[-25:]
    session.modified = True

    return jsonify({"response": response})


# ==================== IMPROVED CITY EXTRACTION ====================
def extract_city_improved(text):
    """Extract city name from weather query - handles more patterns"""
    text = text.lower()
    
    # Pattern 1: "weather of/in/at/for CITY"
    patterns = [
        r"weather\s+(?:of|in|at|for|)\s+([a-z\s]{2,30})",
        r"(?:temp|temperature)\s+(?:of|in|at|for|)\s+([a-z\s]{2,30})",
        r"(?:what|whats|how)\s+(?:is\s+)?(?:the\s+)?weather\s+(?:of|in|at|for|)\s+([a-z\s]{2,30})",
        r"(?:of|in|at|for)\s+([a-z\s]{2,30})\s+weather",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            city = match.group(1).strip()
            # Clean up common words
            city = re.sub(r'\b(the|a|an|is|was|today|now|currently)\b', '', city).strip()
            if len(city) > 2 and city not in ['me', 'here', 'my', 'there']:
                return city.title()
    
    # Pattern 2: Just city name if message is very short
    words = re.findall(r'[a-z]+', text)
    if len(words) <= 4:
        # Filter out obvious non-city words
        non_city = {'what', 'whats', 'is', 'the', 'weather', 'temp', 'temperature', 'of', 'in', 'at', 'for', 'how'}
        city_words = [w for w in words if w not in non_city]
        if 1 <= len(city_words) <= 3:
            city = ' '.join(city_words).title()
            if len(city) > 2:
                return city
    
    return None


# ==================== IMPROVED MATH DETECTION ====================
def is_math_query(text):
    """Detect if query is math-related"""
    # Direct arithmetic operators
    if re.search(r'\d+\s*[+\-*/^%()]\s*\d+', text):
        return True
    
    # Math keywords
    math_keywords = [
        'factorial', 'calculate', 'compute', 'solve', 'add', 'subtract',
        'multiply', 'divide', 'plus', 'minus', 'times', 'sum', 'difference',
        'product', 'quotient', 'square', 'sqrt', 'power', 'root'
    ]
    
    if any(keyword in text for keyword in math_keywords):
        return True
    
    # "X + Y", "what is X / Y", etc.
    if re.search(r'\d+.*?[+\-*/].*?\d+', text):
        return True
    
    return False


def handle_math(text):
    """Handle various math queries including factorial, basic arithmetic"""
    text_lower = text.lower()
    
    # Factorial
    if 'factorial' in text_lower:
        # Extract number
        match = re.search(r'factorial\s+(?:of\s+)?(\d+)', text_lower)
        if not match:
            match = re.search(r'(\d+)\s+factorial', text_lower)
        
        if match:
            try:
                num = int(match.group(1))
                if num < 0:
                    return "Factorial is only defined for non-negative integers."
                if num > 170:
                    return f"Factorial of {num} is too large to calculate!"
                result = math.factorial(num)
                return f"**{num}! = {result:,}**"
            except:
                return "Couldn't calculate that factorial."
        else:
            return "Please specify a number for factorial (e.g., 'factorial of 9')."
    
    # Square root
    if 'sqrt' in text_lower or 'square root' in text_lower:
        match = re.search(r'(?:sqrt|square root)\s+(?:of\s+)?(\d+(?:\.\d+)?)', text_lower)
        if match:
            try:
                num = float(match.group(1))
                if num < 0:
                    return "Square root of negative numbers is not supported."
                result = math.sqrt(num)
                return f"**√{num} = {result:.4f}**"
            except:
                return "Couldn't calculate that square root."
    
    # Power
    if 'power' in text_lower or '^' in text or '**' in text:
        match = re.search(r'(\d+(?:\.\d+)?)\s*(?:\^|\*\*|to the power of|power)\s*(\d+(?:\.\d+)?)', text_lower)
        if match:
            try:
                base = float(match.group(1))
                exp = float(match.group(2))
                result = base ** exp
                return f"**{base}^{exp} = {result:,}**"
            except:
                return "Couldn't calculate that power."
    
    # Basic arithmetic - improved extraction
    # Remove all non-math text
    clean = re.sub(r'\b(can|you|do|calculate|compute|solve|what|is|the|result|of|equals?)\b', '', text_lower)
    clean = re.sub(r'[^0-9+\-*/().% ]', '', clean).strip()
    
    if clean:
        try:
            # Security: Only allow safe characters
            if not all(c in '0123456789+-*/(). ' for c in clean):
                return "I can only handle basic arithmetic operations (+, -, *, /, parentheses)."
            
            # Evaluate
            result = eval(clean, {"__builtins__": {}})
            return f"**{clean} = {result}**"
        except ZeroDivisionError:
            return "Cannot divide by zero!"
        except:
            return "Couldn't calculate that. Try something like: 43 + 23 or 323/23*323"
    
    return "I can help with math! Try: '5 + 3', 'factorial of 9', 'sqrt of 16', etc."


# ==================== WEATHER FUNCTION ====================
def get_weather(city):
    if not OPENWEATHER_API_KEY:
        return "Weather API key is missing! Add OPENWEATHER_API_KEY to your .env file."
    
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
    
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            d = r.json()
            temp = round(d["main"]["temp"])
            feels = round(d["main"]["feels_like"])
            desc = d["weather"][0]["description"].title()
            humidity = d["main"]["humidity"]
            wind = round(d["wind"]["speed"] * 3.6, 1)  # m/s to km/h
            country = d["sys"].get("country", "")
            
            location = f"{city}, {country}" if country else city
            
            return f"""**{location}**
🌡️ Temperature: {temp}°C (feels like {feels}°C)
☁️ Conditions: {desc}
💧 Humidity: {humidity}%
🌬️ Wind: {wind} km/h"""
        else:
            return f"❌ Couldn't find weather for '{city}'. Please check the city name and try again."
    except requests.exceptions.Timeout:
        return "⏱️ Weather service timed out. Please try again."
    except:
        return "⚠️ Weather service is temporarily unavailable. Please try again later."


if __name__ == "__main__":
    print("🚀 AI Assistant Running → http://127.0.0.1:5000")
    app.run(debug=True)