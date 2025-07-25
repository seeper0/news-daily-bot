#!/usr/bin/env python3
import feedparser
import requests
import os
from datetime import datetime
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# API 설정
GEMINI_API_KEY = os.environ['GEMINI_API_KEY']
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
GMAIL_ADDRESS = os.environ.get('GMAIL_ADDRESS', '')  # 받는 사람 이메일
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD', '')  # Gmail 앱 비밀번호

# RSS 피드 목록
RSS_FEEDS = {
    "스토어 정책": [
        "https://android-developers.googleblog.com/feeds/posts/default",
        "https://developer.apple.com/news/rss/news.rss",
    ],
    "AI 생성": [
        "https://openai.com/blog/rss.xml",
        "https://www.anthropic.com/blog/rss.xml",
        "https://huggingface.co/blog/feed.xml",
    ],
    "3D/언리얼": [
        "https://www.unrealengine.com/en-US/blog/feed",
        "https://80.lv/feed/",
    ]
}

def fetch_feeds():
    """RSS 피드에서 최신 기사 수집"""
    all_articles = {}
    
    # 월요일인지 확인 (주말 뉴스 더 많이 수집)
    is_monday = datetime.now().weekday() == 0
    max_articles = 10 if is_monday else 5  # 월요일은 10개, 평일은 5개
    
    for category, feeds in RSS_FEEDS.items():
        articles = []
        for feed_url in feeds:
            try:
                print(f"📡 피드 수집 중: {feed_url}")
                feed = feedparser.parse(feed_url)
                
                # 피드당 최대 기사 수
                for entry in feed.entries[:max_articles]:
                    title = entry.get('title', 'No title')
                    link = entry.get('link', '')
                    summary = entry.get('summary', '')
                    
                    # 요약이 너무 길면 자르기
                    if summary and len(summary) > 200:
                        summary = summary[:200] + '...'
                    
                    articles.append({
                        'title': title,
                        'link': link,
                        'summary': summary,
                        'source': feed.feed.get('title', 'Unknown')
                    })
                    
            except Exception as e:
                print(f"❌ 피드 수집 오류 {feed_url}: {str(e)}")
                continue
                
        all_articles[category] = articles
    
    return all_articles

def summarize_with_gemini(articles):
    """Gemini API로 한국어 요약 생성"""
    
    # 기사가 없으면 종료
    if not any(articles.values()):
        return None
    
    # 입력 텍스트 준비
    prompt = """당신은 AI와 게임 개발 동향을 전문적으로 요약하는 어시스턴트입니다. 
다음 뉴스들을 한국어로 요약해주세요. 

요약 형식:
1. 먼저 "📌 오늘의 핵심" 섹션에 전체 트렌드를 2-3문장으로 정리
2. 각 카테고리별로 중요한 내용을 2-3문장으로 요약
3. 모든 내용은 한국어로 작성

오늘의 뉴스:
"""
    
    for category, items in articles.items():
        if items:
            prompt += f"\n【{category}】\n"
            for idx, item in enumerate(items[:3], 1):  # 카테고리당 3개까지만
                prompt += f"{idx}. {item['title']}\n"
                if item.get('summary'):
                    prompt += f"   - {item['summary'][:100]}...\n"
    
    # Gemini API 호출
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        
        headers = {
            'Content-Type': 'application/json',
        }
        
        payload = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 1000,
            }
        }
        
        print("🤖 Gemini API 호출 중...")
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        
        # 응답에서 텍스트 추출
        if 'candidates' in result and len(result['candidates']) > 0:
            summary = result['candidates'][0]['content']['parts'][0]['text']
        else:
            return "❌ AI 응답을 받지 못했습니다."
        
        # 최종 메시지 포맷팅 - 요약을 최상단에
        today = datetime.now().strftime("%Y년 %m월 %d일")
        is_monday = datetime.now().weekday() == 0
        title = f"📅 {today} AI/게임 동향" + (" (주말 포함)" if is_monday else "")
        
        final_message = f"{title}\n\n{summary}\n"
        
        # 기사 제목들 수집 (번역을 위해)
        all_titles = []
        for category, items in articles.items():
            if items:
                for item in items[:2]:  # 카테고리당 2개
                    all_titles.append(item['title'])
        
        # 제목들 한번에 번역 요청
        if all_titles:
            translation_prompt = "다음 영어 제목들을 한국어로 번역해주세요. 각 제목은 새 줄로 구분해서 번역만 출력하세요:\n\n" + "\n".join(all_titles)
            
            trans_payload = {
                "contents": [{
                    "parts": [{
                        "text": translation_prompt
                    }]
                }],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 500,
                }
            }
            
            trans_response = requests.post(url, json=trans_payload, headers=headers)
            if trans_response.status_code == 200:
                trans_result = trans_response.json()
                if 'candidates' in trans_result and len(trans_result['candidates']) > 0:
                    translations = trans_result['candidates'][0]['content']['parts'][0]['text'].strip().split('\n')
                else:
                    translations = all_titles  # 번역 실패시 원문 사용
            else:
                translations = all_titles  # 번역 실패시 원문 사용
        
        # 주요 링크 추가 (번역된 제목 사용)
        final_message += "\n\n📎 자세히 보기:\n"
        trans_idx = 0
        for category, items in articles.items():
            if items:
                final_message += f"\n【{category}】\n"
                for item in items[:2]:  # 카테고리당 2개 링크
                    if trans_idx < len(translations):
                        korean_title = translations[trans_idx].strip()
                        # 번역이 비어있거나 너무 짧으면 원문 사용
                        if len(korean_title) < 3:
                            korean_title = item['title']
                    else:
                        korean_title = item['title']
                    
                    final_message += f"• {korean_title}\n  {item['link']}\n"
                    trans_idx += 1
        
        return final_message
        
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP 오류: {e}")
        print(f"응답: {e.response.text}")
        return f"❌ 요약 생성 중 오류 발생: {str(e)}"
    except Exception as e:
        print(f"❌ 일반 오류: {e}")
        return f"❌ 요약 생성 중 오류 발생: {str(e)}"

