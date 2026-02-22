import io
import re
import html
import time
import requests
import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

# 1. 설정값 및 가중치
MAX_WORKERS = 10
REQUEST_TIMEOUT = 6
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}

WEIGHTS = {
    "그룹 A": 10.0, "그룹 B": 5.0, "그룹 C": 2.0, "": 1.0,
    "PICK_MULTIPLIER": 1.5, "TITLE_BONUS": 3.0
}

SENTIMENT_DICT = {
    "positive": ["성장", "흑자", "혁신", "인기", "급증", "돌풍", "1위", "상생", "호조", "성공", "확대", "유치"],
    "negative": ["논란", "위기", "적자", "하락", "감소", "조사", "의혹", "비판", "중단", "우려", "갈등", "부진"]
}

GROUP_COLORS = {"그룹 A": "#D5F5E3", "그룹 B": "#FEF9E7", "그룹 C": "#FDEBD0", "": "#FFFFFF"}

# 매핑 데이터 (매체명 분류용)
OID_MAP = {"001": "연합뉴스", "009": "매일경제", "015": "한국경제", "011": "서울경제", "023": "조선일보", "025": "중앙일보"}
GROUP_MAP = {"매일경제": "그룹 A", "한국경제": "그룹 A", "서울경제": "그룹 A", "연합뉴스": "그룹 A"}

# 2. 분석용 함수
def analyze_article_content(link, query):
    if "naver.com" not in link: return 0.0, 0.0
    try:
        res = requests.get(link, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        # [수정 포인트] SyntaxError가 발생했던 soup 객체 생성 부분입니다.
        soup = BeautifulSoup(res.text, 'html.parser')
        content = soup.select_one('#newsct_article, #articeBody')
        if content:
            text = content.get_text()
            freq_score = min(text.count(query) * 0.3, 5.0)
            pos = sum(text.count(w) for w in SENTIMENT_DICT["positive"])
            neg = sum(text.count(w) for w in SENTIMENT_DICT["negative"])
            sentiment_val = (pos - neg) / (pos + neg) if (pos + neg) > 0 else 0.0
            return freq_score, sentiment_val
    except: pass
    return 0.0, 0.0

def fetch_naver_article_info(link):
    res_info = {"publisher": "기타매체", "pick": ""}
    if "naver.com" not in link: return res_info
    try:
        res = requests.get(link, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        soup = BeautifulSoup(res.text, 'html.parser')
        logo = soup.select_one('a.press_logo img, .media_end_head_top a img')
        if logo: res_info["publisher"] = logo.get('alt', '').strip()
        if soup.select_one('.is_pick, .media_end_head_journalist_edit_label') or "PICK" in res.text:
            res_info["pick"] = "PICK"
    except: pass
    return res_info

def run_search(query, client_id, client_secret, progress_bar, days):
    naver_headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    kst = timezone(timedelta(hours=9)); now = datetime.now(kst); since = now - timedelta(days=days)
    raw_items = []
    for start_index in [1, 101]:
        url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&start={start_index}&sort=date"
        res = requests.get(url, headers=naver_headers, timeout=10)
        if res.status_code != 200: return None
        items = res.json().get('items', [])
        for item in items:
            pub_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').replace(tzinfo=kst)
            if pub_date < since: break
            raw_items.append({"pub_date": pub_date, "link": item.get('link', ''), "title": html.unescape(re.sub(r'<[^>]*>', '', item.get('title', '')))})
    
    if not raw_items: return None
    
    crawl_results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_idx = {executor.submit(fetch_naver_article_info, item["link"]): idx for idx, item in enumerate(raw_items)}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            crawl_results[idx] = future.result()
            progress_bar.progress(int((idx+1)/len(raw_items) * 70))

    news_data = []
    for idx, item in enumerate(raw_items):
        info = crawl_results.get(idx, {})
        pub, pick = info.get("publisher", "기타"), info.get("pick", "")
        group = GROUP_MAP.get(pub, "")
        base = WEIGHTS.get(group, 1.0); mult = WEIGHTS["PICK_MULTIPLIER"] if pick == "PICK" else 1.0
        t_bonus = WEIGHTS["TITLE_BONUS"] if query.lower() in item["title"].lower() else 0.0
        f_score, s_val = 0.0, 0.0
        if group == "그룹 A" or pick == "PICK":
            f_score, s_val = analyze_article_content(item["link"], query)
        impact = (base * mult) + t_bonus + f_score
        sent = "긍정" if s_val > 0.1 else ("부정" if s_val < -0.1 else "중립")
        news_data.append({
            "그룹": group, "매체명": pub, "제목": f'=HYPERLINK("{item["link"]}", "{item["title"]}")',
            "제목_표시": item["title"], "링크": item["link"], "PICK": pick,
            "게시일": item["pub_date"].strftime('%Y-%m-%d %H:%M'), "영향력": round(impact, 2), "감성": sent,
            "긍정점수": round(impact, 2) if sent == "긍정" else 0, "부정점수": round(impact, 2) if sent == "부정" else 0
        })
    return pd.DataFrame(news_data)

# 3. UI
st.set_page_config(page_title="이슈 파급력 분석 시스템", layout="wide")
st.title("🚀 글로벌 이슈 파급력 & 리스크 모니터링")

with st.sidebar:
    st.header("🔐 시스템 상태")
    try:
        c_id = st.secrets["naver"]["client_id"]
        c_secret = st.secrets["naver"]["client_secret"]
        st.success("API 서버 연결됨")
    except:
        st.error("Secrets 설정 확인 필요"); st.stop()

st.divider()
c1, c2, c3 = st.columns([3, 1, 1])
with c1: query = st.text_input("검색 키워드", placeholder="예: 무신사")
with c2: days = st.selectbox("기간", [1, 3, 7, 14], index=2, format_func=lambda x: f"최근 {x}일")
with c3: st.write(""); search_btn = st.button("🔍 데이터 분석 시작", type="primary", use_container_width=True)

if search_btn and query:
    pb = st.progress(0)
    df_res = run_search(query, c_id, c_secret, pb, days)
    if df_res is not None:
        st.session_state["df"] = df_res
    else:
        st.warning("결과를 찾을 수 없습니다.")

if "df" in st.session_state:
    df = st.session_state["df"]
    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("종합 파급력", f"{df['영향력'].sum():,.1f} pts")
    m2.metric("평균 영향력", f"{df['영향력'].mean():.1f} pts")
    m3.metric("🟢 호재 지수", f"{df['긍정점수'].sum():,.1f}")
    m4.metric("🔴 리스크 지수", f"{df['부정점수'].sum():,.1f}", delta_color="inverse")

    st.divider()
    lc, rc = st.columns([1.5, 1])
    with lc:
        st.write("📊 시간별 파급력 추이")
        st.plotly_chart(px.bar(df, x="게시일", y=["긍정점수", "부정점수"], color_discrete_map={"긍정점수": "#2ecc71", "부정점수": "#e74c3c"}), use_container_width=True)
    with rc:
        st.write("🚨 주요 리스크 기사")
        risky_df = df[df["감성"] == "부정"].sort_values("영향력", ascending=False).head(5)
        for _, r in risky_df.iterrows():
            st.warning(f"**[{r['영향력']}pt]** {r['매체명']}: {r['제목_표시']}")

    st.divider()
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df[["그룹", "매체명", "제목", "PICK", "게시일", "영향력", "감성"]].to_excel(writer, index=False)
    st.download_button("📥 엑셀 결과 다운로드", output.getvalue(), f"analysis_{query}.xlsx", "application/vnd.ms-excel", type="primary")
