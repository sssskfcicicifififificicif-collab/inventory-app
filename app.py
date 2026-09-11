import streamlit as st
import pandas as pd
import io
from datetime import datetime, date

# ---------------------------------------------------------
# 1. ضبط إعدادات الصفحة والتنسيق (RTL & CSS)
# ---------------------------------------------------------
st.set_page_config(page_title="نظام إدارة ومتابعة المخزون", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700&display=swap');
    html, body, [class*="css"]  {
        font-family: 'Tajawal', sans-serif;
        direction: rtl;
        text-align: right;
    }
    .stDataFrame { direction: rtl; }
    div[data-baseweb="select"] { direction: rtl; }
    </style>
""", unsafe_allow_html=True)

st.title("📦 نظام إدارة ومتابعة المخزون وحركاته")
st.write("قم برفع ملف المنتجات لإدارة المخزون، تسجيل الحركات، وتتبع الأرصدة والتقارير.")

# ---------------------------------------------------------
# 2. تهيئة البيانات داخل الجلسة (Session State)
# ---------------------------------------------------------
if 'movement_history' not in st.session_state:
    # جدول الحركات: قائمة بها قواميس تحتوي تفاصيل الحركة
    st.session_state['movement_history'] = []

if 'stock_adjustments' not in st.session_state:
    # قاموس لحفظ مجموع الزيادة/النقصان التراكمي لكل منتج {product_name: net_change}
    st.session_state['stock_adjustments'] = {}

# ---------------------------------------------------------
# 3. قسم رفع ملف المنتجات والتحقق منه
# ---------------------------------------------------------
st.divider()
st.subheader("1️⃣ رفع ملف البيانات الرئيسي")
uploaded_file = st.file_uploader("يرجى اختيار ملف المنتجات (بصيغة CSV أو Excel)", type=["csv", "xlsx"])

if uploaded_file is not None:
    try:
        # قراءة الملف
        if uploaded_file.name.endswith('.csv'):
            df_raw = pd.read_csv(uploaded_file)
        else:
            df_raw = pd.read_excel(uploaded_file)

        # فحص الملف الفارغ
        if df_raw.empty:
            st.error("⚠️ الملف المرفوع فارغ تماماً ولا يحتوي على بيانات. يرجى التثبت من الملف وإعادة الرفع.")
            st.stop()

        # فحص الأعمدة المطلوبة
        required_columns = ['اسم المنتج', 'السعر', 'الكمية الموجودة', 'التصنيف']
        missing_cols = [col for col in required_columns if col not in df_raw.columns]
        
        if missing_cols:
            st.error(f"⚠️ الملف يفتقد إلى الأعمدة المطلوبة التالية: ({', '.join(missing_cols)}). يرجى تعديل العناوين في ملف Excel/CSV وإعادة الرفع.")
            st.stop()

        # معالجة الأخطاء والبيانات الخاطئة في الملف
        df = df_raw.copy()
        errors_list = []

        df['اسم المنتج'] = df['اسم المنتج'].fillna('منتج غير مسمى')
        df['التصنيف'] = df['التصنيف'].fillna('غير تصنيف')

        for idx, row in df.iterrows():
            row_num = idx + 2
            p_name = row['اسم المنتج']
            
            price_val = pd.to_numeric(row['السعر'], errors='coerce')
            price_invalid = pd.isna(price_val) or price_val < 0
            
            qty_val = pd.to_numeric(row['الكمية الموجودة'], errors='coerce')
            qty_invalid = pd.isna(qty_val) or qty_val < 0

            if price_invalid and qty_invalid:
                errors_list.append({"رقم الصف": row_num, "اسم المنتج": p_name, "المشكلة": "السعر والكمية غير صالحين"})
            elif price_invalid:
                errors_list.append({"رقم الصف": row_num, "اسم المنتج": p_name, "المشكلة": "السعر غير صالح"})
            elif qty_invalid:
                errors_list.append({"رقم الصف": row_num, "اسم المنتج": p_name, "المشكلة": "الكمية غير صالحة"})

        if errors_list:
            st.warning(f"⚠️ تم العثور على {len(errors_list)} صفوف تحتوي على بيانات غير صالحة. تم استبعادها من الحسابات مع استمرار العمل على بقية المنتجات الصحيحة.")
            st.table(pd.DataFrame(errors_list))

        # تنظيف DataFrame للمنتجات الصحيحة
        df['السعر'] = pd.to_numeric(df['السعر'], errors='coerce')
        df['الكمية الموجودة'] = pd.to_numeric(df['الكمية الموجودة'], errors='coerce')
        valid_df = df.dropna(subset=['السعر', 'الكمية الموجودة']).copy()
        valid_df = valid_df[(valid_df['السعر'] >= 0) & (valid_df['الكمية الموجودة'] >= 0)]

        # دمج الأرصدة المعدلة من الحركات الحالية
        def get_current_stock(row):
            p_name = str(row['اسم المنتج'])
            base_qty = float(row['الكمية الموجودة'])
            adj = st.session_state['stock_adjustments'].get(p_name, 0.0)
            return base_qty + adj

        valid_df['الكمية الحالية'] = valid_df.apply(get_current_stock, axis=1)
        valid_df['قيمة المخزون'] = valid_df['السعر'] * valid_df['الكمية الحالية']
        valid_df['حالة المخزون'] = valid_df['الكمية الحالية'].apply(lambda x: 'منخفض' if x < 10 else 'متوفر')

        # ---------------------------------------------------------
        # 4. قسم إضافة حركة مخزون جديدة
        # ---------------------------------------------------------
        st.divider()
        st.subheader("2️⃣ إضافة حركة مخزون جديدة")
        
        product_names = valid_df['اسم المنتج'].astype(str).unique().tolist()
        
        if not product_names:
            st.info("لا توجد منتجات صالحة لتسجيل حركات عليها.")
        else:
            with st.form(key="add_movement_form", clear_on_submit=True):
                col_p, col_t, col_q, col_d = st.columns(4)
                
                with col_p:
                    selected_product = st.selectbox("اسم المنتج", product_names)
                with col_t:
                    movement_type = st.selectbox("نوع الحركة", ["شراء", "إضافة للمخزون", "بيع", "خصم من المخزون"])
                with col_q:
                    movement_qty = st.number_input("الكمية", min_value=0.0, step=1.0, value=0.0)
                with col_d:
                    movement_date = st.date_input("التاريخ", value=date.today())
                
                note = st.text_input("ملاحظة (اختيارية)", "")
                submit_btn = st.form_submit_button("تسجيل الحركة 💾")
            
            if submit_btn:
                # التحقق من أن الكمية أكبر من الصفر
                if movement_qty <= 0:
                    st.error("⚠️ خطأ: يجب إدخال كمية صحيحة أو عشرية موجبة وتكون أكبر من الصفر.")
                else:
                    # حساب الرصيد الحالي للمنتج المحدد قبل تسجيل الحركة
                    prod_row = valid_df[valid_df['اسم المنتج'].astype(str) == str(selected_product)].iloc[0]
                    current_stock = prod_row['الكمية الحالية']
                    
                    is_addition = movement_type in ["شراء", "إضافة للمخزون"]
                    
                    if not is_addition and movement_qty > current_stock:
                        shortage = movement_qty - current_stock
                        st.error(f"❌ لا يمكن تنفيذ عملية {movement_type}. الرصيد الحالي: {current_stock:g}، والكمية المطلوبة: {movement_qty:g}. (الكمية الناقصة: {shortage:g}).")
                    else:
                        # تحديث الرصيد التراكمي في الجلسة
                        delta = movement_qty if is_addition else -movement_qty
                        st.session_state['stock_adjustments'][selected_product] = st.session_state['stock_adjustments'].get(selected_product, 0.0) + delta
                        
                        new_stock_after = current_stock + delta
                        
                        # تسجيل الحركة في السجل
                        movement_record = {
                            "التاريخ": movement_date.strftime("%Y-%m-%d"),
                            "المنتج": selected_product,
                            "نوع الحركة": movement_type,
                            "الكمية": movement_qty,
                            "الرصيد بعد الحركة": new_stock_after,
                            "الملاحظة": note if note.strip() != "" else "-"
                        }
                        st.session_state['movement_history'].append(movement_record)
                        st.success(f"✅ تم تسجيل حركة ({movement_type}) بمقدار {movement_qty:g} للمنتج '{selected_product}'. الرصيد الجديد: {new_stock_after:g}")
                        st.rerun()

        # ---------------------------------------------------------
        # 5. قسم سجل حركات المخزون والبحث/التصفية
        # ---------------------------------------------------------
        st.divider()
        st.subheader("3️⃣ سجل حركات المخزون")
        
        if not st.session_state['movement_history']:
            st.info("لم يتم تسجيل أي حركات مخزون حتى الآن.")
        else:
            moves_df = pd.DataFrame(st.session_state['movement_history'])
            moves_df['التاريخ_dt'] = pd.to_datetime(moves_df['التاريخ'])

            # فلاتر التصفية
            f1, f2, f3, f4 = st.columns(4)
            with f1:
                search_move_p = st.text_input("🔍 بحث باسم المنتج في الحركات", "")
            with f2:
                move_types_list = ['الكل'] + list(moves_df['نوع الحركة'].unique())
                selected_move_type = st.selectbox("تصفية بنوع الحركة", move_types_list)
            with f3:
                min_date = moves_df['التاريخ_dt'].min().date()
                start_d = st.date_input("تاريخ البداية", value=min_date)
            with f4:
                max_date = moves_df['التاريخ_dt'].max().date()
                end_d = st.date_input("تاريخ النهاية", value=max_date)

            # تطبيق الفلاتر المترابطة
            filtered_moves = moves_df.copy()

            if search_move_p.strip() != "":
                filtered_moves = filtered_moves[filtered_moves['المنتج'].astype(str).str.contains(search_move_p, case=False, na=False)]

            if selected_move_type != 'الكل':
                filtered_moves = filtered_moves[filtered_moves['نوع الحركة'] == selected_move_type]

            filtered_moves = filtered_moves[
                (filtered_moves['التاريخ_dt'].dt.date >= start_d) & 
                (filtered_moves['التاريخ_dt'].dt.date <= end_d)
            ]

            display_moves_cols = ['التاريخ', 'المنتج', 'نوع الحركة', 'الكمية', 'الرصيد بعد الحركة', 'الملاحظة']
            st.dataframe(filtered_moves[display_moves_cols], use_container_width=True)

            # تصدير الحركات إلى Excel (المصفاة فقط)
            output_moves = io.BytesIO()
            with pd.ExcelWriter(output_moves, engine='openpyxl') as writer:
                filtered_moves[display_moves_cols].to_excel(writer, index=False, sheet_name='سجل الحركات')
            moves_excel_data = output_moves.getvalue()

            st.download_button(
                label="📥 تصدير سجل الحركات الحالي إلى Excel",
                data=moves_excel_data,
                file_name='inventory_movements_report.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

        # ---------------------------------------------------------
        # 6. قسم تقرير المنتج التفصيلي
        # ---------------------------------------------------------
        st.divider()
        st.subheader("4️⃣ تقرير المنتج")
        
        if not product_names:
            st.info("لا توجد منتجات لعرض تقاريرها.")
        else:
            rep_product = st.selectbox("اختر المنتج لتقييم حسابه وحركاته", product_names, key="rep_p_select")
            
            # حساب إجماليات المنتج
            prod_row_rep = valid_df[valid_df['اسم المنتج'].astype(str) == str(rep_product)].iloc[0]
            current_p_stock = prod_row_rep['الكمية الحالية']
            
            p_moves = [m for m in st.session_state['movement_history'] if m['المنتج'] == rep_product]
            
            tot_buy = sum(m['الكمية'] for m in p_moves if m['نوع الحركة'] == "شراء")
            tot_sell = sum(m['الكمية'] for m in p_moves if m['نوع الحركة'] == "بيع")
            tot_add = sum(m['الكمية'] for m in p_moves if m['نوع الحركة'] == "إضافة للمخزون")
            tot_sub = sum(m['الكمية'] for m in p_moves if m['نوع الحركة'] == "خصم من المخزون")
            
            rc1, rc2, rc3, rc4, rc5 = st.columns(5)
            rc1.metric("الرصيد الحالي", f"{current_p_stock:g}")
            rc2.metric("إجمالي المشتريات", f"{tot_buy:g}")
            rc3.metric("إجمالي المبيعات", f"{tot_sell:g}")
            rc4.metric("إجمالي الإضافات", f"{tot_add:g}")
            rc5.metric("إجمالي الخصومات", f"{tot_sub:g}")
            
            st.write(f"**حركات المنتج الخاصة بـ ({rep_product}):**")
            if p_moves:
                p_moves_df = pd.DataFrame(p_moves)[['التاريخ', 'نوع الحركة', 'الكمية', 'الرصيد بعد الحركة', 'الملاحظة']]
                st.dataframe(p_moves_df, use_container_width=True)
            else:
                st.caption("لا توجد حركات مسجلة لهذا المنتج بعد.")

        # ---------------------------------------------------------
        # 7. قسم لوحة المنتجات الرئيسية (المكونات القديمة المحسنة)
        # ---------------------------------------------------------
        st.divider()
        st.subheader("5️⃣ لوحة المخزون الرئيسية (المنتجات)")
        
        total_products = len(valid_df)
        total_units = valid_df['الكمية الحالية'].sum()
        total_val = valid_df['قيمة المخزون'].sum()
        low_stock_count = len(valid_df[valid_df['الكمية الحالية'] < 10])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("عدد المنتجات الصحيحة", f"{total_products}")
        m2.metric("إجمالي الوحدات الحالية", f"{total_units:,.0f}")
        m3.metric("إجمالي قيمة المخزون", f"${total_val:,.2f}")
        m4.metric("منتجات منخفضة المخزون", f"{low_stock_count}")

        st.write("#### 🔍 البحث والتصفية والترتيب في المنتجات")
        c1, c2, c3 = st.columns(3)
        with c1:
            search_query = st.text_input("🔍 البحث باسم المنتج (جزئي أو كامل)", "")
        with c2:
            cat_list = ['الكل'] + list(valid_df['التصنيف'].astype(str).unique())
            selected_cat = st.selectbox("التصنيف", cat_list)
        with c3:
            show_low = st.checkbox("عرض المنتجات منخفضة المخزون فقط (< 10)")

        display_df = valid_df.copy()

        if search_query:
            display_df = display_df[display_df['اسم المنتج'].astype(str).str.contains(search_query, case=False, na=False)]
        
        if selected_cat != 'الكل':
            display_df = display_df[display_df['التصنيف'].astype(str) == selected_cat]

        if show_low:
            display_df = display_df[display_df['حالة المخزون'] == 'منخفض']

        o1, o2 = st.columns(2)
        with o1:
            sort_field = st.selectbox("ترتيب حسب العمود", ["اسم المنتج", "السعر", "الكمية الحالية", "قيمة المخزون"])
        with o2:
            sort_order = st.radio("اتجاه الترتيب", ["تنازلي ⬇️", "تصاعدي ⬆️"], horizontal=True)

        is_ascending = True if sort_order == "تصاعدي ⬆️" else False
        display_df = display_df.sort_values(by=sort_field, ascending=is_ascending)

        final_columns = ['اسم المنتج', 'التصنيف', 'السعر', 'الكمية الحالية', 'قيمة المخزون', 'حالة المخزون']
        st.dataframe(display_df[final_columns], use_container_width=True)

        # تصدير تقرير المنتجات
        output_prod = io.BytesIO()
        with pd.ExcelWriter(output_prod, engine='openpyxl') as writer:
            display_df[final_columns].to_excel(writer, index=False, sheet_name='تقرير المنتجات')
        prod_report_data = output_prod.getvalue()

        st.download_button(
            label="📥 تصدير جدول المنتجات الحالي إلى Excel",
            data=prod_report_data,
            file_name='final_inventory_report.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        st.error(f"⚠️ تعذر قراءة الملف: الملف المرفوع غير صالح أو تالف. يرجى التأكد من رفع ملف Excel أو CSV صحيح.")
