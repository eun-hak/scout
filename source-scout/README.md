# Source Scout

유튜브 쇼츠 제작용 영상 후보를 모으고, 콘텐츠 적합도와 사용 권리 상태를 함께 관리하는 로컬 MVP입니다.

이 도구의 목적은 공개 게시물을 무단 다운로드하는 것이 아니라 다음 과정을 관리하는 것입니다.

1. 후보 URL과 원작자 정보 기록
2. 쇼츠 소재 적합도 점수화
3. 사용 허락 및 라이선스 상태 추적
4. 검토 대기열 정리
5. CSV 내보내기

## 실행

Python 3.11 이상만 필요하며 외부 패키지를 설치하지 않습니다.

```powershell
cd source-scout
$env:SOURCE_SCOUT_USERNAME = "관리자 아이디"
$env:SOURCE_SCOUT_PASSWORD = "충분히 긴 관리자 비밀번호"
$env:SOURCE_SCOUT_SESSION_SECRET = "32자 이상의 무작위 비밀 문자열"
python -m source_scout
```

프로젝트 루트의 Git 제외 파일 `.env`도 자동으로 읽습니다. 운영 비밀정보는 Git에 커밋하지 마세요.

브라우저에서 <http://127.0.0.1:8765>를 여세요.

다른 포트를 사용하려면:

```powershell
$env:SOURCE_SCOUT_PORT = "9000"
python -m source_scout
```

로그인 세션은 기본 24시간 유지됩니다. `SOURCE_SCOUT_SESSION_HOURS`로 변경할 수 있지만 12시간 미만은 허용하지 않습니다. 운영 서버에서는 `SOURCE_SCOUT_USERNAME`, `SOURCE_SCOUT_PASSWORD`, `SOURCE_SCOUT_SESSION_SECRET`을 반드시 환경변수로 설정하고 Git에 커밋하지 마세요.

운영 서버에서는 `SOURCE_SCOUT_DATA_DIR`을 Git 저장소 밖의 영구 데이터 경로로 지정하세요. Oracle 배포 설정은 `deploy/` 폴더에 있습니다.

## 테스트

```powershell
cd source-scout
python -m unittest discover -s tests -v
```

## 현재 범위

- 후보 추가, 수정, 삭제
- 플랫폼 자동 판별
- 5가지 콘텐츠 평가 항목과 위험도로 종합점수 계산
- 권리 상태, 원작자, 허락 증빙 메모 관리
- 상태 및 테마 필터
- CSV 내보내기
- SQLite 로컬 저장
- Chrome 확장 프로그램을 통한 현재 페이지 원클릭 등록
- 공개 페이지 메타데이터 기반 테마·점수 자동 제안
- 설치형 PWA와 Android 공유 대상
- 기기별 모바일 API 토큰과 iPhone 단축어 연동
- YouTube·Reddit·RSS/Atom 피드 주기적 자동 탐색

## Chrome 원클릭 등록 설치

1. Source Scout 서버를 실행합니다.
2. Chrome 주소창에 `chrome://extensions`를 입력합니다.
3. 오른쪽 위의 **개발자 모드**를 켭니다.
4. **압축해제된 확장 프로그램을 로드합니다**를 선택합니다.
5. 이 프로젝트의 `browser-extension` 폴더를 지정합니다.
6. Instagram, TikTok 또는 YouTube 영상 페이지에서 Source Scout 아이콘을 누릅니다.

확장 프로그램은 현재 탭에서 공개된 제목, 설명, 게시자, 대표 이미지 주소만 읽습니다. 영상을 다운로드하거나 계정을 자동 순회하지 않습니다.

## 모바일 공유

Android에서는 HTTPS 대시보드를 홈 화면에 설치한 뒤 Instagram·TikTok의 공유 대상에서 Source Scout를 선택합니다.

iPhone에서는 대시보드의 **기기 토큰 만들기**로 토큰을 만든 다음 단축어에 다음 요청을 설정합니다.

- URL: `https://scout.jisiknarae.com/api/mobile-share`
- 메서드: `POST`
- 헤더: `Authorization: Bearer 발급받은_토큰`
- JSON 본문: `url`, `title`, `description`, `auto_analyze: true`, `rights_status: unknown`

## 자동 탐색

대시보드에서 YouTube 채널 RSS, Reddit RSS 또는 일반 RSS/Atom 주소를 등록할 수 있습니다. 서버는 기본 60분마다 피드를 확인하고 새 URL만 후보로 저장합니다. 주기는 `SOURCE_SCOUT_DISCOVERY_INTERVAL_MINUTES`로 조정하며 `0`이면 자동 실행을 끕니다.

YouTube 채널 피드 형식:

```text
https://www.youtube.com/feeds/videos.xml?channel_id=채널_ID
```

## Meta Instagram API 연결

다음 환경변수를 설정하면 대시보드에서 Meta 계정 연결과 Instagram 공개 해시태그 탐색을 사용할 수 있습니다.

```text
SOURCE_SCOUT_PUBLIC_URL=https://scout.jisiknarae.com
SOURCE_SCOUT_META_APP_ID=Meta 앱 ID
SOURCE_SCOUT_META_APP_SECRET=Meta 앱 시크릿
SOURCE_SCOUT_META_CONFIG_ID=비즈니스 로그인 구성 ID
```

Meta 앱의 유효한 OAuth 리디렉션 URI에는 다음 주소를 등록합니다.

```text
https://scout.jisiknarae.com/api/meta/callback
```

Instagram 공개 해시태그 검색은 Meta의 `Instagram Public Content Access` 앱 검수 승인이 필요합니다. 연결된 토큰은 API 응답이나 화면에 노출하지 않으며, 연결 해제 시 서버 저장본 삭제와 Meta 권한 취소를 시도합니다.

## 영상 분석 서버 연결

기본 분석은 제목·설명·게시자 정보만 사용하며 화면에 `메타데이터만 분석`으로 표시됩니다. 실제 화면·음성 분석 서버가 준비되면 다음 환경변수로 Webhook을 연결합니다.

```text
SOURCE_SCOUT_ANALYSIS_WEBHOOK=https://analysis.example.com/analyze
SOURCE_SCOUT_ANALYSIS_TOKEN=분석_서버_토큰
```

분석 서버는 후보 JSON을 받고 `theme`, 점수 필드, `analysis_summary`, `analysis_detail`, `script_ideas`를 JSON으로 반환할 수 있습니다.

## 다음 단계

- 브라우저 북마클릿 또는 확장 프로그램으로 현재 페이지 후보 등록
- 허용된 공식 API/RSS 수집기 연결
- 영상 메타데이터 및 중복 URL 검사
- 대본 생성 파이프라인으로 승인 후보 전달
- 사용 허락 메시지 템플릿과 증빙 첨부

상세 설계는 [docs/architecture.md](docs/architecture.md)를 참고하세요.
