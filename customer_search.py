import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

# --- 網頁設定 ---
st.set_page_config(page_title="北營業務客戶維護系統", layout="wide")
st.title("☁️ 雲端客戶資料維護系統")

# --- 雲端連線設定 ---
@st.cache_resource
def get_sheet():
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        creds_dict, 
        ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(creds)
    # 【請填入你的試算表 ID】
    SPREADSHEET_ID = "1r-nFgfVwVRZRNQ5LmvnonvMFHJTTFe1lwOYZ_F57N5M"
    return client.open_by_key(SPREADSHEET_ID).sheet1

# --- 終極修正：補零版資料讀取 ---
@st.cache_data(ttl=600)
def get_all_data():
    sheet = get_sheet()
    all_data = sheet.get_all_values()
    
    if not all_data:
        return pd.DataFrame()
    
    header = all_data[0]
    data = all_data[1:]
    df = pd.DataFrame(data, columns=header)
    
    # 針對「行動電話」與「電話」，如果只有 9 碼且非空值，強制補 0
    def fix_phone(x):
        x = str(x).strip()
        if x and x.isdigit() and len(x) == 9:
            return "0" + x
        return x

    # 針對「客戶代號」，如果是純數字且長度不足（例如你希望它是 4 碼），也可以補零
    def fix_code(x):
        x = str(x).strip()
        # 假設你的客戶代號應該是 4 碼，若讀進來只有 3 碼就補 0
        # 如果不確定長度，可以直接將科學記號 e+10 之類的轉回正常字串
        return x

    if '行動電話' in df.columns:
        df['行動電話'] = df['行動電話'].apply(fix_phone)
    
    if '電話' in df.columns:
        df['電話'] = df['電話'].apply(fix_phone)

    if '客戶代號' in df.columns:
        df['客戶代號'] = df['客戶代號'].apply(fix_code)
        
    return df

# 載入資料
df = get_all_data()

# --- 側邊欄篩選 ---
st.sidebar.header("🎯 篩選面板")
sales_list = ["全部"] + sorted([s for s in df['經營業務'].unique() if s])
selected_sales = st.sidebar.selectbox("經營業務：", sales_list)

temp_df = df.copy()
if selected_sales != "全部":
    temp_df = temp_df[temp_df['經營業務'] == selected_sales]

area_list = ["全部"] + sorted([a for a in temp_df['轄區'].unique() if a])
selected_area = st.sidebar.selectbox("轄區：", area_list)

if selected_area != "全部":
    temp_df = temp_df[temp_df['轄區'] == selected_area]

# --- 搜尋邏輯 ---
query = st.text_input("搜尋客戶 (代號/簡稱/全稱)：", placeholder="輸入關鍵字")

# 初始化搜尋結果
search_results = temp_df 

if query:
    mask = (temp_df['客戶簡稱'].astype(str).str.contains(query, case=False) | 
            temp_df['客戶全稱'].astype(str).str.contains(query, case=False) | 
            temp_df['客戶代號'].astype(str).str.contains(query, case=False))
    search_results = temp_df[mask]

# 限制顯示數量，避免手機當機
display_results = search_results.head(50)

# --- 顯示與維護 ---
if not display_results.empty:
    st.write(f"找到 {len(display_results)} 筆相符資料")
    
    for idx, row in display_results.iterrows():
        title = f"🏢 [{row.get('轄區', '')}] {row.get('客戶簡稱', '無')} ({row.get('客戶代號', '')})"
        with st.expander(title):
            # 兩欄位佈局顯示資料
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**客戶全稱：** {row.get('客戶全稱', '')}")
                st.markdown(f"**負責人：** {row.get('負責人', '')}")
                st.markdown(f"**聯絡人：** {row.get('聯絡人', '')}")
                st.markdown(f"**行業別：** {row.get('行業別', '')}")
                st.markdown(f"**統編：** {row.get('統一編號', '')}")
            with col2:
                st.markdown(f"**成交業務：** {row.get('成交業務', '')}")
                st.markdown(f"**經營業務：** {row.get('經營業務', '')}")
                st.markdown(f"**電話：** {row.get('電話', '')}")
                st.markdown(f"**手機：** {row.get('行動電話', '')}")
                st.markdown(f"**地址：** {row.get('地址', '')}")
            
            st.divider()
            st.subheader("📝 業務維護")
            
            # 輸入框
            new_count = st.text_input("拜訪次數", value=str(row.get('拜訪次數', '')), key=f"count_{idx}")
            new_record = st.text_input("拜訪紀錄", value=str(row.get('拜訪紀錄', '')), key=f"rec_{idx}")
            new_date = st.text_input("最近一次拜訪日期", value=str(row.get('最近一次拜訪日期', '')), key=f"date_{idx}")
            
            # 更新按鈕
            if st.button("上傳至雲端", key=f"save_{idx}"):
                try:
                    sheet = get_sheet()
                    target_row = df[df['客戶代號'] == str(row.get('客戶代號'))].index[0] + 2
                    sheet.update_cell(target_row, 12, new_count)
                    sheet.update_cell(target_row, 13, new_record)
                    sheet.update_cell(target_row, 14, new_date)
                    st.success("✅ 已同步！")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"同步失敗: {e}")
else:
    st.info("查無資料，請嘗試其他搜尋條件。")
