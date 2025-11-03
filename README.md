# Upbit Order Block Trader

웹 기반 현물 자동매매 시스템의 프로토타입입니다. FastAPI 백엔드와 React 프런트엔드로 구성되며, 업비트(Upbit) 현물 WebSocket/REST API 데이터를 활용해 오더블록 기반의 매매 전략을 수행합니다.

## 구성 요소

### 백엔드 (`backend/`)
- **FastAPI** 애플리케이션 (`app/main.py`)
- 오더블록 감지(`services/order_block.py`), 오토 트렌드 채널(`services/channel.py`), 전략 실행 엔진(`services/trading_engine.py`)
- 업비트 데이터 수집 WebSocket/REST 클라이언트(`services/datafeed.py`)
- 전략 상태/설정 모델(`models/trading.py`)

### 프런트엔드 (`frontend/`)
- **React + Vite** 기반 SPA
- `useStrategyState` 훅으로 백엔드 WebSocket/REST 상태 동기화
- Material UI 기반 대시보드(`components/TradeDashboard.tsx`)

## 실행 방법

### 백엔드
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 프런트엔드
```bash
cd frontend
npm install
npm run dev
```

## 주요 전략 규칙
- 1시간봉 데이터 기반 오더블록(Bullish/Bearish) 감지
- 지지 오더블록 확정 시 분할 매수, 저항 오더블록 시 전량 청산 및 쿨다운
- 오더블록 무효화 조건, 반대 신호 처리, 부분/최종 익절 로직 구현
- 손실 허용 금액/비율 설정 및 가중치 적용, 최대 1.5배까지 투자금 증액
- 실시간 로그/포지션/자산 정보 업데이트

## 실거래 설정
업비트 실거래를 사용하려면 FastAPI 서버 실행 디렉터리에 `.env` 파일을 생성하고 아래 값을 입력합니다.

```
UPBIT_ACCESS_KEY=업비트_액세스_키
UPBIT_SECRET_KEY=업비트_시크릿_키
```

서버 기동 후 프런트엔드 대시보드에서 **Start** 버튼으로 엔진을 실행/정지할 수 있고, `Paper ↔ Live` 스위치로 모의거래/실거래 모드를 전환합니다. Live 모드에서 실행하면 전략 진입/청산 시 업비트 주문 엔드포인트(`/v1/orders`)를 통해 실거래 주문이 발송됩니다. API 키가 없으면 자동으로 모의거래로 동작하며, `/api/v1/orders` REST 엔드포인트로 수동 주문도 제출할 수 있습니다.
