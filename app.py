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
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    )
}

# 파급력 산출용 가중치
WEIGHTS = {
    "그룹 A": 10.0,
    "그룹 B": 5.0,
    "그룹 C": 2.0,
    "":       1.0,
    "PICK_MULTIPLIER": 1.5,
    "TITLE_BONUS": 3.0
}

# 리스크 분석용 감성 사전
SENTIMENT_DICT = {
    "positive": ["성장", "흑자", "혁신", "인기", "급증", "돌풍", "1위", "상생", "호조", "성공", "확대", "유치"],
    "negative": ["논란", "위기", "적자", "하락", "감소", "조사", "의혹", "비판", "중단", "우려", "갈등", "부진"]
}

GROUP_COLORS = {
    "그룹 A": "#D5F5E3",
    "그룹 B": "#FEF9E7",
    "그룹 C": "#FDEBD0",
    "":       "#FFFFFF",
}

GROUP_BADGE = {
    "그룹 A": "background:#D5F5E3; color:#1e7e34; padding:2px 8px; border-radius:4px; font-weight:bold;",
    "그룹 B": "background:#FEF9E7; color:#856404; padding:2px 8px; border-radius:4px; font-weight:bold;",
    "그룹 C": "background:#FDEBD0; color:#c05621; padding:2px 8px; border-radius:4px; font-weight:bold;",
    "":       "color:#999; padding:2px 8px;",
}

# ══════════════════════════════════════════════════════════════
#  2. 매핑 테이블 (기존 소스 데이터)
# ══════════════════════════════════════════════════════════════

# [기존의 FIXED_MAP, OID_MAP, GROUP_MAP 데이터를 여기에 그대로 유지하십시오]
# (지면 관계상 생략하지만 실제 파일에는 사용자가 제공한 모든 매핑 데이터를 포함해야 합니다)

# ══════════════════════════════════════════════════════════════
#  3. 핵심 분석 함수
# ══════════════════════════════════════════════════════════════

def analyze_article_content(link: str, query: str):
    """본문을 분석하여 키워드 빈도와 감성 지수 산출"""
    if "naver.com" not in link:
        return 0.0, 0.0
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

def clean_html_text(text: str) -> str:
    if not text: return ""
    text = html.unescape(text)
    text = re.sub(r'<[^>]*>', '', text)
    return text.replace('"', "'")

def publisher_from_url(link: str) -> str:
    # [기존 publisher_from_url 로직 유지]
    if "naver.com" in link:
        m = re.search(r'article/(\d+)/', link)
        if m:
            oid = m.group(1).zfill(3)
            # OID_MAP 참조 (실제 코드엔 OID_MAP 정의 필요)
            return "네이버뉴스" 
    return "기타매체"

