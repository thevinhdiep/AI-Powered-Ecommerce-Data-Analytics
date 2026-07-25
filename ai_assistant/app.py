import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import os
import requests

st.set_page_config(page_title="E-Commerce AI Assistant", layout="wide")

# Custom CSS cho giao diện chat giống Gemini (User bên phải, AI bên trái)
st.markdown("""
<style>
/* Ép User message sang phải */
[data-testid="stChatMessage"]:has(.user-msg) {
    flex-direction: row-reverse;
}
/* Bong bóng chat của User */
[data-testid="stChatMessage"]:has(.user-msg) [data-testid="stChatMessageContent"] {
    background-color: #333639;
    border-radius: 18px 4px 18px 18px;
    padding: 10px 15px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}
/* Bong bóng chat của AI */
[data-testid="stChatMessage"]:has(.ai-msg) [data-testid="stChatMessageContent"] {
    background-color: transparent;
    padding: 10px 5px;
}
/* Ẩn bớt viền dư thừa */
[data-testid="stChatMessageContent"] {
    border: none !important;
}
</style>
""", unsafe_allow_html=True)

st.title("E-Commerce AI Data Assistant")
st.markdown("Trợ lý ảo phân tích dữ liệu trực tiếp từ Database EcommerceDB sử dụng Google Gemini API và LangChain.")
st.markdown("---")

# 1. Cấu hình Sidebar
with st.sidebar:
    st.header("Cấu hình API")
    gemini_api_key = st.text_input("Nhập Google Gemini API Key:", type="password")
    
    st.markdown("[Lấy API Key miễn phí tại đây](https://aistudio.google.com/app/apikey)")
    st.divider()
    
    st.markdown("### Về Trợ lý AI này")
    st.info(
        "Trợ lý AI được thiết kế chuyên biệt để phân tích dữ liệu E-commerce. "
        "Hệ thống tự động biên dịch yêu cầu bằng ngôn ngữ tự nhiên thành luồng truy vấn SQL, "
        "tương tác trực tiếp với Database và trích xuất thông tin theo thời gian thực. "
        "Giải pháp này giúp người dùng nghiệp vụ tra cứu số liệu tức thì mà không cần kiến thức lập trình, "
        "tối ưu hóa quy trình báo cáo và thúc đẩy văn hóa ra quyết định dựa trên dữ liệu (Data-driven)."
    )

# 2. Khởi tạo kết nối DB
@st.cache_resource
def get_database_connection():
    try:
        conn_str = r"mssql+pyodbc://@localhost\sqlexpress/EcommerceDB?driver=ODBC+Driver+17+for+SQL+Server"
        db = SQLDatabase.from_uri(conn_str)
        return db
    except Exception as e:
        return str(e)

db = get_database_connection()

if isinstance(db, str):
    st.error(f"Lỗi kết nối Database: {db}\n(Vui lòng đảm bảo SQL Server đang chạy và tên DB là EcommerceDB)")
    st.stop()

# 3. Khởi tạo Lịch sử Chat
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Chào bạn! Mình là trợ lý phân tích dữ liệu E-commerce đây. Bạn cần mình tra cứu số liệu gì hôm nay nào? (Ví dụ: Liệt kê giúp mình top 5 sản phẩm bán ế nhất nhé)"}
    ]

for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.chat_message("user").markdown(f"<div class='user-msg'></div>\n\n{msg['content']}", unsafe_allow_html=True)
    else:
        st.chat_message("assistant").markdown(f"<div class='ai-msg'></div>\n\n{msg['content']}", unsafe_allow_html=True)

# 4. Xử lý câu hỏi
user_query = st.chat_input("Nhập câu hỏi của bạn (Tiếng Việt)...")

