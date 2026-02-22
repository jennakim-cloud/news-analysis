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
MAX_WORKERS     = 15  # 병렬 처리량 증가
REQUEST_TIMEOUT = 2   # 타임아웃을 2초로 단축 (로딩 방지 핵심)
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}

WEIGHTS = {
    "그룹 A": 10.0, "그룹 B": 5.0, "그룹 C": 2.0, "": 1.0,
    "PICK_MULTIPLIER": 1.5, "TITLE_BONUS": 3.0
}

BRIEF_KEYWORDS = [
    "브리프", "뉴스픽", "정리", "단신", "게시판", "소식", "모음", "업계", "유통가", "외", "外", 
    "DD퇴근길", "AT패션", "N2 유통", "유통 레이더", "유통갤러리", "유통가 뉴스픽", 
    "레이더M", "마켓인사이트", "공시", "특징주", "오늘의"
]

SENTIMENT_DICT = {
    "positive": ["성장", "흑자", "혁신", "인기", "급증", "돌풍", "1위", "상생", "호조", "성공", "확대", "유치"],
    "negative": ["논란", "위기", "적자", "하락", "감소", "조사", "의혹", "비판", "중단", "우려", "갈등", "부진"]
}

GROUP_BADGE = {
    "그룹 A": "background:#D5F5E3; color:#1e7e34; padding:2px 8px; border-radius:4px; font-weight:bold;",
    "그룹 B": "background:#FEF9E7; color:#856404; padding:2px 8px; border-radius:4px; font-weight:bold;",
    "그룹 C": "background:#FDEBD0; color:#c05621; padding:2px 8px; border-radius:4px; font-weight:bold;",
    "":       "color:#999; padding:2px 8px;",
}

GROUP_COLORS = {"그룹 A": "#D5F5E3", "그룹 B": "#FEF9E7", "그룹 C": "#FDEBD0", "": "#FFFFFF"}

# ══════════════════════════════════════════════════════════════
#  2. 매핑 테이블 (사용자 원본 데이터 유지용 섹션)
# ══════════════════════════════════════════════════════════════

