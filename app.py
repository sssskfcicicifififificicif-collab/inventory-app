import streamlit as st
import pandas as pd
import io
from datetime import datetime, date

# ---------------------------------------------------------
# 1. ضبط إعدادات الصفحة والتنسيق (RTL & CSS)
# ---------------------------------------------------------
st.set_page_config(page_title="نظام إدارة ومتابعة المخزون والمبيعات", layout="wide")

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
    .stNumberInput { direction: ltr; }
    </style>
""", unsafe_allow_html=True)

st.title("📦 نظام إدارة المخزون وحركاته والمبيعات")
st.write("قم برفع ملف المنتجات لإدارة المخزون، تسجيل حركات المخزون، إنشاء فواتير المبيعات، وتتبع التقارير.")

# ---------------------------------------------------------
# 2. تهيئة البيانات داخل الجلسة (Session State)
# ---------------------------------------------------------
if 'movement_history' not in st.session_state:
    st.session_state['movement_history'] = []

if 'stock_adjustments' not in st.session_state:
    st.session_state['stock_adjustments'] = {}

if 'invoices' not in st.session_state:
    # قائمة الفواتير: [{"invoice_id": 1001, "date": "2026-09-12", "customer": "عميل", "total": 2500, "items": [...]}]
    st.session_state['invoices'] = []

if 'invoice_counter' not in st.session_state:
    st.session_state['invoice_counter'] = 1001

if 'cart_items' not in st.session_state:
    st.session_state['cart_items'] = []

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

        if df_raw.empty:
            st.error("⚠️ الملف المرفوع فارغ تماماً ولا يحتوي على بيانات. يرجى التثبت من الملف وإعادة الرفع.")
            st.stop()

        required_columns = ['اسم المنتج', 'السعر', 'الكمية الموجودة', 'التصنيف']
        missing_cols = [col for col in required_columns if col not in df_raw.columns]
        
        if missing_cols:
            st.error(f"⚠️ الملف يفتقد إلى الأعمدة المطلوبة التالية: ({', '.join(missing_cols)}). يرجى تعديل العناوين في ملف Excel/CSV وإعادة الرفع.")
            st.stop()

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

        df['السعر'] = pd.to_numeric(df['السعر'], errors='coerce')
        df['الكمية الموجودة'] = pd.to_numeric(df['الكمية الموجودة'], errors='coerce')
        valid_df = df.dropna(subset=['السعر', 'الكمية الموجودة']).copy()
        valid_df = valid_df[(valid_df['السعر'] >= 0) & (valid_df['الكمية الموجودة'] >= 0)]

        # حساب الأرصدة الحالية بالدمج مع حركة المخزون والمبيعات
        def get_current_stock(row):
            p_name = str(row['اسم المنتج'])
            base_qty = float(row['الكمية الموجودة'])
            adj = st.session_state['stock_adjustments'].get(p_name, 0.0)
            return base_qty + adj

        valid_df['الكمية الحالية'] = valid_df.apply(get_current_stock, axis=1)
        valid_df['قيمة المخزون'] = valid_df['السعر'] * valid_df['الكمية الحالية']
        valid_df['حالة المخزون'] = valid_df['الكمية الحالية'].apply(lambda x: 'منخفض' if x < 10 else 'متوفر')

        product_names = valid_df['اسم المنتج'].astype(str).unique().tolist()
        product_price_map = dict(zip(valid_df['اسم المنتج'].astype(str), valid_df['السعر']))
        product_stock_map = dict(zip(valid_df['اسم المنتج'].astype(str), valid_df['الكمية الحالية']))

        # ---------------------------------------------------------
        # 4. قسم إنشاء فاتورة مبيعات جديدة
        # ---------------------------------------------------------
        st.divider()
        st.subheader("2️⃣ إنشاء فاتورة مبيعات جديدة 🛒")

        if not product_names:
            st.info("لا توجد منتجات صالحة لبدء المبيعات.")
        else:
            inv_col1, inv_col2, inv_col3 = st.columns(3)
            with inv_col1:
                st.text_input("رقم الفاتورة", value=str(st.session_state['invoice_counter']), disabled=True)
            with inv_col2:
                sale_date = st.date_input("تاريخ الفاتورة", value=date.today())
            with inv_col3:
                customer_name = st.text_input("اسم العميل (اختياري)", "")

            st.write("---")
            st.write("**إضافة منتجات للفاتورة:**")
            
            p_c1, p_c2, p_c3, p_c4 = st.columns([3, 2, 2, 2])
            with p_c1:
                sel_p = st.selectbox("اختر المنتج", product_names, key="sale_p_select")
            with p_c2:
                default_price = float(product_price_map.get(sel_p, 0.0))
                sale_price = st.number_input("سعر البيع للوحدة", min_value=0.0, value=default_price, step=0.5, key="sale_price_input")
            with p_c3:
                sale_qty = st.number_input("الكمية المطلوبة", min_value=0.0, value=1.0, step=1.0, key="sale_qty_input")
            with p_c4:
                st.write("")
                st.write("")
                add_item_btn = st.button("➕ إضافة للفاتورة")

            if add_item_btn:
                if sale_qty <= 0:
                    st.error("⚠️ يجب أن تكون الكمية أكبر من الصفر.")
                elif sale_price < 0:
                    st.error("⚠️ لا يمكن أن يكون سعر البيع بالسالب.")
                else:
                    curr_stk = product_stock_map.get(sel_p, 0.0)
                    # احتساب الكميات المضافة مسبقاً بنفس الفاتورة
                    already_in_cart = sum(item['qty'] for item in st.session_state['cart_items'] if item['product'] == sel_p)
                    total_req = already_in_cart + sale_qty
                    
                    if total_req > curr_stk:
                        st.error(f"❌ لا توجد كمية كافية للمنتج '{sel_p}'. المخزون المتوفر: {curr_stk:g}، الكمية المطلوبة بالإجمالي: {total_req:g}.")
                    else:
                        st.session_state['cart_items'].append({
                            "product": sel_p,
                            "price": sale_price,
                            "qty": sale_qty,
                            "subtotal": sale_price * sale_qty
                        })
                        st.success(f"تمت إضافة {sale_qty:g} من '{sel_p}' إلى الفاتورة.")
                        st.rerun()

            # عرض الجدول الحالي لبنود الفاتورة
            if st.session_state['cart_items']:
                st.write("#### 📋 محتويات الفاتورة الحالية:")
                cart_df = pd.DataFrame(st.session_state['cart_items'])
                cart_df.columns = ["المنتج", "سعر الوحدة", "الكمية", "الإجمالي"]
                st.dataframe(cart_df, use_container_width=True)

                grand_total = sum(item['subtotal'] for item in st.session_state['cart_items'])
                st.markdown(f"### 💰 **إجمالي الفاتورة: ${grand_total:,.2f}**")

                btn_col1, btn_col2 = st.columns([2, 8])
                with btn_col1:
                    save_inv_btn = st.button("💾 حفظ وتأكيد الفاتورة", type="primary")
                with btn_col2:
                    clear_cart_btn = st.button("🗑️ إفراغ الفاتورة")

                if clear_cart_btn:
                    st.session_state['cart_items'] = []
                    st.rerun()

                if save_inv_btn:
                    # فحص الذري (Atomic Check) لجميع المنتجات قبل الحفظ
                    stock_error = False
                    for item in st.session_state['cart_items']:
                        p_name = item['product']
                        req_q = item['qty']
                        available = product_stock_map.get(p_name, 0.0)
                        if req_q > available:
                            st.error(f"❌ فشل حفظ الفاتورة بالكامل! المنتج '{p_name}' لا يملك مخزون كافي. المتوفر: {available:g}، المطلوب: {req_q:g}.")
                            stock_error = True
                            break

                    if not stock_error:
                        # تنفيذ العملية بالكامل
                        inv_id = st.session_state['invoice_counter']
                        formatted_date = sale_date.strftime("%Y-%m-%d")
                        cust_name_final = customer_name.strip() if customer_name.strip() != "" else "عميل نقد"

                        invoice_record = {
                            "invoice_id": inv_id,
                            "date": formatted_date,
                            "customer": cust_name_final,
                            "item_count": len(st.session_state['cart_items']),
                            "total": grand_total,
                            "items": list(st.session_state['cart_items'])
                        }

                        # خصم المخزون وتسجيل حركات المخزون لكل منتج في الفاتورة
                        for item in st.session_state['cart_items']:
                            p_name = item['product']
                            p_qty = item['qty']
                            
                            st.session_state['stock_adjustments'][p_name] = st.session_state['stock_adjustments'].get(p_name, 0.0) - p_qty
                            new_stk = product_stock_map.get(p_name, 0.0) - p_qty
                            
                            move_record = {
                                "التاريخ": formatted_date,
                                "المنتج": p_name,
                                "نوع الحركة": "بيع",
                                "الكمية": p_qty,
                                "الرصيد بعد الحركة": new_stk,
                                "الملاحظة": f"فاتورة مبيعات رقم #{inv_id}"
                            }
                            st.session_state['movement_history'].append(move_record)

                        st.session_state['invoices'].append(invoice_record)
                        st.session_state['invoice_counter'] += 1
                        st.session_state['cart_items'] = []

                        st.success(f"✅ تم حفظ الفاتورة رقم #{inv_id} بنجاح، وتحديث رصيد وسجل حركات المخزون!")
                        st.rerun()
            else:
                st.caption("لم يتم إضافة منتجات بعد لهذه الفاتورة.")

        # ---------------------------------------------------------
        # 5. قسم فواتير المبيعات وتفاصيلها
        # ---------------------------------------------------------
        st.divider()
        st.subheader("3️⃣ فواتير المبيعات وتفاصيلها 🧾")

        if not st.session_state['invoices']:
            st.info("لا توجد فواتير مبيعات مسجلة حتى الآن.")
        else:
            invoices_list = []
            for inv in st.session_state['invoices']:
                invoices_list.append({
                    "رقم الفاتورة": inv["invoice_id"],
                    "التاريخ": inv["date"],
                    "العميل": inv["customer"],
                    "عدد المنتجات": inv["item_count"],
                    "إجمالي الفاتورة": inv["total"]
                })
            
            inv_df = pd.DataFrame(invoices_list)
            inv_df['التاريخ_dt'] = pd.to_datetime(inv_df['التاريخ'])

            s_col1, s_col2, s_col3, s_col4 = st.columns(4)
            with s_col1:
                search_inv_id = st.text_input("🔍 البحث برقم الفاتورة", "")
            with s_col2:
                search_cust = st.text_input("🔍 البحث باسم العميل", "")
            with s_col3:
                min_inv_d = inv_df['التاريخ_dt'].min().date()
                inv_start_d = st.date_input("تاريخ البداية للفواتير", value=min_inv_d)
            with s_col4:
                max_inv_d = inv_df['التاريخ_dt'].max().date()
                inv_end_d = st.date_input("تاريخ النهاية للفواتير", value=max_inv_d)

            filtered_inv = inv_df.copy()

            if search_inv_id.strip() != "":
                filtered_inv = filtered_inv[filtered_inv['رقم الفاتورة'].astype(str).str.contains(search_inv_id.strip())]

            if search_cust.strip() != "":
                filtered_inv = filtered_inv[filtered_inv['العميل'].astype(str).str.contains(search_cust.strip(), case=False)]

            filtered_inv = filtered_inv[
                (filtered_inv['التاريخ_dt'].dt.date >= inv_start_d) & 
                (filtered_inv['التاريخ_dt'].dt.date <= inv_end_d)
            ]

            display_inv_cols = ["رقم الفاتورة", "التاريخ", "العميل", "عدد المنتجات", "إجمالي الفاتورة"]
            st.dataframe(filtered_inv[display_inv_cols], use_container_width=True)

            # عرض تفاصيل فاتورة محددة
            st.write("#### 📄 عرض تفاصيل فاتورة:")
            available_inv_ids = filtered_inv['رقم الفاتورة'].tolist()
            if available_inv_ids:
                selected_inv_id = st.selectbox("اختر رقم الفاتورة لعرض التفاصيل", available_inv_ids)
                
                selected_inv_obj = next((i for i in st.session_state['invoices'] if i['invoice_id'] == selected_inv_id), None)
                if selected_inv_obj:
                    st.info(f"**تفاصيل الفاتورة رقم #{selected_inv_obj['invoice_id']}** | **التاريخ:** {selected_inv_obj['date']} | **العميل:** {selected_inv_obj['customer']}")
                    
                    inv_items_df = pd.DataFrame(selected_inv_obj['items'])
                    inv_items_df.columns = ["المنتج", "سعر الوحدة", "الكمية", "الإجمالي"]
                    st.dataframe(inv_items_df, use_container_width=True)
                    st.write(f"**الإجمالي الكلي:** ${selected_inv_obj['total']:,.2f}")

            # تصدير الفواتير وتفاصيلها إلى Excel
            exp_c1, exp_c2 = st.columns(2)
            with exp_c1:
                out_inv_main = io.BytesIO()
                with pd.ExcelWriter(out_inv_main, engine='openpyxl') as writer:
                    filtered_inv[display_inv_cols].to_excel(writer, index=False, sheet_name='فواتير المبيعات')
                st.download_button(
                    label="📥 تصدير فواتير المبيعات (المصفاة) إلى Excel",
                    data=out_inv_main.getvalue(),
                    file_name='invoices_summary_report.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )

            with exp_c2:
                # تجميع تفاصيل كافة الفواتير المصفاة
                detailed_rows = []
                filtered_ids_set = set(filtered_inv['رقم الفاتورة'])
                for inv in st.session_state['invoices']:
                    if inv['invoice_id'] in filtered_ids_set:
                        for it in inv['items']:
                            detailed_rows.append({
                                "رقم الفاتورة": inv["invoice_id"],
                                "التاريخ": inv["date"],
                                "العميل": inv["customer"],
                                "المنتج": it["product"],
                                "الكمية": it["qty"],
                                "سعر الوحدة": it["price"],
                                "إجمالي المنتج": it["subtotal"]
                            })
                
                out_inv_det = io.BytesIO()
                with pd.ExcelWriter(out_inv_det, engine='openpyxl') as writer:
                    pd.DataFrame(detailed_rows).to_excel(writer, index=False, sheet_name='تفاصيل المبيعات')
                st.download_button(
                    label="📥 تصدير تفاصيل المبيعات (المصفاة) إلى Excel",
                    data=out_inv_det.getvalue(),
                    file_name='invoices_detailed_report.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )

        # ---------------------------------------------------------
        # 6. قسم تقارير المبيعات والمنتجات الأكثر مبيعاً
        # ---------------------------------------------------------
        st.divider()
        st.subheader("4️⃣ تقارير وتكشوفات المبيعات 📊")

        if not st.session_state['invoices']:
            st.info("لا توجد مبيعات لعرض تقاريرها.")
        else:
            st.write("**تحديد الفترة الزمنية للتقرير:**")
            all_dates = [datetime.strptime(i['date'], "%Y-%m-%d").date() for i in st.session_state['invoices']]
            
            rep_col1, rep_col2 = st.columns(2)
            with rep_col1:
                rep_start_date = st.date_input("من تاريخ", value=min(all_dates), key="rep_start_d_key")
            with rep_col2:
                rep_end_date = st.date_input("إلى تاريخ", value=max(all_dates), key="rep_end_d_key")

            # ترشيح الفواتير بناءً على النطاق الزمني
            period_invoices = [
                i for i in st.session_state['invoices'] 
                if rep_start_date <= datetime.strptime(i['date'], "%Y-%m-%d").date() <= rep_end_date
            ]

            total_sales_val = sum(i['total'] for i in period_invoices)
            total_inv_count = len(period_invoices)
            avg_inv_val = (total_sales_val / total_inv_count) if total_inv_count > 0 else 0.0
            
            total_qty_sold = 0
            product_sales_counter = {}

            for inv in period_invoices:
                for item in inv['items']:
                    total_qty_sold += item['qty']
                    product_sales_counter[item['product']] = product_sales_counter.get(item['product'], 0.0) + item['qty']

            # العرض الرئيسي للمؤشرات
            pm1, pm2, pm3, pm4 = st.columns(4)
            pm1.metric("إجمالي المبيعات", f"${total_sales_val:,.2f}")
            pm2.metric("عدد الفواتير", f"{total_inv_count}")
            pm3.metric("متوسط قيمة الفاتورة", f"${avg_inv_val:,.2f}")
            pm4.metric("إجمالي الكميات المباعة", f"{total_qty_sold:g}")

            st.write("#### 🏆 المنتجات الأكثر مبيعاً في هذه الفترة:")
            if product_sales_counter:
                top_products_df = pd.DataFrame([
                    {"المنتج": p, "إجمالي الكمية المباعة": q} 
                    for p, q in product_sales_counter.items()
                ]).sort_values(by="إجمالي الكمية المباعة", ascending=False)
                
                st.dataframe(top_products_df, use_container_width=True)

                out_top = io.BytesIO()
                with pd.ExcelWriter(out_top, engine='openpyxl') as writer:
                    top_products_df.to_excel(writer, index=False, sheet_name='المنتجات الأكثر مبيعا')
                st.download_button(
                    label="📥 تصدير تقرير المنتجات الأكثر مبيعاً إلى Excel",
                    data=out_top.getvalue(),
                    file_name='top_selling_products.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
            else:
                st.caption("لا توجد مبيعات في هذه الفترة المحدد.")

        # ---------------------------------------------------------
        # 7. قسم إضافة وسجل حركة المخزون
        # ---------------------------------------------------------
        st.divider()
        st.subheader("5️⃣ إضافة وسجل حركة المخزون 🔄")

        with st.form(key="add_movement_form", clear_on_submit=True):
            col_p, col_t, col_q, col_d = st.columns(4)
            with col_p:
                selected_product = st.selectbox("اسم المنتج", product_names, key="mov_p_select")
            with col_t:
                movement_type = st.selectbox("نوع الحركة", ["شراء", "إضافة للمخزون", "خصم من المخزون"])
            with col_q:
                movement_qty = st.number_input("الكمية", min_value=0.0, step=1.0, value=0.0, key="mov_q_input")
            with col_d:
                movement_date = st.date_input("التاريخ", value=date.today(), key="mov_d_input")
            
            note = st.text_input("ملاحظة (اختيارية)", "", key="mov_note_input")
            submit_btn = st.form_submit_button("تسجيل الحركة 💾")

        if submit_btn:
            if movement_qty <= 0:
                st.error("⚠️ خطأ: يجب إدخال كمية صحيحة أو عشرية موجبة وتكون أكبر من الصفر.")
            else:
                current_stock = product_stock_map.get(selected_product, 0.0)
                is_addition = movement_type in ["شراء", "إضافة للمخزون"]
                
                if not is_addition and movement_qty > current_stock:
                    shortage = movement_qty - current_stock
                    st.error(f"❌ لا يمكن تنفيذ عملية {movement_type}. الرصيد الحالي: {current_stock:g}، والكمية المطلوبة: {movement_qty:g}. (الكمية الناقصة: {shortage:g}).")
                else:
                    delta = movement_qty if is_addition else -movement_qty
                    st.session_state['stock_adjustments'][selected_product] = st.session_state['stock_adjustments'].get(selected_product, 0.0) + delta
                    new_stock_after = current_stock + delta
                    
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

        st.write("#### 📋 سجل جميع حركات المخزون:")
        if not st.session_state['movement_history']:
            st.info("لم يتم تسجيل أي حركات مخزون حتى الآن.")
        else:
            moves_df = pd.DataFrame(st.session_state['movement_history'])
            moves_df['التاريخ_dt'] = pd.to_datetime(moves_df['التاريخ'])

            f1, f2, f3, f4 = st.columns(4)
            with f1:
                search_move_p = st.text_input("🔍 بحث باسم المنتج في الحركات", "")
            with f2:
                move_types_list = ['الكل'] + list(moves_df['نوع الحركة'].unique())
                selected_move_type = st.selectbox("تصفية بنوع الحركة", move_types_list)
            with f3:
                min_date = moves_df['التاريخ_dt'].min().date()
                start_d = st.date_input("تاريخ البداية للحركات", value=min_date)
            with f4:
                max_date = moves_df['التاريخ_dt'].max().date()
                end_d = st.date_input("تاريخ النهاية للحركات", value=max_date)

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

            output_moves = io.BytesIO()
            with pd.ExcelWriter(output_moves, engine='openpyxl') as writer:
                filtered_moves[display_moves_cols].to_excel(writer, index=False, sheet_name='سجل الحركات')
            
            st.download_button(
                label="📥 تصدير سجل الحركات الحالي إلى Excel",
                data=output_moves.getvalue(),
                file_name='inventory_movements_report.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

        # ---------------------------------------------------------
        # 8. قسم تقرير حسابات منتج تفصيلي
        # ---------------------------------------------------------
        st.divider()
        st.subheader("6️⃣ تقرير حسابات المنتجات التفصيلي 🔍")

        if product_names:
            rep_product = st.selectbox("اختر المنتج لتقييم حسابه وحركاته", product_names, key="rep_p_select_main")
            
            current_p_stock = product_stock_map.get(rep_product, 0.0)
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
            
            st.write(f"**سجل حركات المنتج الخاص بـ ({rep_product}):**")
            if p_moves:
                p_moves_df = pd.DataFrame(p_moves)[['التاريخ', 'نوع الحركة', 'الكمية', 'الرصيد بعد الحركة', 'الملاحظة']]
                st.dataframe(p_moves_df, use_container_width=True)
            else:
                st.caption("لا توجد حركات مسجلة لهذا المنتج حتى الآن.")

        # ---------------------------------------------------------
        # 9. قسم لوحة المنتجات والمخزون الرئيسية
        # ---------------------------------------------------------
        st.divider()
        st.subheader("7️⃣ لوحة المخزون الرئيسية (المنتجات)")

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

        output_prod = io.BytesIO()
        with pd.ExcelWriter(output_prod, engine='openpyxl') as writer:
            display_df[final_columns].to_excel(writer, index=False, sheet_name='تقرير المنتجات')
        
        st.download_button(
            label="📥 تصدير جدول المنتجات الحالي إلى Excel",
            data=output_prod.getvalue(),
            file_name='final_inventory_report.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        st.error(f"⚠️ تعذر قراءة الملف: الملف المرفوع غير صالح أو تالف. يرجى التأكد من رفع ملف Excel أو CSV صحيح.")
