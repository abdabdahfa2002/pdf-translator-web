import streamlit as st
import fitz  # PyMuPDF
from google import genai
from google.genai import types
from deep_translator import GoogleTranslator
import os
import tempfile
import time
import json
import concurrent.futures
from arabic_reshaper import reshape
from bidi.algorithm import get_display

# إعداد واجهة المستخدم
st.set_page_config(page_title="مترجم PDF الاحترافي", layout="wide")

# إضافة الإهداء الخاص
st.markdown("<h3 style='text-align: center; color: #FF69B4;'>مقدم للطالبة الذكية بنت ابوها رحمة خالد 🥰🌚😁♥️</h3>", unsafe_url_ strawberries=True)

st.title("🚀 مترجم PDF الاحترافي (أصل + ترجمة)")
st.write("ترجمة النصوص مع الحفاظ على التنسيق الأصلي وعرض الصفحات بالتناوب.")

# إعدادات الشريط الجانبي
st.sidebar.header("⚙️ إعدادات الترجمة")
translation_mode = st.sidebar.radio(
    "اختر محرك الترجمة:",
    ("الترجمة الذكية (Gemini)", "الترجمة السريعة (بدون مفتاح API)")
)

# إعداد Gemini API
gemini_key = st.secrets.get("GEMINI_API_KEY")

def get_gemini_client():
    if not gemini_key:
        return None
    try:
        client = genai.Client(api_key=gemini_key)
        return client
    except Exception as e:
        st.sidebar.error(f"خطأ في تهيئة Gemini: {e}")
        return None

client = get_gemini_client()

def translate_text_local(text):
    if not text.strip() or len(text.strip()) < 2:
        return text
    try:
        translated = GoogleTranslator(source='en', target='ar').translate(text)
        return translated
    except Exception:
        return text

def translate_batch_local(texts):
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(translate_text_local, texts))
    return results

def translate_batch_gemini(texts, client):
    if not texts or not client:
        return texts
    valid_texts = {i: t for i, t in enumerate(texts) if t.strip() and len(t.strip()) >= 2}
    if not valid_texts:
        return texts

    prompt = "Translate the following list of English strings to Arabic. Return ONLY a JSON object where keys are the original indices and values are the translated strings. Keep translations professional.\n\n"
    prompt += json.dumps(valid_texts)

    model_name = "gemini-2.5-flash"
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
                contents=prompt
            )
            if response and response.text:
                translated_dict = json.loads(response.text)
                results = list(texts)
                for idx, translated in translated_dict.items():
                    results[int(idx)] = translated
                return results
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep((attempt + 1) * 5)
                continue
            break
    return texts

def process_pdf(input_pdf_path, font_path, client, mode):
    doc = fitz.open(input_pdf_path)
    output_pdf = fitz.open()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_pages = len(doc)
    
    for page_num in range(total_pages):
        status_text.text(f"جاري معالجة الصفحة {page_num + 1} من {total_pages}...")
        
        # 1. إضافة الصفحة الأصلية
        output_pdf.insert_pdf(doc, from_page=page_num, to_page=page_num)
        
        # 2. إنشاء الصفحة المترجمة (نسخة من الأصلية للحفاظ على الجداول والصور)
        temp_doc = fitz.open()
        temp_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
        translated_page = temp_doc[0]
        
        # استخراج النصوص (العودة لنظام Spans المستقر)
        blocks = translated_page.get_text("dict")["blocks"]
        all_spans = []
        texts_to_translate = []
        
        for b in blocks:
            if "lines" in b:
                for l in b["lines"]:
                    for s in l["spans"]:
                        if s["text"].strip():
                            all_spans.append(s)
                            texts_to_translate.append(s["text"])
        
        if texts_to_translate:
            if mode == "الترجمة الذكية (Gemini)":
                batch_size = 40
                translated_texts = []
                for i in range(0, len(texts_to_translate), batch_size):
                    batch = texts_to_translate[i:i+batch_size]
                    translated_texts.extend(translate_batch_gemini(batch, client))
            else:
                translated_texts = translate_batch_local(texts_to_translate)
            
            for s, translated_text in zip(all_spans, translated_texts):
                reshaped_text = reshape(translated_text)
                bidi_text = get_display(reshaped_text)
                
                rect = fitz.Rect(s["bbox"])
                font_size = s["size"]
                
                # مسح النص الأصلي
                translated_page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
                
                try:
                    translated_page.insert_text(
                        rect.bl + (0, -1),
                        bidi_text,
                        fontname="f0",
                        fontsize=font_size,
                        fontfile=font_path,
                        color=fitz.pdfcolor["black"]
                    )
                except Exception:
                    pass
        
        output_pdf.insert_pdf(temp_doc)
        temp_doc.close()
        progress_bar.progress((page_num + 1) / total_pages)
    
    output_path = "translated_output.pdf"
    output_pdf.save(output_path)
    output_pdf.close()
    doc.close()
    return output_path

# واجهة رفع الملفات
uploaded_file = st.file_uploader("ارفع ملف الـ PDF هنا", type="pdf")

if uploaded_file is not None:
    if st.button("ابدأ عملية الترجمة"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_input:
            tmp_input.write(uploaded_file.read())
            input_path = tmp_input.name
        
        font_path = "Amiri-Regular.ttf"
        if not os.path.exists(font_path):
            st.error("ملف الخط Amiri-Regular.ttf مفقود!")
        else:
            with st.spinner(f"جاري الترجمة..."):
                try:
                    final_pdf_path = process_pdf(input_path, font_path, client, translation_mode)
                    if final_pdf_path:
                        st.success("تمت الترجمة بنجاح!")
                        with open(final_pdf_path, "rb") as f:
                            st.download_button(
                                label="تحميل الملف المترجم",
                                data=f,
                                file_name="translated_document.pdf",
                                mime="application/pdf"
                            )
                except Exception as e:
                    st.error(f"حدث خطأ: {e}")
                finally:
                    if os.path.exists(input_path):
                        os.unlink(input_path)
