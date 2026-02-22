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
    "PICK_MULTIPLIER": 1.5, # PICK 기사는 기본 점수의 1.5배
    "TITLE_BONUS": 3.0      # 제목에 키워드 포함 시 가산점
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
#  2. 매핑 테이블 (기존 소스 유지)
# ══════════════════════════════════════════════════════════════

# [기존 소스의 FIXED_MAP, OID_MAP, GROUP_MAP 데이터를 여기에 유지]
# (코드 간결화를 위해 생략되었으나 실제 파일에는 기존 데이터를 모두 포함하세요)
FIXED_MAP = { "apparelnews": "어패럴뉴스", "fashionbiz": "패션비즈", "byline": "바이라인네트워크" } # 예시
OID_MAP = { "001": "연합뉴스", "009": "매일경제", "015": "한국경제" } # 예시
GROUP_MAP = { "매일경제": "그룹 A", "한국경제": "그룹 A", "어패럴뉴스": "그룹 A" } # 예시

# ══════════════════════════════════════════════════════════════
#  3. 핵심 분석 함수 (점수 및 감성)
# ══════════════════════════════════════════════════════════════

def analyze_article_content(link: str, query: str):
    """본문을 긁어 키워드 빈도와 감성 지수를 산출"""
    if "naver.com" not in link:
        return 0.0, 0.0
    try:
        res = requests.get(link, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        soup = BeautifulSoup(res.text, 'html.parser')
        content = soup.select_one('#newsct_article, #articeBody')
        if content:
            text = content.get_text()
            # 1) 키워드 빈도 점수 (최대 5점)
            freq_score = min(text.count(query) * 0.3, 5.0)
            # 2) 감성 분석
            pos = sum(text.count(w) for w in SENTIMENT_DICT["positive"])
            neg = sum(text.count(w) for w in SENTIMENT_DICT["negative"])
            sentiment_val = (pos - neg) / (pos + neg) if (pos + neg) > 0 else 0.0
            return freq_score, sentiment_val
    except: pass
    return 0.0, 0.0

def clean_html_text(text: str) -> str:
    if not text: return ""
    return html.unescape(re.sub(r'<[^>]*>', '', text)).replace('"', "'")

def publisher_from_url(link: str) -> str:
    # [기존 publisher_from_url 로직 유지]
    return "매체명"

def fetch_naver_article_info(link: str) -> dict:
    # [기존 fetch_naver_article_info 로직 유지]
    return {"publisher": "기타", "pick": ""}

# ══════════════════════════════════════════════════════════════
#  4. 수집 및 파이프라인
# ══════════════════════════════════════════════════════════════

def run_search(query: str, client_id: str, client_secret: str, progress_bar, status_text, days: int):
    naver_headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    since = now - timedelta(days=days)

    # Step 1: API 수집
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
    
    # Step 2: 병렬 크롤링 & 분석
    crawl_results = {}
    total = len(raw_items)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_idx = {executor.submit(fetch_naver_article_info, item["link"]): idx for idx, item in enumerate(raw_items)}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            crawl_results[idx] = future.result()
            progress_bar.progress(int((idx+1)/total * 80))

    # Step 3: 데이터 구성 및 점수 산출
    news_data = []
    for idx, item in enumerate(raw_items):
        info = crawl_results.get(idx, {})
        pub, pick = info.get("publisher", "기타"), info.get("pick", "")
        group = GROUP_MAP.get(pub, "")
        
        # --- 파급력 & 리스크 계산 ---
        base = WEIGHT_VAL = WEIGHTS.get(group, 1.0)
        mult = WEIGHTS["PICK_MULTIPLIER"] if pick == "PICK" else 1.0
        t_bonus = WEIGHTS["TITLE_BONUS"] if query.lower() in item["title"].lower() else 0.0
        
        f_score, s_val = 0.0, 0.0
        if group == "그룹 A" or pick == "PICK":
            f_score, s_val = analyze_article_content(item["link"], query)
            
        impact = (base * mult) + t_bonus + f_score
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

st.set_page_config(page_title="영향력 & 리스크 뉴스 클리핑", layout="wide")
st.title("🚀 글로벌 이슈 파급력 & 리스크 모니터링")

# [세션 및 사이드바 설정 부분 기존 코드 유지]

# ... (검색 실행 로직) ...

if "df" in st.session_state:
    df = st.session_state["df"]
    
    # --- 대시보드 ---
    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("종합 파급력", f"{df['영향력'].sum():,.1f} pts")
    c2.metric("기사당 평균", f"{df['영향력'].mean():.1f} pts")
    c3.metric("🟢 호재 지수", f"{df['긍정점수'].sum():,.1f}", delta_color="normal")
    c4.metric("🔴 리스크 지수", f"{df['부정점수'].sum():,.1f}", delta="-위험", delta_color="inverse")

    st.divider()
    chart_col, list_col = st.columns([1.5, 1])
    
    with chart_col:
        st.write("📊 **시간별 긍정/부정 파급력 추이**")
        fig = px.bar(df, x="게시일", y=["긍정점수", "부정점수"], 
                     color_discrete_map={"긍정점수": "#2ecc71", "부정점수": "#e74c3c"})
        st.plotly_chart(fig, use_container_width=True)

    with list_col:
        st.write("🚨 **최고 리스크 기사 (Top 5)**")
        risky = df[df["감성"] == "부정"].sort_values(by="영향력", ascending=False).head(5)
        for _, r in risky.iterrows():
            st.warning(f"**[{r['영향력']}pt]** {r['매체명']}: {r['제목_표시']}")

    # [테이블 렌더링 및 다운로드 로직 유지]
