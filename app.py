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

# ══════════════════════════════════════════════════════════════
#  1. 설정값 및 가중치 사전
# ══════════════════════════════════════════════════════════════

MAX_WORKERS     = 10
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
GROUP_BADGE = {
    "그룹 A": "background:#D5F5E3; color:#1e7e34; padding:2px 8px; border-radius:4px; font-weight:bold;",
    "그룹 B": "background:#FEF9E7; color:#856404; padding:2px 8px; border-radius:4px; font-weight:bold;",
    "그룹 C": "background:#FDEBD0; color:#c05621; padding:2px 8px; border-radius:4px; font-weight:bold;",
    "":       "color:#999; padding:2px 8px;",
}

# ══════════════════════════════════════════════════════════════
#  2. 매핑 테이블 (기본 소스 데이터 포함)
# ══════════════════════════════════════════════════════════════

# [사용자의 기존 데이터를 그대로 통합하였습니다]
FIXED_MAP = {
    "1conomynews": "1코노미뉴스", "cctimes": "충청타임즈", "chungnamilbo": "충남일보", "dtnews24": "대전뉴스",
    "enetnews": "이넷뉴스", "financialreview": "파이낸셜리뷰", "globalepic": "글로벌에픽", "gokorea": "고코리아",
    "apparelnews": "어패럴뉴스", "fashionbiz": "패션비즈", "biztribune": "비즈트리뷴", "etoday": "이투데이",
    "byline": "바이라인네트워크", "dealsite": "딜사이트", "businesspost": "비즈니스포스트", "insight": "인사이트"
}

OID_MAP = {
    "001": "연합뉴스", "003": "뉴시스", "008": "머니투데이", "009": "매일경제", "011": "서울경제",
    "015": "한국경제", "018": "이데일리", "020": "동아일보", "023": "조선일보", "025": "중앙일보",
    "410": "어패럴뉴스", "273": "패션비즈", "214": "MBC", "056": "KBS", "055": "SBS"
}

# [사용자의 GROUP_MAP 데이터 반영]
GROUP_MAP = {
    "매일경제": "그룹 A", "한국경제": "그룹 A", "서울경제": "그룹 A", "조선일보": "그룹 A", "중앙일보": "그룹 A",
    "어패럴뉴스": "그룹 A", "패션비즈": "그룹 A", "동아일보": "그룹 A", "연합뉴스": "그룹 A", "머니투데이": "그룹 A",
    "이데일리": "그룹 A", "비즈니스포스트": "그룹 B", "어패럴뉴스": "그룹 A", "패션엔": "그룹 C"
}

# ══════════════════════════════════════════════════════════════
#  3. 분석 함수
# ══════════════════════════════════════════════════════════════

def analyze_article_content(link, query):
    if "naver.com" not in link: return 0.0, 0.0
    try:
        res = requests.get(link, headers=HEADERS, timeout=REQUEST_TIMEOUT)
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

def publisher_from_url(link):
    if "naver.com" in link:
        m = re.search(r'article/(\d+)/', link)
        if m:
            oid = m.group(1).zfill(3)
            if oid in OID_MAP: return OID_MAP[oid]
    try:
        domain = link.split('//')[-1].split('/')[0].lower()
        domain = re.sub(r'^(www\.|n\.|news\.|m\.|blog\.|sports\.)', '', domain)
        for key, name in FIXED_MAP.items():
            if key in domain: return name
        return domain.split('.')[0].upper()
    except: return "기타매체"