FIXED_MAP = {
    "1conomynews": "1코노미뉴스", "cctimes": "충청타임즈", "chungnamilbo": "충남일보", "dtnews24": "대전뉴스",
    "enetnews": "이넷뉴스", "financialreview": "파이낸셜리뷰", "globalepic": "글로벌에픽", "gokorea": "고코리아",
    "goodmorningcc": "굿모닝충청", "hinews": "하이뉴스", "idaegu": "아이대구", "joongdo": "중도일보",
    "kdfnews": "한국면세뉴스", "ktnews": "강원타임즈", "newslock": "뉴스락", "newsway": "뉴스웨이",
    "opinionnews": "오피니언뉴스", "startuptoday": "스타트업투데이", "straightnews": "스트레이트뉴스",
    "tfmedia": "조세금융신문", "weekly": "주간한국", "wolyo": "월요신문", "womaneconomy": "여성경제신문",
    "lawissue": "로이슈", "newsworker": "뉴스워커", "topdaily": "톱데일리", "wikitree": "위키트리",
    "thepublic": "더퍼블릭", "thebigdata": "빅데이터뉴스", "socialvalue": "소셜밸류", "smartfn": "스마트에프엔",
    "sisacast": "시사캐스트", "siminilbo": "시민일보", "seoultimes": "서울타임즈", "sentv": "서울경제TV",
    "segyebiz": "세계비즈", "pressman": "프레스맨", "popcornnews": "팝콘뉴스", "pointe": "포인트데일리",
    "onews": "열린뉴스통신", "nextdaily": "넥스트데일리", "newswatch": "뉴스워치", "newsquest": "뉴스퀘스트",
    "newsprime": "뉴스프라임", "newsinside": "뉴스인사이드", "mkhealth": "매경헬스", "metroseoul": "메트로신문",
    "meconomynews": "M이코노미", "kbsm": "경북신문", "joongangenews": "중앙이코노미뉴스", "iminju": "민주신문",
    "ilyo": "일요신문", "hankooki": "스포츠한국", "ezyeconomy": "이지경제", "enewstoday": "이뉴스투데이",
    "ekn": "에너지경제", "dizzotv": "디지틀조선일보", "cstimes": "컨슈머타임스", "consumernews": "소비자가만드는신문",
    "ceoscoredaily": "CEO스코어데일리", "breaknews": "브레이크뉴스", "bizwnews": "비즈월드", "beyondpost": "비욘드포스트",
    "asiatime": "아시아타임즈", "apnews": "ap뉴스", "biz": "뉴데일리", "viva100": "브릿지경제",
    "srtimes": "SR타임스", "kpenews": "한국정경신문", "news2day": "뉴스투데이", "fashionbiz": "패션비즈",
    "econovill": "이코노믹리뷰", "businessplus": "비즈니스플러스", "newspim": "뉴스핌", "m-i": "매일일보",
    "pointdaily": "포인트데일리", "ajunews": "아주경제", "asiatoday": "아시아투데이", "xportsnews": "엑스포츠뉴스",
    "sports": "엑스포츠뉴스", "youthdaily": "청년일보", "seoulwire": "서울와이어", "newstomato": "뉴스토마토",
    "widedaily": "와이드경제", "apparelnews": "어패럴뉴스", "biztribune": "비즈트리뷴", "etoday": "이투데이",
    "ngetnews": "뉴스저널리즘", "hansbiz": "한스경제", "byline": "바이라인네트워크", "dealsite": "딜사이트",
    "businesspost": "비즈니스포스트", "dnews": "대한경제", "insight": "인사이트", "slist": "싱글리스트",
    "theviewers": "뷰어스", "daily": "데일리한국", "veritas-a": "베리타스알파", "fortunekorea": "포춘코리아",
    "huffingtonpost": "허프포스트", "mediapen": "미디어펜", "paxetv": "팍스경제TV", "shinailbo": "신아일보",
    "pinpointnews": "핀포인트뉴스", "sisunnews": "시선뉴스", "sisaon": "시사온", "smarttoday": "스마트투데이",
    "ziksir": "직썰", "job-post": "잡포스트", "issuenbiz": "이슈앤비즈", "fashionn": "패션엔",
    "thebell": "더벨", "ftoday": "파이낸셜투데이", "newspost": "뉴스포스트", "econonews": "이코노뉴스",
    "thevaluenews": "더밸류뉴스", "megaeconomy": "메가경제", "greened": "녹색경제신문",
    "sisajournal-e": "시사저널이코노미", "digitaltoday": "디지털투데이", "asisaa": "아시아에이",
}

OID_MAP = {
    "001": "연합뉴스", "002": "프레시안", "003": "뉴시스", "004": "내일신문", "005": "국민일보", "008": "머니투데이",
    "009": "매일경제", "011": "서울경제", "014": "파이낸셜뉴스", "015": "한국경제", "016": "헤럴드경제", "018": "이데일리",
    "020": "동아일보", "021": "문화일보", "022": "세계일보", "023": "조선일보", "025": "중앙일보", "028": "한겨레",
    "029": "디지털타임스", "030": "전자신문", "031": "아이뉴스24", "032": "경향신문", "034": "이코노미스트", "038": "한국일보",
    "052": "YTN", "055": "SBS", "056": "KBS", "057": "MBN", "065": "스포츠서울", "076": "스포츠조선", "079": "노컷뉴스",
    "081": "서울신문", "082": "부산일보", "088": "매일신문", "092": "지디넷코리아", "117": "마이데일리", "119": "데일리안",
    "123": "조세일보", "138": "디지털데일리", "143": "쿠키뉴스", "144": "스포츠월드", "214": "MBC", "215": "한국경제TV",
    "241": "시사IN", "243": "이코노미스트", "277": "아시아경제", "584": "아시아투데이", "293": "블로터", "321": "브릿지경제",
    "323": "한국섬유신문", "324": "이투데이", "329": "뉴데일리", "366": "조선비즈", "374": "SBS Biz", "383": "한국정경신문",
    "410": "어패럴뉴스", "417": "머니S", "421": "뉴스1", "437": "JTBC", "445": "대한경제", "448": "서울와이어",
    "449": "TV조선", "465": "여성경제신문", "468": "스포츠경향", "512": "뉴스핌", "529": "싱글리스트", "586": "시사저널e",
    "629": "뉴스토마토", "645": "아주경제", "648": "비즈워치", "654": "비즈트리뷴", "658": "뷰어스", "660": "청년일보",
    "929": "디지털투데이", "239": "바이라인네트워크", "273": "패션비즈"
}

