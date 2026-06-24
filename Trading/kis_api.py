"""
한국투자증권 OpenAPI 래퍼.
인증, 시세 조회, 잔고 조회, 주문 실행만 담당한다.
"""
import os, json, pickle, time
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import mojito

load_dotenv()

BASE_URL   = "https://openapi.koreainvestment.com:9443"
KEY_ISA    = os.environ['KIS_API_KEY_ISA']
SECRET_ISA = os.environ['KIS_API_SECRET_ISA']
ACC_ISA    = os.environ['KIS_ACC_NO_ISA']

broker = mojito.KoreaInvestment(
    api_key=KEY_ISA,
    api_secret=SECRET_ISA,
    acc_no=ACC_ISA,
)

_access_token: str | None = None

# ──────────────────────────────────────────────
# 인증
# ──────────────────────────────────────────────

def _issue_token() -> None:
    global _access_token
    resp = requests.post(
        f"{BASE_URL}/oauth2/tokenP",
        headers={"content-type": "application/json"},
        data=json.dumps({
            "grant_type": "client_credentials",
            "appkey": KEY_ISA,
            "appsecret": SECRET_ISA,
        }),
        timeout=10,
    )
    data = resp.json()
    _access_token = f'Bearer {data["access_token"]}'

    data['timestamp'] = int(datetime.now().timestamp()) + data["expires_in"]
    data['api_key']    = KEY_ISA
    data['api_secret'] = SECRET_ISA
    with open("token.dat", "wb") as f:
        pickle.dump(data, f)


def _load_token() -> None:
    global _access_token
    with open("token.dat", "rb") as f:
        data = pickle.load(f)
    _access_token = f'Bearer {data["access_token"]}'


def _is_token_valid() -> bool:
    try:
        with open("token.dat", "rb") as f:
            data = pickle.load(f)
        expire_date = datetime.strptime(data['access_token_token_expired'][:10], "%Y-%m-%d")
        now_date    = datetime.strptime(datetime.now().strftime("%Y-%m-%d"), "%Y-%m-%d")
        if (int(datetime.now().timestamp()) >= data['timestamp'] or
                (expire_date - now_date).days == 0 or
                data['api_key'] != KEY_ISA or
                data['api_secret'] != SECRET_ISA):
            return False
        return True
    except (IOError, KeyError):
        return False


def init_token() -> None:
    if _is_token_valid():
        _load_token()
        print("token: loaded from cache")
    else:
        _issue_token()
        print("token: issued new token")


# ──────────────────────────────────────────────
# 시세
# ──────────────────────────────────────────────

def get_asking_price(code: str) -> tuple[int, int, int]:
    """(현재가, 매도호가1, 매수호가1) 반환"""
    resp = requests.get(
        f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn",
        params={"fid_cond_mrkt_div_code": "J", "fid_input_iscd": code},
        headers={
            "Content-Type": "application/json",
            "authorization": _access_token,
            "appKey": KEY_ISA,
            "appSecret": SECRET_ISA,
            "tr_id": "FHKST01010200",
        },
        timeout=10,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"get_asking_price {code}: HTTP {resp.status_code}")
    d = resp.json()
    return (
        int(d['output2']['stck_prpr']),
        int(d['output1']['askp1']),
        int(d['output1']['bidp1']),
    )


def get_current_price(code: str) -> dict:
    """현재가 + 등락률 조회. {price, changePercent} 반환"""
    resp = requests.get(
        f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price",
        params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
        headers={
            "Content-Type": "application/json",
            "authorization": _access_token,
            "appKey": KEY_ISA,
            "appSecret": SECRET_ISA,
            "tr_id": "FHKST01010100",
        },
        timeout=10,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"get_current_price {code}: HTTP {resp.status_code}")
    d = resp.json().get('output', {})
    return {
        "price":         int(d.get('stck_prpr', 0)),
        "changePercent": float(d.get('prdy_ctrt', 0)),
    }


def get_ohlcv(code: str) -> pd.DataFrame:
    """일봉 OHLCV DataFrame (index=date, columns=open/high/low/close)"""
    resp = broker.fetch_ohlcv(symbol=code, timeframe='D', adj_price=True)
    df = pd.DataFrame(resp['output2'])
    dt = pd.to_datetime(df['stck_bsop_date'], format="%Y%m%d")
    df.set_index(dt, inplace=True)
    df = df[['stck_oprc', 'stck_hgpr', 'stck_lwpr', 'stck_clpr']]
    df.columns = ['open', 'high', 'low', 'close']
    df.index.name = "date"
    return df


# ──────────────────────────────────────────────
# 잔고
# ──────────────────────────────────────────────

def get_cash() -> int:
    """D+2 예수금"""
    resp = broker.fetch_balance()
    return int(resp['output2'][0]['prvs_rcdl_excc_amt'])


def get_holdings() -> dict[str, dict]:
    """보유 종목 딕셔너리: {code: {name, qty, avg_price, evlu_pfls_rt}}"""
    resp = broker.fetch_balance()
    result = {}
    for item in resp['output1']:
        result[item['pdno']] = {
            'name':        item['prdt_name'],
            'qty':         int(item['hldg_qty']),
            'avg_price':   float(item['pchs_avg_pric']),
            'evlu_pfls_rt': float(item['evlu_pfls_rt']),
        }
    return result


# ──────────────────────────────────────────────
# 주문
# ──────────────────────────────────────────────

def buy(code: str, qty: int, order_type: str = '16', price: int = 0) -> dict:
    """매수 주문. order_type 16=FOK최유리, 00=지정가"""
    return broker.create_order(side='buy', symbol=code, quantity=qty,
                               order_type=order_type, price=price)


def sell(code: str, qty: int, order_type: str = '15', price: int = 0) -> dict:
    """매도 주문. order_type 15=IOC최유리, 00=지정가"""
    return broker.create_order(side='sell', symbol=code, quantity=qty,
                               order_type=order_type, price=price)
