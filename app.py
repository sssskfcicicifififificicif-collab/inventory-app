import streamlit as st
import pandas as pd
import io

# ضبط إعدادات الصفحة والاتجاه RTL
st.set_page_config(page_title="نظام إدارة المخزون", layout="wide")

# تطبيق تنسيقات CSS لدعم اللغة العربية والاتجاه من اليمين إلى اليسار
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700&display=swap');
    html, body, [class*="css"]  {
        font-family: 'Tajawal', sans-serif;
        direction: rtl;
        text-align: right;
    }
    .stDataFrame { direction: rtl; }
    </style>
""", unsafe_allow_html=True)

st.title("📦 نظام إدارة ومتابعة المخزون")
st.write("قم برفع ملف المنتجات (CSV أو Excel) للبدء في تحليل المخزون.")

# رفع الملف
uploaded_file = st.file_uploader("اختر ملف البيانات", type=["csv", "xlsx"])

if uploaded_file is not None:
    try:
        # قراءة الملف حسب نوعه
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        # التأكد من وجود الأعمدة المطلوبة
        required_columns = ['اسم المنتج', 'السعر', 'الكمية الموجودة', 'التصنيف']
        missing_cols = [col for col in required_columns if col not in df.columns]
        
        if missing_cols:
            st.error(f"⚠️ الملف المرفوع يفتقد إلى الأعمدة التالية: {', '.join(missing_cols)}")
        else:
            # معالجة وتطهير البيانات
            df['السعر'] = pd.to_numeric(df['السعر'], errors='coerce')
            df['الكمية الموجودة'] = pd.to_numeric(df['الكمية الموجودة'], errors='coerce')
            
            # التحقق من وجود أخطاء في البيانات
            invalid_rows = df[df['السعر'].isna() | df['الكمية الموجودة'].isna()]
            if not invalid_rows.empty:
                st.warning(f"⚠️ يوجد {len(invalid_rows)} صفوف تحتوي على أسعار أو كميات غير صحيحة تم استبعادها من الحسابات.")
                df = df.dropna(subset=['السعر', 'الكمية الموجودة'])

            # الحسابات الإضافية
            df['قيمة المخزون'] = df['السعر'] * df['الكمية الموجودة']
            df['حالة المخزون'] = df['الكمية الموجودة'].apply(lambda x: 'منخفض جداً ⚠️' if x < 10 else 'متوفر ✅')

            # الملخص السريع
            total_products = len(df)
            total_units = int(df['الكمية الموجودة'].sum())
            total_val = df['قيمة المخزون'].sum()
            low_stock_count = len(df[df['الكمية الموجودة'] < 10])

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("عدد المنتجات", f"{total_products}")
            col2.metric("إجمالي الوحدات", f"{total_units:,}")
            col3.metric("إجمالي قيمة المخزون", f"${total_val:,.2f}")
            col4.metric("منتجات منخفضة المخزون", f"{low_stock_count}")

            st.divider()

            # أدوات البحث والتصفية
            st.subheader("🔍 البحث والتصفية")
            f_col1, f_col2, f_col3 = st.columns(3)
            
            with f_col1:
                search_term = st.text_input("البحث باسم المنتج")
            with f_col2:
                categories = ['الكل'] + list(df['التصنيف'].unique())
                selected_cat = st.selectbox("التصنيف", categories)
            with f_col3:
                show_low_only = st.checkbox("عرض المنتجات منخفضة المخزون فقط")

            # تطبيق التصفية
            filtered_df = df.copy()
            if search_term:
                filtered_df = filtered_df[filtered_df['اسم المنتج'].astype(str).str.contains(search_term, case=False)]
            if selected_cat != 'الكل':
                filtered_df = filtered_df[filtered_df['التصنيف'] == selected_cat]
            if show_low_only:
                filtered_df = filtered_df[filtered_df['الكمية الموجودة'] < 10]

            # ترتيب البيانات
            sort_by = st.selectbox("ترتيب حسب", ["اسم المنتج", "السعر", "الكمية الموجودة", "قيمة المخزون"])
            filtered_df = filtered_df.sort_values(by=sort_by, ascending=False)

            # عرض الجدول
            st.subheader("📋 جدول المنتجات")
            st.dataframe(filtered_df, use_container_width=True)

            # تصدير التقرير
            st.divider()
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                filtered_df.to_excel(writer, index=False, sheet_name='تقرير المخزون')
            processed_data = output.getvalue()

            st.download_button(
                label="📥 تصدير التقرير إلى Excel",
                data=processed_data,
                file_name='inventory_report.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

    except Exception as e:
        st.error(f"حدث خطأ أثناء قراءة الملف: {e}")