def send_telegram_message(message):
    """텔레그램으로 메시지 전송"""
    
    if not message:
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # HTML 특수문자 이스케이프
    message = message.replace('&', '&amp;')
    message = message.replace('<', '&lt;')
    message = message.replace('>', '&gt;')
    
    # 텔레그램 메시지 길이 제한 (4096자)
    if len(message) > 4000:
        message = message[:3997] + "..."
    
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
        "parse_mode": "HTML"  # HTML 사용
    }
    
    try:
        print("📤 텔레그램 전송 중...")
        response = requests.post(url, json=data)
        response.raise_for_status()
        print("✅ 텔레그램 메시지 전송 성공")
        return True
    except Exception as e:
        print(f"❌ 텔레그램 전송 실패: {str(e)}")
        if hasattr(e, 'response'):
            print(f"응답: {e.response.text}")
        return False

def send_gmail(subject, body):
    """Gmail로 이메일 전송"""
    
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("⚠️ Gmail 설정이 없어 이메일 전송을 건너뜁니다.")
        return False
    
    try:
        # 이메일 메시지 생성
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = GMAIL_ADDRESS
        msg['To'] = GMAIL_ADDRESS
        
        # HTML 버전 생성 (더 보기 좋게)
        html_body = body.replace('\n', '<br>')
        html_body = html_body.replace('📅', '<h2>📅').replace('\n\n📌', '</h2>\n\n<h3>📌').replace('</h2>\n\n<h3>📌', '</h2><h3>📌')
        html_body = html_body.replace('【', '<h4>【').replace('】', '】</h4>')
        
        # 링크를 클릭 가능하게 만들기
        import re
        html_body = re.sub(r'(https?://[^\s<]+)', r'<a href="\1">\1</a>', html_body)
        
        html_part = MIMEText(html_body, 'html', 'utf-8')
        text_part = MIMEText(body, 'plain', 'utf-8')
        
        msg.attach(text_part)
        msg.attach(html_part)
        
        # Gmail SMTP 서버 연결
        print("📧 Gmail 전송 중...")
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        
        print("✅ Gmail 전송 성공")
        return True
        
    except Exception as e:
        print(f"❌ Gmail 전송 실패: {str(e)}")
        return False

def main():
    """메인 실행 함수"""
    print("="*50)
    print("🚀 일일 뉴스 요약 봇 시작")
    print(f"⏰ 실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)
    
    # 1. RSS 피드 수집
    print("\n📰 뉴스 수집 시작...")
    articles = fetch_feeds()
    
    # 수집된 기사 수 출력
    total_articles = sum(len(items) for items in articles.values())
    print(f"\n📊 수집 완료: 총 {total_articles}개 기사")
    for category, items in articles.items():
        print(f"  - {category}: {len(items)}개")
    
    if total_articles == 0:
        message = "📭 오늘은 새로운 뉴스가 없습니다."
        send_telegram_message(message)
        today = datetime.now().strftime("%Y년 %m월 %d일")
        send_gmail(f"{today} AI/게임 동향", message)
        return
    
    # 2. AI로 요약
    print("\n🤖 AI 요약 생성 중...")
    summary = summarize_with_gemini(articles)
    
    if summary:
        # 3. 텔레그램 전송
        send_telegram_message(summary)
        
        # 4. Gmail 전송
        today = datetime.now().strftime("%Y년 %m월 %d일")
        is_monday = datetime.now().weekday() == 0
        subject = f"{today} AI/게임 동향" + (" - 주말 포함" if is_monday else "")
        send_gmail(subject, summary)
    else:
        error_msg = "❌ 뉴스 요약 생성에 실패했습니다."
        send_telegram_message(error_msg)
        send_gmail("뉴스 요약 실패", error_msg)
    
    print("\n✅ 작업 완료!")
    print("="*50)

if __name__ == "__main__":
    main()