GROUP_MAP = {
    "1코노미뉴스":"그룹 B","CBS노컷뉴스":"그룹 A","CEO스코어데일리":"그룹 C","EBN":"그룹 B","FETV":"그룹 C",
    "IT조선":"그룹 C","KBS":"그룹 A","K패션뉴스":"그룹 C","MBC":"그룹 A","MBN":"그룹 A","S-저널":"그룹 C",
    "SBS":"그룹 A","SBS Biz":"그룹 A","SR타임스":"그룹 C","TV조선":"그룹 A","YTN":"그룹 A","경향신문":"그룹 A",
    "공공뉴스":"그룹 B","국민일보":"그룹 A","국제섬유신문":"그룹 A","굿모닝경제":"그룹 C","남다른디테일":"그룹 B",
    "내일신문":"그룹 A","녹색경제신문":"그룹 C","뉴데일리":"그룹 A","뉴스1":"그룹 A","뉴스워치":"그룹 C",
    "뉴스워커":"그룹 C","뉴스웨이":"그룹 B","뉴스인사이드":"그룹 C","뉴스저널리즘":"그룹 B","뉴스토마토":"그룹 C",
    "뉴스톱":"그룹 B","뉴스투데이":"그룹 B","뉴스포스트":"그룹 C","뉴스핌":"그룹 A","뉴시스":"그룹 A","뉴시ian":"그룹 C",
    "대한경제":"그룹 B","더리브스":"그룹 C","더밸류뉴스":"그룹 B","더벨":"그룹 B","더스쿠프":"그룹 B","더스탁":"그룹 B",
    "더팩트":"그룹 A","더피알":"그룹 C","데일리안":"그룹 A","데일리한국":"그룹 A","동아닷컴":"그룹 C","동아일보":"그룹 A",
    "동행미디어 시대":"그룹 A","디지털데일리":"그룹 A","디지털타임스":"그룹 A","디지털투데이":"그룹 B",
    "디지틀조선일보":"그룹 C","디토앤디토":"그룹 A","딜사이트":"그룹 B","딜사이트TV":"그룹 C","로이슈":"그룹 B",
    "마이데일리":"그룹 B","매경이코노미":"그룹 B","매경헬스":"그룹 B","매일경제":"그룹 A","매일경제 레이더M":"그룹 B",
    "매일경제TV":"그룹 C","매일신문":"그룹 B","매일일보":"그룹 B","머니투데이":"그룹 A","머니투데이방송":"그룹 A",
    "메가경제":"그룹 C","메트로신문":"그룹 C","문화일보":"그룹 A","문화저널21":"그룹 C","미디어펜":"그룹 C",
    "바이라인네트워크":"그룹 A","부산일보":"그룹 B","뷰어스":"그룹 C","브릿지경제":"그룹 B","블로터":"그룹 A",
    "비즈니스워치":"그룹 A","비즈니스포스트":"그룹 B","비즈니스플러스":"그룹 B","비즈트리뷴":"그룹 C","비즈한국":"그룹 C",
    "서울경제":"그룹 A","서울경제TV":"그룹 A","서울신문":"그룹 A","서울와이어":"그룹 C","서울파이낸스":"그룹 C",
    "세계비즈":"그룹 C","세계일보":"그룹 A","소비자가만드는신문":"그룹 B","소셜밸류":"그룹 C","스마트투데이":"그룹 C",
    "스트레이트뉴스":"그룹 C","스포츠조선":"그룹 B","스포츠한국":"그룹 B","시사오늘":"그룹 C","시사위크":"그룹 C",
    "시사저널이코노미":"그룹 C","시사캐스트":"그룹 C","신아일보":"그룹 C","싱글리스트":"그룹 C","아시아경제":"그룹 A",
    "아시아타임즈":"그룹 B","아시아투데이":"그룹 A","아웃스탠딩":"그룹 A","아이뉴스24":"그룹 A","아주경제":"그룹 A",
    "아주일보":"그룹 C","알파경제":"그룹 B","약업신문":"그룹 C","어패럴뉴스":"그룹 A","에너지경제":"그룹 B",
    "여성경제신문":"그룹 C","연합 인포맥스":"그룹 B","연합뉴스":"그룹 A","연합뉴스TV":"그룹 A","오늘경제":"그룹 C",
    "월요신문":"그룹 B","위키리크스한국":"그룹 B","위키트리":"그룹 C","이뉴스투데이":"그룹 B","이데일리":"그룹 A",
    "이코노미스트":"그룹 B","이코노믹리뷰":"그룹 B","이투데이":"그룹 A","인베스트조선":"그룹 B","인사이트":"그룹 C",
    "인사이트코리아":"그룹 B","일간스포츠":"그룹 B","일요서울":"그룹 C","일요신문":"그룹 C","전자신문":"그룹 A",
    "조선비즈":"그룹 A","조선일보":"그룹 A","주간한국":"그룹 B","중소기업신문":"그룹 C",
    "중앙선데이":"그룹 A","중앙이코노미뉴스":"그룹 C","중앙일보":"그룹 A",
    "지디넷코리아":"그룹 A","청년일보":"그룹 C","커넥터스":"그룹 C","컨슈머타임즈":"그룹 B",
    "코리아중앙데일리":"그룹 A","코리아타임스":"그룹 A","코리아헤럴드":"그룹 A","쿠키뉴스":"그룹 A",
    "테넌트뉴스":"그룹 A","테크엠":"그룹 A","토요경제":"그룹 C","톱데일리":"그룹 B","투데이신문":"그룹 B",
    "투데이코리아":"그룹 C","파이낸셜뉴스":"그룹 A","파이낸셜리뷰":"그룹 C","파이낸셜투데이":"그룹 C",
    "파이낸셜포스트":"그룹 C","팝콘뉴스":"그룹 C","패션비즈":"그룹 A","패션인사이트":"그룹 A","패션포스트":"그룹 A",
    "포인트데일리":"그룹 C","프라임경제":"그룹 C","하이뉴스":"그룹 C","한겨레":"그룹 A","한경비즈니스":"그룹 B",
    "한국경제":"그룹 A","한국경제TV":"그룹 A","한국금융신문":"그룹 C","한국면세뉴스":"그룹 C","한국섬유신문":"그룹 A",
    "한국일보":"그룹 A","한국정경신문":"그룹 C","한스경제":"그룹 B","허프포스트":"그룹 C","헤럴드경제":"그룹 A",
    "현대경제신문":"그룹 C","후지TV":"그룹 C","MTN":"그룹 A",
}

