import streamlit as st
import fitz  # PyMuPDF
import google.generativeai as genai
import os
import tempfile
from arabic_reshaper import reshape
from bidi.algorithm import get_display

# إعداد Gemini API
# سيتم جلب المفتاح من Secrets في Streamlit Cloud
gemini_key = st.secrets.get("GEMINI_API_KEY")
if gemini_key:
    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    st.warning("الرجاء إضافة GEMINI_API_KEY في إعدادات Secrets لتفعيل الترجمة.")

def translate_text(text):
    if not text.strip() or len(text.strip()) < 2:
        return text
    if not gemini_key:
        return text
        
    try:
        prompt = f"Translate the following English text to Arabic. Keep it concise to fit in the same space. Only return the translated text:\n\n{text}"
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception:
        return text

def process_pdf_layout_preserved(input_pdf_path, font_path):
    doc = fitz.open(input_pdf_path)
    output_pdf = fitz.open()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_pages = len(doc)
    
    for page_num in range(total_pages):
        status_text.text(f"جاري معالجة الصفحة {page_num + 1} من {total_pages}...")
        
        # 1. إضافة الصفحة الأصلية
        output_pdf.insert_pdf(doc, from_page=page_num, to_page=page_num)
        
        # 2. إنشاء نسخة مترجمة
        page = doc.load_page(page_num)
        temp_doc = fitz.open()
        temp_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
        translated_page = temp_doc[0]
        
        blocks = page.get_text("dict")["blocks"]
        
        for b in blocks:
            if "lines" in b:
                for l in b["lines"]:
                    for s in l["spans"]:
                        original_text = s["text"]
                        if original_text.strip():
                            translated_text = translate_text(original_text)
                            reshaped_text = reshape(translated_text)
                            bidi_text = get_display(reshaped_text)
                            
                            rect = fitz.Rect(s["bbox"])
                            translated_page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
                            
                            font_size = s["size"]
                            translated_page.insert_text(
                                rect.bl + (0, -2),
                                bidi_text,
                                fontname="f0",
                                fontsize=font_size,
                                fontfile=font_path,
                                color=fitz.pdfcolor["black"]
                            )
        
        output_pdf.insert_pdf(temp_doc)
        temp_doc.close()
        progress_bar.progress((page_num + 1) / total_pages)
    
    output_path = "translated_layout_preserved.pdf"
    output_pdf.save(output_path)
    output_pdf.close()
    doc.close()
    return output_path

# واجهة المستخدم
st.set_page_config(page_title="مترجم PDF بـ Gemini", layout="wide")

st.title("🚀 مترجم PDF الاحترافي (مدعوم بـ Gemini)")
st.write("ترجمة النصوص مع الحفاظ على الصور والتنسيق الأصلي للملف.")

if not gemini_key:
    st.error("⚠️ مفتاح Gemini API مفقود. يرجى إضافته في الإعدادات باسم GEMINI_API_KEY.")

uploaded_file = st.file_uploader("ارفع ملف الـ PDF الإنجليزي هنا", type="pdf")

if uploaded_file is not None:
    if st.button("ابدأ الترجمة باستخدام Gemini"):
        if not gemini_key:
            st.error("لا يمكن البدء بدون مفتاح API.")
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_input:
                tmp_input.write(uploaded_file.read())
                input_path = tmp_input.name
            
            font_path = "Amiri-Regular.ttf"
            
            with st.spinner("جاري الترجمة باستخدام ذكاء Gemini..."):
                try:
                    final_pdf_path = process_pdf_layout_preserved(input_path, font_path)
                    st.success("تمت الترجمة بنجاح!")
                    
                    with open(final_pdf_path, "rb") as f:
                        st.download_button(
                            label="تحميل الملف المدمج",
                            data=f,
                            file_name="translated_with_gemini.pdf",
                            mime="application/pdf"
                        )
                except Exception as e:
                    st.error(f"حدث خطأ: {str(e)}")
                finally:
                    if os.path.exists(input_path):
                        os.unlink(input_path)
