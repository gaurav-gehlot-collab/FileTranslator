import pytesseract
import pdfplumber
from docx import Document
from PIL import Image, ImageEnhance
import os
from flask import Flask, request, render_template_string, session, send_file
import io
from googletrans import Translator, LANGUAGES
import sqlite3
from datetime import datetime

# Set Tesseract path (uncomment if needed)
# pytesseract.pytesseract.tesseract_cmd = '/opt/homebrew/bin/tesseract'

# Set up Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key'
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Set up SQLite database
def init_db():
    conn = sqlite3.connect('translations.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS translations
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  filename TEXT,
                  original_text TEXT,
                  translated_text TEXT,
                  detected_language TEXT,
                  target_language TEXT,
                  timestamp TEXT)''')
    conn.commit()
    conn.close()

init_db()

# HTML template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>File Translator</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; transition: background-color 0.3s, color 0.3s; }
        body.light { background-color: #f0f2f5; color: #333; }
        body.dark { background-color: #333; color: #f0f2f5; }
        h1 { text-align: center; }
        pre, textarea { background: inherit; padding: 15px; border: 1px solid #ccc; border-radius: 5px; max-height: 400px; overflow-y: auto; width: 100%; box-sizing: border-box; color: inherit; }
        select, input[type="file"], input[type="submit"], input[type="button"] { margin: 10px 0; padding: 8px; border-radius: 4px; width: 100%; box-sizing: border-box; }
        input[type="submit"], input[type="button"] { padding: 10px 20px; background: #4CAF50; color: white; border: none; cursor: pointer; font-size: 16px; }
        input[type="submit"]:hover, input[type="button"]:hover { background: #45a049; }
        .error { color: red; font-weight: bold; }
        form { max-width: 800px; margin: 0 auto; background: inherit; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        a.download-btn { display: inline-block; margin: 10px 5px; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; }
        a.download-btn:hover { background: #0056b3; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { border: 1px solid #ccc; padding: 10px; text-align: left; }
        th { background: #f8f8f8; }
        body.dark th { background: #444; }
        .theme-toggle { position: fixed; top: 10px; right: 10px; }
        .spinner { display: none; border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 30px; height: 30px; animation: spin 1s linear infinite; margin: 20px auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
    <script>
        function toggleTheme() {
            document.body.classList.toggle('dark');
            document.body.classList.toggle('light');
            localStorage.setItem('theme', document.body.classList.contains('dark') ? 'dark' : 'light');
        }
        window.onload = function() {
            if (localStorage.getItem('theme') === 'dark') {
                document.body.classList.add('dark');
            } else {
                document.body.classList.add('light');
            }
            document.getElementById('uploadForm').addEventListener('submit', function() {
                document.getElementById('spinner').style.display = 'block';
            });
        }
    </script>
</head>
<body class="light">
    <button onclick="toggleTheme()" class="theme-toggle">Change Theme</button>
    <h1>File Translator</h1>
    <form id="uploadForm" method="POST" enctype="multipart/form-data" action="/">
        <input type="file" name="files" accept=".jpg,.jpeg,.png,.pdf,.doc,.docx,.txt" multiple required>
        <select name="language" required>
            <option value="">Select Target Language</option>
            {% for code, name in languages.items() %}
                <option value="{{ code }}" {% if code == selected_language %}selected{% endif %}>{{ name }}</option>
            {% endfor %}
        </select>
        <input type="submit" value="Translate">
    </form>
    <div id="spinner" class="spinner"></div>
    {% if results %}
        <table>
            <tr>
                <th>File Name</th>
                <th>Detected Language</th>
                <th>Original Text</th>
                <th>Translated Text</th>
                <th>Actions</th>
            </tr>
            {% for result in results %}
                <tr>
                    <td>{{ result.filename }}</td>
                    <td>{{ result.detected_language }}</td>
                    <td>
                        <form method="POST" action="/retranslate">
                            <input type="hidden" name="language" value="{{ selected_language }}">
                            <input type="hidden" name="filename" value="{{ result.filename }}">
                            <textarea name="edited_text" rows="5">{{ result.original_text }}</textarea>
                            <input type="submit" value="Reload Translation">
                        </form>
                    </td>
                    <td><pre>{{ result.translated_text }}</pre></td>
                    <td><a href="/download/{{ loop.index0 }}" class="download-btn">Download</a></td>
                </tr>
            {% endfor %}
        </table>
    {% endif %}
    {% if history %}
        <h2>Translation History</h2>
        <table>
            <tr>
                <th>Timestamp</th>
                <th>File Name</th>
                <th>Detected Language</th>
                <th>Target Language</th>
                <th>Original Text</th>
                <th>Translated Text</th>
            </tr>
            {% for entry in history %}
                <tr>
                    <td>{{ entry.timestamp }}</td>
                    <td>{{ entry.filename }}</td>
                    <td>{{ entry.detected_language }}</td>
                    <td>{{ entry.target_language }}</td>
                    <td><pre>{{ entry.original_text }}</pre></td>
                    <td><pre>{{ entry.translated_text }}</pre></td>
                </tr>
            {% endfor %}
        </table>
    {% endif %}
    {% if error %}
        <p class="error">{{ error }}</p>
    {% endif %}
</body>
</html>
'''

# Function to preprocess image
def preprocess_image(image_path):
    try:
        img = Image.open(image_path)
        img = img.convert('L')
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)
        temp_path = os.path.join(UPLOAD_FOLDER, f"processed_{os.path.basename(image_path)}")
        img.save(temp_path)
        return temp_path
    except Exception as e:
        return image_path