# ══════════════════════════════════════════════════════════════
#  3. 지능형 분석 엔진 (속도 최적화 버전)
# ══════════════════════════════════════════════════════════════

def analyze_article_content(link: str, query: str, title: str, is_pick: bool):
    """속도 저하를 막기 위해 제목을 우선 분석하고, 본문은 빠르게 시도"""
    penalty_ratio = 1.0
    freq_score = 0.0
    sentiment_val = 0.0
    p_mult = 1.0
    
    # [1] 제목 기반 즉각 분석 (로딩 없이 즉시 실행)
    list_markers = title.count('·') + title.count(',') + title.count('|') + title.count('/')
    is_brief_corner = any(k in title for k in BRIEF_KEYWORDS)
    
    if is_brief_corner or list_markers >= 2:
        query_pos = title.find(query)
        if 0 <= query_pos <= 12: # 제목 서두에 있으면 주인공 인정
            penalty_ratio = 0.8
        else:
            penalty_ratio = 0.45 # 나열형 강력 패널티 (10pt -> 4.5pt)

    # [2] 본문 크롤링 (Timeout을 아주 짧게 설정하여 로딩 방지)
    try:
        # 네이버 뉴스거나, 어패럴뉴스와 같이 점수 보정이 꼭 필요한 매체만 시도
        can_crawl = any(domain in link for domain in ["naver.com", "apparelnews", "ajunews", "biztribune"])
        
        if can_crawl:
            res = requests.get(link, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            soup = BeautifulSoup(res.text, 'html.parser')
            content = soup.select_one('#newsct_article, #articeBody, .view_con, #articleBodyContents, .article_view')
            
            if content:
                text = content.get_text()
                text_len = len(text)
                count = text.count(query)
                
                density = (count * 1000) / text_len if text_len > 0 else 0
                is_listing = True if text_len > 1000 and density < 1.5 else False
                
                freq_score = min(density * 2.0, 5.0)
                if query in text[:200]: freq_score += 1.5 
                
                # 나열형 기사는 PICK 가중치 취소
                p_mult = WEIGHTS["PICK_MULTIPLIER"] if (is_pick and not is_listing) else 1.0
                
                # 감성 분석
                pos = sum(text.count(w) for w in SENTIMENT_DICT["positive"])
                neg = sum(text.count(w) for w in SENTIMENT_DICT["negative"])
                sentiment_val = (pos - neg) / (pos + neg) if (pos + neg) > 0 else 0.0
            else:
                # 본문을 못 찾을 경우 제목 페널티 유지
                if penalty_ratio < 1.0: freq_score = 0.5
        else:
            # 크롤링 미지원 매체는 제목 기반 분석값만 반환
            if penalty_ratio < 1.0: freq_score = 0.5
            
    except:
        # 오류 발생 시 기다리지 않고 즉시 반환
        if penalty_ratio < 1.0: freq_score = 0.5
        
    return freq_score, sentiment_val, penalty_ratio, p_mult

def publisher_from_url(link: str) -> str:
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

def fetch_naver_article_info(link: str) -> dict:
    res_info = {"publisher": publisher_from_url(link), "pick": ""}
    if "naver.com" not in link: return res_info
    try:
        # 네이버 기사는 속도가 빠르므로 정보를 긁어옴
        res = requests.get(link, headers=HEADERS, timeout=1.5)
        soup = BeautifulSoup(res.text, 'html.parser')
        logo = soup.select_one('a.press_logo img, .media_end_head_top a img')
        if logo: res_info["publisher"] = logo.get('alt', '').strip()
        if soup.select_one('.is_pick, .media_end_head_journalist_edit_label') or "PICK" in res.text:
            res_info["pick"] = "PICK"
    except: pass
    return res_info

def run_search(query, client_id, client_secret, progress_bar, start_dt, end_dt):
    naver_headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    kst = timezone(timedelta(hours=9))
    
    raw_items = []
    # 검색량을 200개로 조절하여 속도 확보
    for start_index in range(1, 201, 100):
        url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&start={start_index}&sort=date"
        res = requests.get(url, headers=naver_headers)
        if res.status_code != 200: break
        items = res.json().get('items', [])
        for item in items:
            pub_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').replace(tzinfo=kst)
            if start_dt <= pub_date <= end_dt:
                raw_items.append({"pub_date": pub_date, "link": item.get('link', ''), "title": html.unescape(re.sub(r'<[^>]*>', '', item.get('title', '')))})
    
    if not raw_items: return None

    crawl_results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_idx = {executor.submit(fetch_naver_article_info, item["link"]): i for i, item in enumerate(raw_items)}
        for i, f in enumerate(as_completed(future_to_idx)):
            crawl_results[future_to_idx[f]] = f.result()
            progress_bar.progress(int((i+1)/len(raw_items)*60))

    news_data = []
    for idx, item in enumerate(raw_items):
        info = crawl_results.get(idx, {})
        pub, pick = info.get("publisher", "기타매체"), info.get("pick", "")
        group = GROUP_MAP.get(pub, "")
        base = WEIGHTS.get(group, 1.0)
        t_bonus = WEIGHTS["TITLE_BONUS"] if query.lower() in item["title"].lower() else 0.0
        
        f_score, s_val, p_ratio, p_mult = analyze_article_content(item["link"], query, item["title"], (pick == "PICK"))
        
        impact = ((base * p_mult) + t_bonus + f_score) * p_ratio
        sent = "긍정" if s_val > 0.1 else ("부정" if s_val < -0.1 else "중립")
        
        news_data.append({
            "그룹": group, "매체명": pub, "제목": f'=HYPERLINK("{item["link"]}", "{item["title"]}")',
            "제목_표시": item["title"], "링크": item["link"], "PICK": pick,
            "게시일": item["pub_date"].strftime('%Y-%m-%d %H:%M'), "pts": round(impact, 2), "감성": sent,
            "긍정pts": round(impact, 2) if sent == "긍정" else 0, "부정pts": round(impact, 2) if sent == "부정" else 0
        })
    return pd.DataFrame(news_data)

# ══════════════════════════════════════════════════════════════
#  4. UI
# ══════════════════════════════════════════════════════════════
st.set_page_config(page_title="커버리지 분석", layout="wide")
st.title("🚀 이슈 파급력 & 리스크 모니터링")

with st.sidebar:
    st.header("🔐 시스템 상태")
    try:
        c_id = st.secrets["naver"]["client_id"]; c_secret = st.secrets["naver"]["client_secret"]
        st.success("API 연결됨")
    except:
        st.error("API Secrets 누락"); st.stop()

st.divider()
c1, c2, c3 = st.columns([2, 2, 1])
with c1: query = st.text_input("검색 키워드", placeholder="예: 무신사 서울숲")
with c2: 
    today = datetime.now(); date_range = st.date_input("기간 설정", value=(today - timedelta(days=7), today), max_value=today)
with c3: st.write(""); search_btn = st.button("🔍 데이터 분석", type="primary", use_container_width=True)

if search_btn and query:
    if len(date_range) != 2: st.warning("시작일과 종료일을 선택하세요.")
    else:
        kst = timezone(timedelta(hours=9))
        start_dt = datetime.combine(date_range[0], datetime.min.time()).replace(tzinfo=kst)
        end_dt = datetime.combine(date_range[1], datetime.max.time()).replace(tzinfo=kst)
        pb = st.progress(0)
        st.session_state["df"] = run_search(query, c_id, c_secret, pb, start_dt, end_dt)
        st.session_state["query_val"] = query

if "df" in st.session_state and st.session_state["df"] is not None:
    df = st.session_state["df"]
    
    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("종합 파급력", f"{df['pts'].sum():,.1f} pts")
    m2.metric("평균 파급력", f"{df['pts'].mean():.1f} pts")
    m3.metric("🟢 호재 지수", f"{df['긍정pts'].sum():,.1f} pts")
    m4.metric("🔴 리스크 지수", f"{df['부정pts'].sum():,.1f} pts", delta_color="inverse")

    st.divider()
    lc, rc = st.columns([1.5, 1])
    with lc:
        st.plotly_chart(px.bar(df, x="게시일", y=["긍정pts", "부정pts"], color_discrete_map={"긍정pts": "#2ecc71", "부정pts": "#e74c3c"}), use_container_width=True)
    with rc:
        st.write("🏆 주요 기사 (Top 5)")
        for _, r in df.sort_values("pts", ascending=False).head(5).iterrows():
            st.caption(f"**[{r['pts']} pts]** {r['매체명']} | {r['제목_표시']}")
        st.write("---")
        st.write("🚨 리스크 기사 (Top 5)")
        risk_t5 = df[df["감성"] == "부정"].sort_values("pts", ascending=False).head(5)
        for _, r in risk_t5.iterrows(): st.warning(f"**[{r['pts']} pts]** {r['매체명']} | {r['제목_표시']}")

    st.divider()
    st.subheader("📂 뉴스 상세 리스트")
    f1, f2, f3, f4 = st.columns([2, 1, 2, 1.5])
    with f1: sel_groups = st.multiselect("매체 그룹", ["그룹 A", "그룹 B", "그룹 C", "미분류"], default=["그룹 A", "그룹 B", "그룹 C", "미분류"])
    with f2: st.write(""); pick_only = st.checkbox("PICK 기사")
    with f3: sel_sents = st.multiselect("감성", ["긍정", "중립", "부정"], default=["긍정", "중립", "부정"])
    with f4: sort_by = st.selectbox("정렬", ["포인트 높은순", "최신순", "포인트 낮은순"])

    mask = pd.Series([True] * len(df), index=df.index)
    mask &= df["그룹"].isin([("" if g=="미분류" else g) for g in sel_groups])
    if pick_only: mask &= df["PICK"] == "PICK"
    mask &= df["감성"].isin(sel_sents)
    
    df_f = df[mask].copy()
    if sort_by == "포인트 높은순": df_f = df_f.sort_values("pts", ascending=False)
    elif sort_by == "포인트 낮은순": df_f = df_f.sort_values("pts", ascending=True)
    else: df_f = df_f.sort_values("게시일", ascending=False)

    def render_table(df_view):
        rows = ""
        for _, row in df_view.iterrows():
            badge = f'<span style="{GROUP_BADGE.get(row["그룹"], GROUP_BADGE[""])}">{row["그룹"] if row["그룹"] else "미분류"}</span>'
            pick = '<span style="color:#e74c3c;font-weight:bold;">PICK</span>' if row["PICK"] == "PICK" else ""
            sent_style = 'color:#e74c3c;font-weight:bold;' if row["감성"] == "부정" else ('color:#2ecc71;' if row["감성"] == "긍정" else '')
            rows += f'<tr style="background:{GROUP_COLORS.get(row["그룹"], "#FFF")}; border-bottom:1px solid #eee;">' \
                    f'<td style="padding:10px;">{badge}</td><td>{row["매체명"]}</td>' \
                    f'<td><a href="{row["링크"]}" target="_blank" style="text-decoration:none; color:#1f1f1f;">{row["제목_표시"]}</a></td>' \
                    f'<td style="text-align:center;">{pick}</td><td style="text-align:center; {sent_style}">{row["감성"]}</td>' \
                    f'<td style="font-weight:bold;">{row["pts"]}</td><td>{row["게시일"]}</td></tr>'
        return f'<table style="width:100%; border-collapse:collapse;"><thead><tr style="background:#2C3E50; color:white; text-align:left;"><th>그룹</th><th>매체명</th><th>제목</th><th>PICK</th><th>감성</th><th>pts</th><th>게시일</th></tr></thead><tbody>{rows}</tbody></table>'

    st.markdown(render_table(df_f), unsafe_allow_html=True)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_f[["그룹", "매체명", "제목", "PICK", "게시일", "pts", "감성"]].to_excel(writer, index=False)
    st.download_button("📥 엑셀 다운로드", output.getvalue(), f"news_report.xlsx", type="primary", use_container_width=True)
