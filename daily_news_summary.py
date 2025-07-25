#!/usr/bin/env python3
import feedparser
import requests
import os
from datetime import datetime
import time

# API 설정
GEMINI_API_KEY = os.environ['GEMINI_API_KEY']
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

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
다음 뉴스들을 한국어로 요약해주세요. 각 카테고리별로 중요한 내용을 2-3문장으로 요약하고, 
마지막에 오늘의 핵심 트렌드를 한 문장으로 정리해주세요.

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
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
        
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
        
        # 최종 메시지 포맷팅
        today = datetime.now().strftime("%Y년 %m월 %d일")
        final_message = f"📅 {today} AI/게임 동향\n\n{summary}\n"
        
        # 주요 링크 추가
        final_message += "\n\n📎 자세히 보기:\n"
        for category, items in articles.items():
            if items:
                final_message += f"\n【{category}】\n"
                for item in items[:2]:  # 카테고리당 2개 링크
                    final_message += f"• {item['title']}\n  {item['link']}\n"
        
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
    
    # 텔레그램 메시지 길이 제한 (4096자)
    if len(message) > 4000:
        message = message[:3997] + "..."
    
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
        "parse_mode": "Markdown"  # HTML 대신 Markdown 사용
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
        return
    
    # 2. AI로 요약
    print("\n🤖 AI 요약 생성 중...")
    summary = summarize_with_gemini(articles)
    
    if summary:
        # 3. 텔레그램 전송
        send_telegram_message(summary)
    else:
        send_telegram_message("❌ 뉴스 요약 생성에 실패했습니다.")
    
    print("\n✅ 작업 완료!")
    print("="*50)

if __name__ == "__main__":
    main()
