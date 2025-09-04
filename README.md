# regi — MOIS `region_cd` lookup

행안부 **법정동 표준코드 API**에서 `region_cd`만 추출해 주는 도구입니다.

- `region.py` : 로컬 CLI (표준 라이브러리만, HTTPS→HTTP 폴백, 전국 스캔 옵션)
- `api/region.py` : Vercel Serverless Function — `GET /api/region?q=...`
- `api/healthz.py` : `GET /api/healthz`
- `api/version.py` : `GET /api/version`
- `index.html` : 루트 안내 페이지
- `vercel.json` : Python 런타임/리라이트 설정
