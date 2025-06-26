import streamlit as st
import pytesseract
import pdfplumber
from docx import Document
from PIL import Image, ImageEnhance
from googletrans import Translator, LANGUAGES
import os
import sqlite3
from datetime import datetime

# Set Tesseract path (uncomment if needed)
# pytesseract.pytesseract.tesseract_cmd = '/opt/homebrew/bin/tesseract'

def preprocess_image(image_path):
    try:
        img = Image.open(image_path)
        img = img.convert('L')
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)
        temp_path = os.path.join('Uploads', f"processed_{os.path.basename(image_path)}")
        img.save(temp_path)
        return temp_path
    except Exception as e:
        return image_path

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

def save_to_history(filename, original_text, translated_text, detected_language, target_language):
    conn = sqlite3.connect('translations.db')
    c = conn.cursor()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute('''INSERT INTO translations (filename, original_text, translated_text, detected_language, target_language, timestamp)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (filename, original_text, translated_text, detected_language, LANGUAGES.get(target_language, "Unknown"), timestamp))
    conn.commit()
    conn.close()

def get_history():
    conn = sqlite3.connect('translations.db')
    c = conn.cursor()
    c.execute('SELECT timestamp, filename, detected_language, target_language, original_text, translated_text FROM translations ORDER BY timestamp DESC')
    history = [{'timestamp': row[0], 'filename': row[1], 'detected_language': row[2], 'target_language': row[3], 'original_text': row[4], 'translated_text': row[5]} for row in c.fetchall()]
    conn.close()
    return history

st.title("File Translator")

# Dark mode toggle
theme = st.radio("Theme", ["Light", "Dark"], index=0)
if theme == "Dark":
    st.markdown('<style>body {background-color: #333; color: #f0f2f5;} .stTextArea textarea {background-color: #444; color: #f0f2f5;}</style>', unsafe_allow_html=True)
else:
    st.markdown('<style>body {background-color: #f0f2f5; color: #333;} .stTextArea textarea {background-color: #fff; color: #333;}</style>', unsafe_allow_html=True)

# Initialize session state
if 'results' not in st.session_state:
    st.session_state.results = []
if 'target_language' not in st.session_state:
    st.session_state.target_language = None

uploaded_files = st.file_uploader("Upload files", type=['jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx', 'txt'], accept_multiple_files=True)
language_options = [(code, name) for code, name in LANGUAGES.items()]
language = st.selectbox("Select Target Language", options=[name for _, name in language_options], format_func=lambda x: x)
language_code = next((code for code, name in language_options if name == language), None)

# Process uploaded files
if uploaded_files and language_code:
    with st.spinner("Processing files..."):
        st.session_state.results = []
        for uploaded_file in uploaded_files:
            if uploaded_file and uploaded_file.name:
                file_path = f"Uploads/{uploaded_file.name}"
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                if file_path.endswith(('.jpg', '.jpeg', '.png')):
                    st.image(file_path, caption=f"Uploaded Image: {uploaded_file.name}")
                text = extract_text(file_path)
                translated_text, detected_language = translate_text(text, language_code)
                st.session_state.results.append({
                    'filename': uploaded_file.name,
                    'original_text': text,
                    'translated_text': translated_text,
                    'detected_language': detected_language
                })
                save_to_history(uploaded_file.name, text, translated_text, detected_language, language_code)
                try:
                    os.remove(file_path)
                except:
                    pass
        st.session_state.target_language = language_code

# Display results
if st.session_state.results:
    for i, result in enumerate(st.session_state.results):
        st.write(f"**File: {result['filename']}**")
        st.write(f"**Detected Language**: {result['detected_language']}")
        st.write("**Extracted Text:**")
        new_text = st.text_area(f"Original_{i}", result['original_text'], height=200, key=f"original_{i}")
        if new_text != result['original_text']:
            st.session_state.results[i]['original_text'] = new_text
            new_translated, new_detected = translate_text(new_text, st.session_state.target_language)
            st.session_state.results[i]['translated_text'] = new_translated
            st.session_state.results[i]['detected_language'] = new_detected
            save_to_history(result['filename'], new_text, new_translated, new_detected, st.session_state.target_language)
        if st.button("Reload Translation", key=f"reload_{i}"):
            with st.spinner("Retranslating..."):
                new_translated, new_detected = translate_text(st.session_state.results[i]['original_text'], st.session_state.target_language)
                st.session_state.results[i]['translated_text'] = new_translated
                st.session_state.results[i]['detected_language'] = new_detected
                save_to_history(result['filename'], st.session_state.results[i]['original_text'], new_translated, new_detected, st.session_state.target_language)
        st.write("**Translated Text:**")
        st.text_area(f"Translated_{i}", result['translated_text'], height=200, key=f"translated_{i}")
        st.download_button(
            label=f"Download {result['filename']}",
            data=result['translated_text'],
            file_name=f"translated_{result['filename']}.txt",
            mime="text/plain",
            key=f"download_{i}"
        )

# Display history
history = get_history()
if history:
    st.write("**Translation History**")
    history_df = st.dataframe([
        {
            'Timestamp': entry['timestamp'],
            'File Name': entry['filename'],
            'Detected Language': entry['detected_language'],
            'Target Language': entry['target_language'],
            'Original Text': entry['original_text'],
            'Translated Text': entry['translated_text']
        } for entry in history
    ])

if not uploaded_files and not st.session_state.results:
    st.error("Please upload at least one file to translate.")