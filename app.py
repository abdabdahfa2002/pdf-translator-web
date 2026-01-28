import streamlit as st
import fitz  # PyMuPDF
from openai import OpenAI
import os
import tempfile
from arabic_reshaper import reshape
from bidi.algorithm import get_display

# إعداد عميل OpenAI
client = OpenAI()

def translate_text(text):
    if not text.strip() or len(text.strip()) < 2:
        return text
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are a professional translator. Translate the following English text to Arabic. Keep it concise to fit in the same space. Only return the translated text."},
                {"role": "user", "content": text}
            ]
        )
        return response.choices[0].message.content
    except Exception:
        return text

def process_pdf_layout_preserved(input_pdf_path, font_path):
    # فتح الملف الأصلي
    doc = fitz.open(input_pdf_path)
    output_pdf = fitz.open()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_pages = len(doc)
    
    for page_num in range(total_pages):
        status_text.text(f"جاري معالجة الصفحة {page_num + 1} من {total_pages}...")
        
        # 1. إضافة الصفحة الأصلية أولاً كما طلب المستخدم
        output_pdf.insert_pdf(doc, from_page=page_num, to_page=page_num)
        
        # 2. إنشاء نسخة مترجمة من نفس الصفحة
        # نقوم بنسخ الصفحة الأصلية للحفاظ على الصور والأشكال
        page = doc.load_page(page_num)
        
        # إنشاء ملف مؤقت للصفحة المترجمة
        temp_doc = fitz.open()
        temp_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
        translated_page = temp_doc[0]
        
        # استخراج النصوص مع إحداثياتها
        blocks = page.get_text("dict")["blocks"]
        
        for b in blocks:
            if "lines" in b:
                for l in b["lines"]:
                    for s in l["spans"]:
                        original_text = s["text"]
                        if original_text.strip():
                            # ترجمة النص
                            translated_text = translate_text(original_text)
                            
                            # تجهيز النص العربي (Reshaping & Bidi)
                            reshaped_text = reshape(translated_text)
                            bidi_text = get_display(reshaped_text)
                            
                            # مسح النص القديم (رسم مستطيل أبيض فوقه)
                            rect = fitz.Rect(s["bbox"])
                            translated_page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
                            
                            # كتابة النص المترجم في نفس المكان
                            # نحاول مطابقة حجم الخط
                            font_size = s["size"]
                            translated_page.insert_text(
                                rect.bl + (0, -2), # تعديل طفيف للموقع
                                bidi_text,
                                fontname="f0", # سنقوم بتعريف الخط لاحقاً
                                fontsize=font_size,
                                fontfile=font_path,
                                color=fitz.pdfcolor["black"]
                            )
        
        # دمج الصفحة المترجمة في الملف النهائي
        output_pdf.insert_pdf(temp_doc)
        temp_doc.close()
        
        progress_bar.progress((page_num + 1) / total_pages)
    
    output_path = "translated_layout_preserved.pdf"
    output_pdf.save(output_path)
    output_pdf.close()
    doc.close()
    return output_path

# واجهة المستخدم
st.set_page_config(page_title="مترجم PDF الاحترافي", layout="wide")

st.title("🎨 مترجم PDF مع الحفاظ على التنسيق")
st.write("هذا الإصدار يقوم بترجمة النصوص مع الحفاظ على الصور والأشكال والخلفيات الأصلية.")

uploaded_file = st.file_uploader("ارفع ملف الـ PDF الإنجليزي هنا", type="pdf")

if uploaded_file is not None:
    if st.button("ابدأ الترجمة الاحترافية"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_input:
            tmp_input.write(uploaded_file.read())
            input_path = tmp_input.name
        
        font_path = "/home/ubuntu/Amiri-Regular.ttf"
        
        with st.spinner("جاري تحليل الصفحات وترجمة النصوص مع الحفاظ على التنسيق..."):
            try:
                final_pdf_path = process_pdf_layout_preserved(input_path, font_path)
                st.success("تمت الترجمة بنجاح! تم الحفاظ على الصور والأشكال.")
                
                with open(final_pdf_path, "rb") as f:
                    st.download_button(
                        label="تحميل الملف المدمج (أصل + مترجم)",
                        data=f,
                        file_name="translated_with_layout.pdf",
                        mime="application/pdf"
                    )
            except Exception as e:
                st.error(f"حدث خطأ أثناء المعالجة: {str(e)}")
            finally:
                if os.path.exists(input_path):
                    os.unlink(input_path)