# Function to extract text from files
def extract_text(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ['.jpg', '.jpeg', '.png']:
        try:
            processed_path = preprocess_image(file_path)
            text = pytesseract.image_to_string(Image.open(processed_path))
            if processed_path != file_path:
                os.remove(processed_path)
            return text if text.strip() else "No text found in image"
        except Exception as e:
            return f"Error processing image: {str(e)}"
    elif ext == '.pdf':
        try:
            with pdfplumber.open(file_path) as pdf:
                text = ''
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + '\n'
                return text if text.strip() else "No text found in PDF"
        except Exception as e:
            return f"Error processing PDF: {str(e)}"
    elif ext in ['.doc', '.docx']:
        try:
            doc = Document(file_path)
            text = '\n'.join([para.text for para in doc.paragraphs if para.text.strip()])
            return text if text.strip() else "No text found in DOC"
        except Exception as e:
            return f"Error processing DOC: {str(e)}"
    elif ext == '.txt':
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                text = file.read()
                return text if text.strip() else "No text found in TXT"
        except Exception as e:
            return f"Error processing TXT: {str(e)}"
    else:
        return "Unsupported file format"

# Function to translate text with language detection
def translate_text(text, target_language):
    if not text or text.startswith("Error") or text.startswith("No text found"):
        return text, "N/A"
    try:
        translator = Translator()
        detected = translator.detect(text)
        language = LANGUAGES.get(detected.lang, "Unknown") if detected.lang else "Unknown"
        translated = translator.translate(text, dest=target_language)
        return translated.text, language
    except Exception as e:
        return f"Error during translation: {str(e)}", "N/A"

# Function to save translation to history
def save_to_history(filename, original_text, translated_text, detected_language, target_language):
    conn = sqlite3.connect('translations.db')
    c = conn.cursor()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute('''INSERT INTO translations (filename, original_text, translated_text, detected_language, target_language, timestamp)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (filename, original_text, translated_text, detected_language, LANGUAGES.get(target_language, "Unknown"), timestamp))
    conn.commit()
    conn.close()

# Function to get translation history
def get_history():
    conn = sqlite3.connect('translations.db')
    c = conn.cursor()
    c.execute('SELECT timestamp, filename, detected_language, target_language, original_text, translated_text FROM translations ORDER BY timestamp DESC')
    history = [{'timestamp': row[0], 'filename': row[1], 'detected_language': row[2], 'target_language': row[3], 'original_text': row[4], 'translated_text': row[5]} for row in c.fetchall()]
    conn.close()
    return history

# Flask route for file upload and initial translation
@app.route('/', methods=['GET', 'POST'])
def upload_file():
    results = []
    error = None
    selected_language = session.get('selected_language', '')
    history = get_history()

    if request.method == 'POST':
        files = request.files.getlist('files')
        target_language = request.form.get('language')

        if not files or all(not f or not f.filename for f in files):
            error = "No files uploaded or invalid files."
        elif not target_language:
            error = "Please select a target language."
        elif target_language not in LANGUAGES:
            error = "Selected language is not supported."
        else:
            session['results'] = []
            for file in files:
                if file and file.filename and file.filename.strip():
                    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
                    file.save(file_path)

                    # Extract and translate
                    original_text = extract_text(file_path)
                    translated_text, detected_language = translate_text(original_text, target_language)
                    session['results'].append({
                        'filename': file.filename,
                        'original_text': original_text,
                        'translated_text': translated_text,
                        'detected_language': detected_language
                    })
                    save_to_history(file.filename, original_text, translated_text, detected_language, target_language)

                    # Clean up
                    try:
                        os.remove(file_path)
                    except:
                        pass
                else:
                    error = f"Invalid file: {file.filename if file else 'None'}"
            session['selected_language'] = target_language
            results = session.get('results', [])

    return render_template_string(HTML_TEMPLATE, languages=LANGUAGES, results=results, error=error, selected_language=selected_language, history=history)

# Flask route for retranslating edited text
@app.route('/retranslate', methods=['POST'])
def retranslate():
    edited_text = request.form.get('edited_text')
    target_language = request.form.get('language')
    filename = request.form.get('filename')
    error = None
    results = session.get('results', [])
    history = get_history()

    if not edited_text:
        error = "No text provided for translation."
    elif not target_language or target_language not in LANGUAGES:
        error = "Invalid target language."
    else:
        translated_text, detected_language = translate_text(edited_text, target_language)
        for result in results:
            if result['filename'] == filename:
                result['original_text'] = edited_text
                result['translated_text'] = translated_text
                result['detected_language'] = detected_language
                break
        session['results'] = results
        session['selected_language'] = target_language
        save_to_history(filename, edited_text, translated_text, detected_language, target_language)

    return render_template_string(HTML_TEMPLATE, languages=LANGUAGES, results=results, error=error, selected_language=target_language, history=history)

# Route for downloading translated text
@app.route('/download/<int:index>')
def download_file(index):
    results = session.get('results', [])
    if index < len(results):
        result = results[index]['translated_text']
        buffer = io.StringIO(result)
        buffer.seek(0)
        return send_file(
            io.BytesIO(buffer.getvalue().encode('utf-8')),
            download_name=f"translated_{results[index]['filename']}.txt",
            as_attachment=True
        )
    return "File not found", 404

# Run the app
if __name__ == '__main__':
    app.run(debug=True)