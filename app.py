import streamlit as st
import fitz  # PyMuPDF
from google import genai
from google.genai import types
import os
import tempfile
import time
import json
from arabic_reshaper import reshape
from bidi.algorithm import get_display

# إعداد واجهة المستخدم
st.set_page_config(page_title="مترجم PDF بـ Gemini", layout="wide")

st.title("🚀 مترجم PDF الاحترافي (مدعوم بـ Gemini 2.0)")
st.write("ترجمة النصوص مع الحفاظ على الصور والتنسيق الأصلي للملف.")

# إعداد Gemini API
gemini_key = st.secrets.get("GEMINI_API_KEY")

def get_gemini_client():
    if not gemini_key:
        return None
    try:
        client = genai.Client(api_key=gemini_key)
        return client
    except Exception as e:
        st.error(f"خطأ في تهيئة Gemini Client: {e}")
        return None

client = get_gemini_client()

def translate_batch(texts, client):
    """ترجمة مجموعة من النصوص في طلب واحد مع معالجة ذكية للـ Quota"""
    if not texts or not client:
        return texts
    
    valid_texts = {i: t for i, t in enumerate(texts) if t.strip() and len(t.strip()) >= 2}
    if not valid_texts:
        return texts

    prompt = "Translate the following list of English strings to Arabic. Return the result as a JSON object where keys are the original indices and values are the translated strings. Keep translations concise.\n\n"
    prompt += json.dumps(valid_texts)

    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
                contents=prompt
            )
            
            if response and response.text:
                translated_dict = json.loads(response.text)
                results = list(texts)
                for idx, translated in translated_dict.items():
                    results[int(idx)] = translated
                return results
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                wait_time = (attempt + 1) * 10 # انتظار أطول للـ Free Tier
                st.sidebar.warning(f"تم تجاوز الحصة (Quota). جاري الانتظار {wait_time} ثانية...")
                time.sleep(wait_time)
                continue
            st.sidebar.error(f"خطأ في الترجمة: {e}")
            break
    
    return texts

def process_pdf_dual_page(input_pdf_path, font_path, client):
    """معالجة الملف ليكون (صفحة أصلية تليها صفحة مترجمة)"""
    doc = fitz.open(input_pdf_path)
    output_pdf = fitz.open()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_pages = len(doc)
    
    for page_num in range(total_pages):
        status_text.text(f"جاري معالجة الصفحة {page_num + 1} من {total_pages}...")
        
        # 1. إضافة الصفحة الأصلية كما هي
        output_pdf.insert_pdf(doc, from_page=page_num, to_page=page_num)
        
        # 2. إنشاء نسخة مترجمة من نفس الصفحة
        temp_doc = fitz.open()
        temp_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
        translated_page = temp_doc[0]
        
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
            # استخدام Batch أصغر للـ Free Tier لتجنب الـ Timeout
            batch_size = 15 
            translated_texts = []
            for i in range(0, len(texts_to_translate), batch_size):
                batch = texts_to_translate[i:i+batch_size]
                translated_batch = translate_batch(batch, client)
                translated_texts.extend(translated_batch)
                time.sleep(2) # تأخير بسيط بين الـ Batches لتجنب الـ Rate Limit
            
            for s, translated_text in zip(all_spans, translated_texts):
                reshaped_text = reshape(translated_text)
                bidi_text = get_display(reshaped_text)
                
                rect = fitz.Rect(s["bbox"])
                # مسح النص الأصلي
                translated_page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
                
                font_size = s["size"]
                try:
                    translated_page.insert_text(
                        rect.bl + (0, -1),
                        bidi_text,
                        fontname="f0",
                        fontsize=font_size,
                        fontfile=font_path,
                        color=fitz.pdfcolor["black"]
                    )
                except Exception as e:
                    print(f"خطأ في إدراج النص: {e}")
        
        # إضافة الصفحة المترجمة بعد الصفحة الأصلية
        output_pdf.insert_pdf(temp_doc)
        temp_doc.close()
        progress_bar.progress((page_num + 1) / total_pages)
    
    output_path = "translated_dual_layout.pdf"
    output_pdf.save(output_path)
    output_pdf.close()
    doc.close()
    return output_path

# واجهة المستخدم
if not gemini_key:
    st.error("⚠️ مفتاح Gemini API مفقود. يرجى إضافته في إعدادات Secrets باسم GEMINI_API_KEY.")

uploaded_file = st.file_uploader("ارفع ملف الـ PDF الإنجليزي هنا", type="pdf")

if uploaded_file is not None:
    if st.button("ابدأ الترجمة (صفحة أصلية + صفحة مترجمة)"):
        if not gemini_key:
            st.error("لا يمكن البدء بدون مفتاح API.")
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_input:
                tmp_input.write(uploaded_file.read())
                input_path = tmp_input.name
            
            font_path = "Amiri-Regular.ttf"
            if not os.path.exists(font_path):
                st.error(f"ملف الخط {font_path} غير موجود!")
            else:
                with st.spinner("جاري الترجمة... قد يستغرق الأمر وقتاً بسبب حدود الحصة المجانية (Free Tier)"):
                    try:
                        final_pdf_path = process_pdf_dual_page(input_path, font_path, client)
                        st.success("تمت الترجمة بنجاح!")
                        
                        with open(final_pdf_path, "rb") as f:
                            st.download_button(
                                label="تحميل الملف المدمج (أصل + ترجمة)",
                                data=f,
                                file_name="translated_dual_pages.pdf",
                                mime="application/pdf"
                            )
                    except Exception as e:
                        st.error(f"حدث خطأ: {str(e)}")
                    finally:
                        if os.path.exists(input_path):
                            os.unlink(input_path)
