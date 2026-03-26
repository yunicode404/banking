import os
import json
import datetime
import requests
from bs4 import BeautifulSoup
import yfinance as yf
from pykrx import stock
import gspread

# 텔레그램 설정
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    requests.post(url, data=payload)

def run_morning():
    msg = "🌅 <b>[오전 시황 및 뉴스 요약]</b>\n\n"
    
    # 1. 뉴스 요약 (Google News RSS 활용)
    keywords = ['반도체', 'AI', '전쟁', '국채']
    for kw in keywords:
        url = f"https://news.google.com/rss/search?q={kw}&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(url)
        soup = BeautifulSoup(res.content, 'xml')
        items = soup.find_all('item')[:2]
        msg += f"📌 <b>{kw}</b>\n"
        for item in items:
            msg += f"- <a href='{item.link.text}'>{item.title.text}</a>\n"
        msg += "\n"
        
    # 2. 위기 감지 (환율)
    try:
        usd_krw = yf.Ticker("KRW=X").history(period="1d")['Close'].iloc[-1]
        if usd_krw >= 1380:
            msg += f"🚨 <b>[위기 감지]</b> 환율 급등 (현재 {usd_krw:.1f}원).\n달러 자산 및 미국 국채 직접 매수(TLT 등) 비중 확대를 권고합니다.\n\n"
    except Exception:
        pass
        
    msg += "💡 <b>[오늘의 포지션 제안]</b>\n시장 변동성에 유의하며, 보수적인 접근 및 원칙 매매를 추천합니다."
    send_telegram(msg)

def run_afternoon():
    msg = "🌇 <b>[오후 마감 시황 및 포트폴리오 점검]</b>\n\n"
    
    # 1. KRX 외인/기관 Top 5
    try:
        today_str = datetime.datetime.now().strftime("%Y%m%d")
        # 주말/휴일 등 장 미열림 대응을 위해 가장 최근 영업일 조회
        b_days = stock.get_business_days_dates(today_str[:6]+"01", today_str)
        last_bday = b_days[-1].strftime("%Y%m%d")
        
        f_buy = stock.get_market_net_purchases_of_equities_by_ticker(last_bday, last_bday, "KOSPI", "외국인")
        f_buy_top5 = f_buy.sort_values('순매수거래대금', ascending=False).head(5)
        
        msg += "🛒 <b>[KOSPI 외국인 순매수 Top 5]</b>\n"
        for _, row in f_buy_top5.iterrows():
            msg += f"- {row['종목명']}\n"
        msg += "\n"
    except Exception as e:
        msg += f"KRX 데이터 조회 실패: {e}\n\n"
        
    # 2. 개인화 알림 (구글 시트 포트폴리오 연동)
    msg += "📊 <b>[내 포트폴리오 점검]</b>\n"
    try:
        creds_json = os.getenv('GOOGLE_SHEETS_CREDENTIALS')
        sheet_name = os.getenv('GOOGLE_SHEET_NAME', 'MyPortfolio')
        
        creds_dict = json.loads(creds_json)
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open(sheet_name).sheet1
        records = sh.get_all_records()
        
        for row in records:
            name = row.get('종목명', '')
            ticker = str(row.get('티커', '')).strip() # 예: 000270.KS
            avg_price = float(row.get('평단가', 0))
            
            if not name or not ticker or avg_price == 0:
                continue
                
            # 현재가 조회 (Yahoo Finance 기준)
            ticker_obj = yf.Ticker(ticker)
            curr_price_df = ticker_obj.history(period="1d")
            if curr_price_df.empty:
                continue
                
            current_price = curr_price_df['Close'].iloc[-1]
            return_rate = (current_price - avg_price) / avg_price * 100
            
            advice = "홀딩"
            if return_rate <= -5.0:
                advice = "⚠️ 물타기 금지"
            elif return_rate >= 10.0:
                advice = "✅ 익절 검토"
                
            msg += f"- {name}: {return_rate:.2f}% ({advice})\n"
            
    except Exception as e:
        msg += f"포트폴리오 조회 실패 (시트 설정/티커를 확인하세요): {e}\n"
        
    send_telegram(msg)

if __name__ == "__main__":
    # GitHub Actions는 UTC 기준. (KST = UTC + 9)
    now_kst = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    
    # 오전 8:30 실행 시 KST 기준 12시 이전이므로 morning_routine 실행
    if now_kst.hour < 12:
        run_morning()
    else:
        run_afternoon()