if user_query:
    if not gemini_api_key:
        st.warning("Vui lòng nhập Gemini API Key ở thanh bên trái trước khi bắt đầu!")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": user_query})
    st.chat_message("user").markdown(f"<div class='user-msg'></div>\n\n{user_query}", unsafe_allow_html=True)

    with st.chat_message("assistant"):
        st.markdown("<div class='ai-msg'></div>", unsafe_allow_html=True)
        with st.spinner("Đang suy nghĩ và phân tích dữ liệu..."):
            try:
                os.environ["GOOGLE_API_KEY"] = gemini_api_key
                
                # Tự động nhận diện Model
                if "working_model" not in st.session_state:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_api_key}"
                    resp = requests.get(url)
                    working_model = None
                    if resp.status_code == 200:
                        data = resp.json()
                        available_models = [m['name'].replace("models/", "") for m in data.get('models', []) if 'generateContent' in m.get('supportedGenerationMethods', [])]
                        
                        # Ưu tiên các model flash ổn định trước để tránh dính lỗi 404/403 của các bản cũ/khóa
                        priority_models = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
                        models_to_test = [m for m in priority_models if m in available_models]
                        
                        # Thêm các model flash khác nếu không có trong priority
                        for m in available_models:
                            if "flash" in m and m not in models_to_test:
                                models_to_test.append(m)
                                
                        for m in models_to_test:
                            # Test trực tiếp bằng REST API, nếu lỗi sẽ văng ngay lập tức không bị treo (như khi test qua Langchain)
                            test_url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={gemini_api_key}"
                            payload = {"contents": [{"parts": [{"text": "hi"}]}]}
                            try:
                                test_resp = requests.post(test_url, json=payload, timeout=5)
                                if test_resp.status_code == 200:
                                    working_model = m
                                    break
                            except Exception:
                                continue
                                
                    if not working_model:
                        st.error("Tài khoản của bạn hiện đang bị giới hạn truy cập (Rate Limit) hoặc không có quyền dùng các Model AI. Vui lòng thử lại sau 1-2 phút hoặc dùng API Key khác.")
                        st.stop()
                    st.session_state.working_model = working_model

                chosen_model = st.session_state.working_model
                
                llm = ChatGoogleGenerativeAI(model=chosen_model, temperature=0.3)

                # Phân loại câu hỏi (Router)
                router_template = """Phân loại câu hỏi sau của người dùng.
Nếu đó chỉ là lời chào hỏi (như hi, hello, chào), cảm ơn, hoặc giao tiếp thông thường không liên quan đến trích xuất số liệu từ CSDL, hãy trả về đúng 1 chữ: CHITCHAT
Nếu người dùng hỏi về số liệu, sản phẩm, doanh thu, khách hàng, hoặc cần báo cáo... hãy trả về đúng 1 chữ: SQL
Chỉ trả về 1 từ duy nhất.

Câu hỏi: {question}"""
                router_prompt = ChatPromptTemplate.from_template(router_template)
                router_chain = router_prompt | llm | StrOutputParser()
                intent = router_chain.invoke({"question": user_query}).strip().upper()

                if "CHITCHAT" in intent:
                    # Xử lý giao tiếp thông thường
                    chat_template = """Bạn là trợ lý phân tích dữ liệu E-commerce thân thiện.
Hãy đáp lại lời chào hoặc câu hỏi giao tiếp sau của người dùng một cách gần gũi, tự nhiên bằng tiếng Việt.
Không dùng Kính gửi, Trân trọng, không dùng bullet points, không dùng emoji.
Câu hỏi: {question}
Trả lời:"""
                    chat_prompt = ChatPromptTemplate.from_template(chat_template)
                    chat_chain = chat_prompt | llm | StrOutputParser()
                    final_answer = chat_chain.invoke({"question": user_query})
                    
                    st.write(final_answer)
                    st.session_state.messages.append({"role": "assistant", "content": final_answer})
                else:
                    # Bước 1: Dịch Text sang SQL
                    sql_template = """Bạn là chuyên gia phân tích dữ liệu trên hệ quản trị SQL Server. 
Hãy viết MỘT câu truy vấn T-SQL duy nhất hợp lệ để trả lời câu hỏi sau. 
CHỈ TRẢ VỀ CÂU LỆNH SQL, KHÔNG GIẢI THÍCH, KHÔNG BỌC TRONG ```sql.
Nếu cần giới hạn kết quả, hãy dùng SELECT TOP (ví dụ SELECT TOP 5).

Lược đồ Database hiện tại:
{table_info}

Câu hỏi từ User: {question}
SQL Query:"""
                
                    sql_prompt = ChatPromptTemplate.from_template(sql_template)
                    sql_chain = sql_prompt | llm | StrOutputParser()

                    raw_sql = sql_chain.invoke({
                        "table_info": db.get_table_info(),
                        "question": user_query
                    })
                    
                    clean_sql = raw_sql.replace("```sql", "").replace("```", "").strip()

                    with st.expander("Xem câu lệnh SQL đã tự động tạo"):
                        st.code(clean_sql, language="sql")

                    # Bước 2: Chạy SQL Query
                    try:
                        sql_result = db.run(clean_sql)
                    except Exception as run_err:
                        sql_result = f"Lỗi khi chạy SQL: {run_err}"

                    # Bước 3: Dịch Kết quả SQL sang Ngôn ngữ tự nhiên
                    answer_template = """Bạn là một đồng nghiệp phân tích dữ liệu (Data Analyst) đang trò chuyện trong công ty.
Dựa trên câu hỏi, câu truy vấn SQL và kết quả lấy được từ Database, hãy viết một câu trả lời mang phong cách thân thiện, gần gũi, mạch lạc bằng tiếng Việt.
YÊU CẦU BẮT BUỘC:
1. PHẢI ĐƯA RA CON SỐ CỤ THỂ VÀ CHÍNH XÁC lấy từ phần "Kết quả Data".
2. BỐ CỤC DỄ NHÌN: Khi liệt kê danh sách (như Top 5, Top 10), HÃY dùng gạch đầu dòng ngắn gọn. Bôi đậm (bold) tên đối tượng/sản phẩm và để số liệu ngay bên cạnh để người xem dễ đọc. TUYỆT ĐỐI KHÔNG viết một đoạn văn dài miên man dính chùm vào nhau.
3. TUYỆT ĐỐI KHÔNG dùng văn phong quá trang trọng (không dùng Kính gửi, Trân trọng, Thưa sếp).
4. TUYỆT ĐỐI KHÔNG sử dụng biểu tượng cảm xúc (emoji/icon) nào.
5. Không giải thích về code hay cách truy vấn. Chỉ báo cáo kết quả.

Câu hỏi: {question}
SQL Query: {query}
Kết quả Data: {result}

Trả lời:"""
                    
                    answer_prompt = ChatPromptTemplate.from_template(answer_template)
                    answer_chain = answer_prompt | llm | StrOutputParser()

                    final_answer = answer_chain.invoke({
                        "question": user_query,
                        "query": clean_sql,
                        "result": str(sql_result)
                    })

                    st.write(final_answer)
                    st.session_state.messages.append({"role": "assistant", "content": final_answer})

            except Exception as e:
                st.error(f"Đã xảy ra lỗi: {str(e)}")