def fetch_naver_article_info(link: str) -> dict:
    # [기존 fetch_naver_article_info 로직 유지]
    result = {"publisher": publisher_from_url(link), "pick": ""}
    try:
        res = requests.get(link, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        soup = BeautifulSoup(res.text, 'html.parser')
        if soup.select_one('.is_pick, .media_end_head_journalist_edit_label') or "PICK" in res.text:
            result["pick"] = "PICK"
    except: pass
    return result

# ══════════════════════════════════════════════════════════════
#  4. 수집 파이프라인
# ══════════════════════════════════════════════════════════════

def run_search(query: str, client_id: str, client_secret: str, progress_bar, status_text, days: int):
    naver_headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    since = now - timedelta(days=days)

    raw_items = []
    for start_index in [1, 101]:
        url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&start={start_index}&sort=date"
        res = requests.get(url, headers=naver_headers, timeout=10)
        if res.status_code != 200: return None
        items = res.json().get('items', [])
        for item in items:
            pub_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').replace(tzinfo=kst)
            if pub_date < since: break
            raw_items.append({"pub_date": pub_date, "link": item.get('link', ''), "title": clean_html_text(item.get('title', ''))})
    
    if not raw_items: return None
    
    crawl_results = {}
    total = len(raw_items)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_idx = {executor.submit(fetch_naver_article_info, item["link"]): idx for idx, item in enumerate(raw_items)}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            crawl_results[idx] = future.result()
            progress_bar.progress(int((idx+1)/total * 70))

    news_data = []
    for idx, item in enumerate(raw_items):
        info = crawl_results.get(idx, {"publisher": "기타", "pick": ""})
        pub, pick = info.get("publisher", "기타"), info.get("pick", "")
        # GROUP_MAP에서 분류 가져오기
        # group = GROUP_MAP.get(pub, "")
        group = "" # 실제 코드엔 GROUP_MAP 기반 로직 필요
        
        impact_base = WEIGHTS.get(group, 1.0)
        mult = WEIGHTS["PICK_MULTIPLIER"] if pick == "PICK" else 1.0
        t_bonus = WEIGHTS["TITLE_BONUS"] if query.lower() in item["title"].lower() else 0.0
        
        f_score, s_val = 0.0, 0.0
        if group == "그룹 A" or pick == "PICK":
            f_score, s_val = analyze_article_content(item["link"], query)
            
        impact = (impact_base * mult) + t_bonus + f_score
        sent_label = "긍정" if s_val > 0.1 else ("부정" if s_val < -0.1 else "중립")
        
        news_data.append({
            "그룹": group, "매체명": pub, "제목": f'=HYPERLINK("{item["link"]}", "{item["title"]}")',
            "제목_표시": item["title"], "링크": item["link"], "PICK": pick,
            "게시일": item["pub_date"].strftime('%Y-%m-%d %H:%M'),
            "영향력": round(impact, 2), "감성": sent_label,
            "긍정점수": round(impact, 2) if sent_label == "긍정" else 0,
            "부정점수": round(impact, 2) if sent_label == "부정" else 0
        })
    return pd.DataFrame(news_data)

# ══════════════════════════════════════════════════════════════
#  5. UI 구성
# ══════════════════════════════════════════════════════════════

st.set_page_config(page_title="영향력 뉴스 클리핑", layout="wide")
st.title("🚀 글로벌 이슈 파급력 & 리스크 모니터링")

# ... (사이드바 및 검색어 입력 UI 생략 - 기존 코드와 동일하게 구성) ...

if "df" in st.session_state:
    df = st.session_state["df"]
    
    # --- 상단 분석 지표 ---
    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("종합 파급력", f"{df['영향력'].sum():,.1f} pts")
    m2.metric("그룹 A 기사", f"{(df['그룹']=='그룹 A').sum()}건")
    m3.metric("PICK 기사", f"{(df['PICK']=='PICK').sum()}건")
    m4.metric("리스크 지수", f"{df['부정점수'].sum():,.1f}", delta_color="inverse")

    # --- 시각화 ---
    st.divider()
    chart_col, list_col = st.columns([1.5, 1])
    with chart_col:
        st.write("📊 시간별 파급력 추이")
        fig = px.bar(df, x="게시일", y=["긍정점수", "부정점수"], 
                     color_discrete_map={"긍정점수": "#2ecc71", "부정점수": "#e74c3c"})
        st.plotly_chart(fig, use_container_width=True)
    with list_col:
        st.write("🏆 주요 영향력 기사")
        top_articles = df.sort_values(by="영향력", ascending=False).head(5)
        for _, r in top_articles.iterrows():
            st.caption(f"**[{r['영향력']}pt]** {r['매체명']} | {r['제목_표시']}")

    # --- 기존 리스트 렌더링 (HTML Table) ---
    st.divider()
    st.write("📂 전체 뉴스 클리핑 리스트")
    
    # [이전 코드의 render_table 함수 내용을 여기에 배치하여 리스트 표시]
    # 사용자가 원했던 그룹 A/B/C 배지 및 색상 적용 테이블이 여기에 출력됩니다.
