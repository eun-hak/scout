# Meta 앱 검수 제출 패키지 — Source Scout

작성일: 2026-08-18  
앱: Scout  
서비스 URL: https://scout.jisiknarae.com  
검수 대상 기능: Instagram Public Content Access

> 이 문서는 제출 초안이다. 실제 Scout 화면에서 Meta 로그인, 해시태그 검색, 결과 표시, 연결 해제 기능이 완성된 뒤 화면과 정확히 일치하는지 확인하고 제출한다. 구현되지 않은 기능을 작동한다고 주장하지 않는다.

## 1. 서비스 한 줄 설명

### 한국어

Source Scout는 콘텐츠 제작자가 공개 Instagram 게시물을 해시태그로 발견하고, 원본 게시물 링크와 제한된 공개 메타데이터를 검토하며, 원작자 및 사용 허락 상태를 기록하는 콘텐츠 조사·권리 관리 도구입니다.

### English

Source Scout is a content research and rights-review tool that helps a creator discover public Instagram posts by hashtag, review limited public metadata with a direct link to the original post, and record creator attribution and permission status before any reuse decision is made.

## 2. 검수 핵심 원칙

- Instagram 영상 파일을 API로 다운로드하거나 재호스팅하지 않는다.
- 검색 결과는 원본 Instagram 게시물로 연결한다.
- 공개 게시물의 제한된 메타데이터만 후보 평가에 사용한다.
- 공개 게시물을 찾았다는 사실을 재사용 허락으로 간주하지 않는다.
- 사용자는 원작자와 라이선스를 확인하고 권리 상태를 기록한다.
- `permitted`, `licensed`, `public_domain` 중 하나가 확인되지 않으면 Scout에서 게시용 승인 상태로 변경할 수 없다.
- 데이터를 판매하거나 광고 타기팅, 감시, 개인 프로파일링에 사용하지 않는다.

## 3. Instagram Public Content Access 요청 사유

### Meta 제출용 영문 초안

Source Scout uses Instagram Public Content Access only to let an authenticated creator search for public Instagram media by a hashtag that the creator explicitly enters. The app displays a limited set of public metadata returned by the Instagram Graph API, including the original post link, creator attribution when available, caption, timestamp, media type, thumbnail or media preview where permitted, and public engagement metrics where permitted.

The purpose is content research and rights review. Results are saved as research candidates with a direct link back to the original Instagram post. Source Scout does not treat discovery as permission to reuse a post. The user must separately verify the creator and record permission, license, or public-domain evidence before a candidate can be marked approved. The app does not sell Meta data, build user profiles, perform surveillance, or download and rehost Instagram video files through this feature.

This feature is initiated by the user, limited to hashtags entered by the user, and the returned data is shown only inside the authenticated research workspace.

### 한국어 참고 번역

Source Scout는 인증된 콘텐츠 제작자가 직접 입력한 해시태그로 공개 Instagram 미디어를 검색할 수 있도록 하기 위해서만 Instagram Public Content Access를 사용합니다. 앱은 Instagram Graph API가 반환하는 제한된 공개 메타데이터와 원본 게시물 링크를 표시합니다.

검색 결과는 콘텐츠 조사 및 권리 검토 후보로 저장됩니다. 발견 자체를 콘텐츠 재사용 허락으로 취급하지 않으며, 사용자는 후보를 승인하기 전에 원작자와 사용 허락·라이선스·퍼블릭 도메인 근거를 별도로 확인해야 합니다. Meta 데이터를 판매하거나 프로파일링·감시 목적으로 사용하지 않으며, 이 기능으로 Instagram 영상 파일을 다운로드하거나 재호스팅하지 않습니다.

## 4. 권한별 제출 설명

실제로 신청하는 권한만 제출한다. 자동 게시 기능 구현 전에는 `instagram_content_publishing`을 신청하지 않는다.

### `instagram_basic`

Source Scout uses `instagram_basic` to identify the Instagram professional account connected by the authenticated user and to display the account connection status inside the app. This establishes the Instagram professional account context required for the user-initiated public hashtag research workflow. The app does not access consumer Instagram accounts.

### `pages_show_list`

Source Scout uses `pages_show_list` to show the Facebook Pages that the authenticated user manages so the user can select the Page connected to the Instagram professional account used for the research workflow. The Page list is not shared with third parties or used for advertising.

### `pages_read_engagement`

Source Scout uses `pages_read_engagement` as required by the Instagram API with Facebook Login to confirm the selected Page and its connected Instagram professional account. The app uses this only to establish the account context required for the user-initiated hashtag search feature.

### `business_management`