def fetch_naver_article_info(link):
    result = {"publisher": publisher_from_url(link), "pick": ""}
    if "naver.com" not in link: return result
    try:
        res = requests.get(link, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        soup = BeautifulSoup(res.text, 'html.parser')
        logo = soup.select_one('a.press_logo img, .media_end_head_top a img')
        if logo: result["publisher"] = logo.get('alt', '').strip()
        if soup.select_one('.is_pick, .media_end_head_journalist_edit_label') or "PICK" in res.text:
            result["pick"] = "PICK"
    except: pass
    return result

def run_search(query, client_id, client_secret, progress_bar, status_text, days):
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
        future_to_idx = {executor.submit(fetch_naver_article_info, item["link"]): i for i, item in enumerate(raw_items)}
        for i, future in enumerate(as_completed(future_to_idx)):
            idx = future_to_idx[future]
            crawl_results[idx] = future.result()
            progress_bar.progress(int((i+1)/len(raw_items)*70))

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

# ══════════════════════════════════════════════════════════════
#  4. UI 및 실행 로직 (입력창 최상단 배치)
# ══════════════════════════════════════════════════════════════

st.set_page_config(page_title="영향력 & 리스크 뉴스 클리핑", layout="wide")
st.title("🚀 이슈 파급력 & 리스크 모니터링")

# --- 입력창 구역 ---
st.divider()
c1, c2, c3 = st.columns([3, 1, 1])
with c1: query = st.text_input("검색 키워드 입력", placeholder="예: 무신사")
with c2: days = st.selectbox("검색 기간", [1, 3, 7, 14], index=2, format_func=lambda x: f"최근 {x}일")
with c3: st.write(""); search_btn = st.button("🔍 데이터 분석 시작", type="primary", use_container_width=True)

# API 키 자동 로드 (사이드바 표시)
try:
    c_id = st.secrets["naver"]["client_id"]
    c_secret = st.secrets["naver"]["client_secret"]
    with st.sidebar:
        st.success("✅ 네이버 API 연결됨")
        st.divider()
        st.caption("가중치 기준: 그룹 A(10) > B(5) > C(2)")
except:
    st.error("Secrets 설정을 확인하세요."); st.stop()

# 검색 실행
if search_btn and query:
    pb = st.progress(0); st.session_state["df"] = run_search(query, c_id, c_secret, pb, st.empty(), days)
    st.session_state["query_val"] = query

# 결과 표시 구역
if "df" in st.session_state and st.session_state["df"] is not None:
    df = st.session_state["df"]
    
    # ── 상단 대시보드 ──
    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("종합 파급력", f"{df['영향력'].sum():,.1f} pts")
    m2.metric("그룹 A 기사", f"{(df['그룹']=='그룹 A').sum()}건")
    m3.metric("PICK 기사", f"{(df['PICK']=='PICK').sum()}건")
    m4.metric("리스크 지수", f"{df['부정점수'].sum():,.1f}", delta_color="inverse")

    # ── 시각화 차트 ──
    lc, rc = st.columns([1.5, 1])
    with lc:
        st.write("📊 시간별 파급력 추이")
        st.plotly_chart(px.bar(df, x="게시일", y=["긍정점수", "부정점수"], color_discrete_map={"긍정점수": "#2ecc71", "부정점수": "#e74c3c"}), use_container_width=True)
    with rc:
        st.write("🏆 주요 영향력 기사 (Top 5)")
        for _, r in df.sort_values("영향력", ascending=False).head(5).iterrows():
            st.caption(f"**[{r['영향력']}pt]** {r['매체명']} | {r['제목_표시']}")

    # ── 상세 리스트 테이블 (HTML) ──
    st.divider()
    st.subheader("📂 뉴스 클리핑 상세 리스트")
    
    def render_table(df_view):
        rows = ""
        for _, row in df_view.iterrows():
            badge = f'<span style="{GROUP_BADGE.get(row["그룹"], GROUP_BADGE[""])}">{row["그룹"] if row["그룹"] else "미분류"}</span>'
            pick = '<span style="color:#e74c3c;font-weight:bold;">PICK</span>' if row["PICK"] == "PICK" else ""
            rows += f'<tr style="background:{GROUP_COLORS.get(row["그룹"], "#FFF")};"><td style="padding:8px;">{badge}</td><td>{row["매체명"]}</td><td><a href="{row["링크"]}" target="_blank">{row["제목_표시"]}</a></td><td style="text-align:center;">{pick}</td><td>{row["영향력"]}</td><td>{row["게시일"]}</td></tr>'
        return f'<table style="width:100%; border-collapse:collapse; font-size:0.9rem;"><thead><tr style="background:#2C3E50; color:white;"><th>그룹</th><th>매체명</th><th>제목</th><th>PICK</th><th>점수</th><th>게시일</th></tr></thead><tbody>{rows}</tbody></table>'

    st.markdown(render_table(df), unsafe_allow_html=True)

    # 엑셀 다운로드
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df[["그룹", "매체명", "제목", "PICK", "게시일", "영향력", "감성"]].to_excel(writer, index=False)
    st.download_button("📥 엑셀 결과 다운로드", output.getvalue(), f"analysis_{st.session_state['query_val']}.xlsx", type="primary", use_container_width=True)
