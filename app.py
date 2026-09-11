import streamlit as st
import pandas as pd
import io

# ضبط إعدادات الصفحة والاتجاه RTL
st.set_page_config(page_title="نظام إدارة ومتابعة المخزون", layout="wide")

# تنسيقات CSS لدعم اللغة العربية والواجهة النظيفة
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700&display=swap');
    html, body, [class*="css"]  {
        font-family: 'Tajawal', sans-serif;
        direction: rtl;
        text-align: right;
    }
    .stDataFrame { direction: rtl; }
    .step-box {
        background-color: #f0f2f6;
        padding: 10px 15px;
        border-radius: 8px;
        margin-bottom: 20px;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📦 نظام إدارة ومتابعة المخزون")
st.write("خطوات العمل: **1. رفع الملف** ⬅️ **2. مراجعة التنبيهات** ⬅️ **3. ملخص المخزون** ⬅️ **4. البحث والتصفية** ⬅️ **5. تصدير التقرير**")

# 1. رفع الملف
st.divider()
st.subheader("1️⃣ رفع ملف البيانات")
uploaded_file = st.file_uploader("يرجى اختيار ملف المنتجات (بصيغة CSV أو Excel)", type=["csv", "xlsx"])

if uploaded_file is not None:
    try:
        # قراءة الملف
        if uploaded_file.name.endswith('.csv'):
            df_raw = pd.read_csv(uploaded_file)
        else:
            df_raw = pd.read_excel(uploaded_file)

        # التحقق من الملف الفارغ
        if df_raw.empty:
            st.error("⚠️ الملف المرفوع فارغ تماماً ولا يحتوي على بيانات. يرجى التثبت من الملف وإعادة الرفع.")
            st.stop()

        # التحقق من وجود الأعمدة المطلوبة
        required_columns = ['اسم المنتج', 'السعر', 'الكمية الموجودة', 'التصنيف']
        missing_cols = [col for col in required_columns if col not in df_raw.columns]
        
        if missing_cols:
            st.error(f"⚠️ الملف يفتقد إلى الأعمدة المطلوبة التالية: ({', '.join(missing_cols)}). يرجى تعديل العناوين في ملف Excel/CSV وإعادة الرفع.")
            st.stop()

        # 2. مراجعة البيانات وفحص الأخطاء
        st.divider()
        st.subheader("2️⃣ مراجعة البيانات والأخطاء")
        
        # إنشاء نسخ للبيانات والمعالجة
        df = df_raw.copy()
        errors_list = []

        # معالجة الأسماء الفارغة
        df['اسم المنتج'] = df['اسم المنتج'].fillna('منتج غير مسمى')
        
        # معالجة التصنيفات الفارغة
        df['التصنيف'] = df['التصنيف'].fillna('غير تصنيف')

        # فحص الأسعار والكميات
        for idx, row in df.iterrows():
            row_num = idx + 2 # مراعاة صف العناوين في Excel
            p_name = row['اسم المنتج']
            
            # فحص السعر
            price_val = pd.to_numeric(row['السعر'], errors='coerce')
            price_invalid = pd.isna(price_val) or price_val < 0
            
            # فحص الكمية
            qty_val = pd.to_numeric(row['الكمية الموجودة'], errors='coerce')
            qty_invalid = pd.isna(qty_val) or qty_val < 0

            if price_invalid and qty_invalid:
                errors_list.append({"رقم الصف": row_num, "اسم المنتج": p_name, "المشكلة": "السعر والكمية غير صالحين"})
            elif price_invalid:
                errors_list.append({"رقم الصف": row_num, "اسم المنتج": p_name, "المشكلة": "السعر غير صالح"})
            elif qty_invalid:
                errors_list.append({"رقم الصف": row_num, "اسم المنتج": p_name, "المشكلة": "الكمية غير صالحة"})

        # عرض التنبيهات إن وجدت
        if errors_list:
            st.warning(f"⚠️ تم العثور على {len(errors_list)} صفوف تحتوي على بيانات غير صالحة. تم استبعادها من الحسابات مع استمرار العمل على بقية المنتجات الصحيحة.")
            st.table(pd.DataFrame(errors_list))
        else:
            st.success("✅ جميع البيانات في الملف صالحة وتمت قراءتها بنجاح!")

        # تصفية الصفوف الصحيحة للحسابات
        df['السعر'] = pd.to_numeric(df['السعر'], errors='coerce')
        df['الكمية الموجودة'] = pd.to_numeric(df['الكمية الموجودة'], errors='coerce')
        valid_df = df.dropna(subset=['السعر', 'الكمية الموجودة']).copy()
        valid_df = valid_df[(valid_df['السعر'] >= 0) & (valid_df['الكمية الموجودة'] >= 0)]

        # الحسابات الأساسية
        valid_df['قيمة المخزون'] = valid_df['السعر'] * valid_df['الكمية الموجودة']
        valid_df['حالة المخزون'] = valid_df['الكمية الموجودة'].apply(lambda x: 'منخفض' if x < 10 else 'متوفر')

        # 3. لوحة المخزون (الملخص)
        st.divider()
        st.subheader("3️⃣ لوحة المخزون (الملخص السريع)")
        
        total_products = len(valid_df)
        total_units = int(valid_df['الكمية الموجودة'].sum())
        total_val = valid_df['قيمة المخزون'].sum()
        low_stock_count = len(valid_df[valid_df['الكمية الموجودة'] < 10])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("عدد المنتجات الصحيحة", f"{total_products}")
        m2.metric("إجمالي الوحدات", f"{total_units:,}")
        m3.metric("إجمالي قيمة المخزون", f"${total_val:,.2f}")
        m4.metric("منتجات منخفضة المخزون", f"{low_stock_count}")

        # 4. البحث والتصفية
        st.divider()
        st.subheader("4️⃣ البحث والتصفية والترتيب")
        
        c1, c2, c3 = st.columns(3)
        with c1:
            search_query = st.text_input("🔍 البحث باسم المنتج (جزئي أو كامل)", "")
        with c2:
            cat_list = ['الكل'] + list(valid_df['التصنيف'].astype(str).unique())
            selected_cat = st.selectbox("التصنيف", cat_list)
        with c3:
            show_low = st.checkbox("عرض المنتجات منخفضة المخزون فقط (< 10)")

        # تطبيق البحث والتصفية
        display_df = valid_df.copy()

        if search_query:
            display_df = display_df[display_df['اسم المنتج'].astype(str).str.contains(search_query, case=False, na=False)]
        
        if selected_cat != 'الكل':
            display_df = display_df[display_df['التصنيف'].astype(str) == selected_cat]

        if show_low:
            display_df = display_df[display_df['حالة المخزون'] == 'منخفض']

        # الترتيب
        o1, o2 = st.columns(2)
        with o1:
            sort_field = st.selectbox("ترتيب حسب العمود", ["اسم المنتج", "السعر", "الكمية الموجودة", "قيمة المخزون"])
        with o2:
            sort_order = st.radio("اتجاه الترتيب", ["تنازلي ⬇️", "تصاعدي ⬆️"], horizontal=True)

        is_ascending = True if sort_order == "تصاعدي ⬆️" else False
        display_df = display_df.sort_values(by=sort_field, ascending=is_ascending)

        # عرض البيانات
        final_columns = ['اسم المنتج', 'التصنيف', 'السعر', 'الكمية الموجودة', 'قيمة المخزون', 'حالة المخزون']
        st.dataframe(display_df[final_columns], use_container_width=True)

        # 5. تصدير التقرير
        st.divider()
        st.subheader("5️⃣ تصدير التقرير النهائي")
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            display_df[final_columns].to_excel(writer, index=False, sheet_name='تقرير المخزون')
        report_data = output.getvalue()

        st.download_button(
            label="📥 تصدير التقرير التفاعلي الحالي إلى Excel",
            data=report_data,
            file_name='final_inventory_report.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        st.error(f"⚠️ تعذر قراءة الملف: الملف المرفوع غير صالح أو تالف. يرجى التأكد من رفع ملف Excel أو CSV صحيح.")