Request this permission only if the implemented Meta login flow and API calls demonstrably require it. If the final implementation works without it, remove it from the submission to keep the requested access minimal.

## 5. 검수자용 테스트 안내 영문 초안

### Prerequisites

- Open `https://scout.jisiknarae.com` in a desktop browser.
- Use the Source Scout reviewer credentials supplied in the confidential App Review credential fields.
- Use a Meta test account that has access to a Facebook Page connected to an Instagram professional account.

### Test steps

1. Sign in to Source Scout using the reviewer credentials.
2. Open the **Instagram Discovery** section.
3. Click **Connect Meta account**.
4. Complete Facebook Login and grant only the permissions shown in the review request.
5. Return to Source Scout and confirm that the connected Facebook Page and Instagram professional account are displayed.
6. Enter the hashtag `woodworking` in the hashtag search field and click **Search public Instagram posts**.
7. Confirm that Source Scout displays results with limited public metadata and a link labeled **Open original on Instagram**.
8. Open one result and confirm that the original post opens on Instagram.
9. Save one result as a candidate. Set its rights status to **Unknown** and confirm that the app does not allow the candidate to be marked **Approved**.
10. Change the rights status to **Permission granted** only for the test record and add a test evidence note. Confirm that the candidate can now be marked **Approved**.
11. Open **Meta connection settings** and click **Disconnect** to revoke the app connection and remove the stored access token.

## 6. 화면 녹화 대본

권장 길이: 2~4분. 브라우저 주소창과 마우스 포인터가 보이도록 녹화한다. 실제 비밀번호와 전체 액세스 토큰은 영상에 노출하지 않는다.

1. `scout.jisiknarae.com` 주소와 로그아웃 상태를 보여준다.
2. 검수용 Scout 계정으로 로그인한다.
3. Instagram Discovery 영역에서 연결되지 않은 상태를 보여준다.
4. **Connect Meta account**를 누른다.
5. Facebook 로그인과 요청 권한 목록을 빠짐없이 보여주고 승인한다.
6. Scout로 돌아와 연결된 페이지와 Instagram 프로페셔널 계정명을 보여준다.
7. `woodworking`을 입력하고 검색한다.
8. 실제 API 결과와 각 결과의 원본 Instagram 링크를 보여준다.
9. 결과 하나를 후보로 저장한다.
10. 권리 상태가 미확인일 때 승인할 수 없다는 메시지를 보여준다.
11. 테스트용 허락 증빙을 입력하고 승인 상태 변경을 보여준다.
12. Meta 연결 해제 화면과 데이터 삭제 안내 링크를 보여준다.
13. 공개 정책 페이지 3개가 로그인 없이 열리는 것을 짧게 보여준다.

## 7. 공개 URL

- Privacy Policy: `https://scout.jisiknarae.com/privacy`
- Terms of Service: `https://scout.jisiknarae.com/terms`
- User Data Deletion: `https://scout.jisiknarae.com/data-deletion`

## 8. 제출 전 체크리스트

- [ ] Meta OAuth 콜백 URL이 HTTPS 운영 도메인으로 설정됨
- [ ] Meta 로그인부터 Scout 복귀까지 실제로 작동함
- [ ] 연결된 Page와 Instagram 프로페셔널 계정이 표시됨
- [ ] 해시태그 검색이 실제 Graph API 요청으로 수행됨
- [ ] 결과에 원본 Instagram 링크가 있음
- [ ] 영상 파일을 API로 다운로드하거나 재호스팅하지 않음
- [ ] 권리 미확인 후보의 승인 차단이 영상에서 확인됨
- [ ] Meta 연결 해제 시 저장 토큰이 삭제됨
- [ ] 검수자용 Scout 계정이 작동함
- [ ] 정책 페이지 3개가 로그인 없이 접근 가능함
- [ ] 제출 설명, 영상, 실제 UI의 버튼명이 일치함
- [ ] 신청하지 않는 기능과 권한을 설명에서 제거함
- [ ] 화면 녹화에서 비밀번호와 토큰이 노출되지 않음

## 9. 피해야 할 표현

- “인스타 영상을 수집·다운로드해 재업로드합니다.”
- “모든 Instagram 계정을 자동 순회합니다.”
- “바이럴 영상을 대량으로 스크래핑합니다.”
- “검색된 콘텐츠는 자유롭게 사용할 수 있습니다.”

실제 목적을 숨기라는 뜻이 아니다. Scout가 실제로 수행하는 공개 메타데이터 기반 후보 조사, 원본 연결, 원작자 추적 및 권리 확인 기능을 정확히 설명해야 한다.
