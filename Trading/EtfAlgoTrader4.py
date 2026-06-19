import sys, time, os
import mojito
import requests
import json
from datetime import datetime
import pandas as pd
import pickle
from dotenv import load_dotenv

load_dotenv()

slackToken = os.environ['SLACK_TOKEN']
key        = os.environ['KIS_API_KEY']
secret     = os.environ['KIS_API_SECRET']
acc_no     = os.environ['KIS_ACC_NO']
key_isa    = os.environ['KIS_API_KEY_ISA']
secret_isa = os.environ['KIS_API_SECRET_ISA']
acc_no_isa = os.environ['KIS_ACC_NO_ISA']
K = 0.5
base_url = "https://openapi.koreainvestment.com:9443"
access_token = None

broker_isa = mojito.KoreaInvestment(
    api_key=key_isa,
    api_secret=secret_isa,
    acc_no=acc_no_isa
)

def issue_access_token():
    """OAuth인증/접근토큰발급
    """
    global access_token
    path = "oauth2/tokenP"
    url = f"{base_url}/{path}"
    headers = {"content-type": "application/json"}
    data = {
        "grant_type": "client_credentials",
        "appkey": key_isa,
        "appsecret": secret_isa
    }

    resp = requests.post(url, headers=headers, data=json.dumps(data))
    resp_data = resp.json()
    access_token = f'Bearer {resp_data["access_token"]}'

    # add extra information for the token verification
    now = datetime.now()
    resp_data['timestamp'] = int(now.timestamp()) + resp_data["expires_in"]
    resp_data['api_key'] = key_isa
    resp_data['api_secret'] = secret_isa

    # dump access token
    with open("token.dat", "wb") as f:
        pickle.dump(resp_data, f)

def check_access_token():
    """check access token

    Returns:
        Bool: True: token is valid, False: token is not valid
    """
    try:
        f = open("token.dat", "rb")
        data = pickle.load(f)
        f.close()

        expire_epoch = data['timestamp']
        now_epoch = int(datetime.now().timestamp())

        expire_date = datetime.strptime(data['access_token_token_expired'][:10], "%Y-%m-%d")
        now_date = datetime.strptime(datetime.now().strftime("%Y-%m-%d"), "%Y-%m-%d")
        date_diff = expire_date - now_date
        status = False
        #print(now_date, expire_date, date_diff.days)

        if ((now_epoch - expire_epoch > 0) or
            (date_diff.days == 0) or
            (data['api_key'] != key_isa) or
            (data['api_secret'] != secret_isa)):
            status = False
        else:
            status = True
        return status
    except IOError:
        return False

#print(check_access_token())

def load_access_token():
    """load access token
    """
    global access_token
    with open("token.dat", "rb") as f:
        data = pickle.load(f)
        access_token = f'Bearer {data["access_token"]}'

def init_token():
    global access_token
    if check_access_token():
        load_access_token()
        print("load_token")
    else:
        issue_access_token()
        print("issue_token")


#print(access_token)

### Communications ###
def post_message(token, channel, text):
    response = requests.post("https://slack.com/api/chat.postMessage",
                             headers={"Authorization": "Bearer " + token},
                             data={"channel": channel, "text": text}
                             )
    print(response)

def post_message_block(token, channel, blocks):

    response = requests.post("https://slack.com/api/chat.postMessage",
                             headers={"Authorization": "Bearer " + token},
                             data={"channel": channel, "blocks": blocks}
                             )
    print(response)

def dbgout(message):
    print(datetime.now().strftime('[%m/%d %H:%M:%S]'), message)
    strbuf = datetime.now().strftime('[%m/%d %H:%M:%S]') + message
    post_message(slackToken,"stock",strbuf)

def printlog(message, *args):
    print(datetime.now().strftime('[%m/%d %H:%M:%S]'), message, *args)
#dbgout("algo test")
#printlog("algo test", slackToken)

### Communications ###


def get_current_price_direct(code):
    """ 현재가 구하기, 안써도 됨 """
    url = 'https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price'
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": code
    }
    headers = {
        "Content-Type": "application/json",
        "authorization": access_token,
        "appKey": key_isa,
        "appSecret": secret_isa,
        "tr_id": "FHKST01010100"
    }

    res = requests.get(url, params=params, headers=headers)
    rescode = res.status_code
    if rescode == 200:
        # print(res.headers)
        # print(str(rescode) + " | " + res.text)
        res_dict = json.loads(res.text)
        return res_dict['output']['stck_prpr']
    else:
        print("Error Code : " + str(rescode) + " | " + res.text)
        return res.text

#print(get_current_price_direct('005930'))

def get_asking_price_direct(code):
    """ 현재가, 매도호가, 매수호가 리턴 """
    url = 'https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn'
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": code
    }
    headers = {
        "Content-Type": "application/json",
        "authorization": access_token,
        "appKey": key_isa,
        "appSecret": secret_isa,
        "tr_id": "FHKST01010200"
    }

    res = requests.get(url, params=params, headers=headers)
    rescode = res.status_code

    if rescode == 200:
        # print(res.headers)
        #print(str(rescode) + " | " + res.text)
        res_dict = json.loads(res.text)
        return int(res_dict['output2']['stck_prpr']),int(res_dict['output1']['askp1']), int(res_dict['output1']['bidp1'])
    else:
        print("Error Code : " + str(rescode) + " | " + res.text)
        return res.text

#print(get_asking_price_direct('252670'))

def get_current_price(code):
    """ 브로커 통해 받는 현재가, 현재 안씀 """
    resp = broker_isa.fetch_price(code)
    print(resp)
    item = {}
    item['cur_price'] = resp['output']['stck_prpr']

    return item['cur_price']

#print(get_current_price('252670'))

def get_ohlc(code, qty=100):
    resp = broker_isa.fetch_ohlcv(symbol=code,timeframe='D',adj_price=True)
    df = pd.DataFrame(resp['output2'])
    dt = pd.to_datetime(df['stck_bsop_date'], format="%Y%m%d")
    df.set_index(dt, inplace=True)
    df = df[['stck_oprc', 'stck_hgpr', 'stck_lwpr', 'stck_clpr']]
    df.columns = ['open', 'high', 'low', 'close']
    df.index.name = "date"
    return df
#print(get_ohlc('252670'))

def get_stock_balance(code):
    try:
        resp = broker_isa.fetch_balance()

        if code == 'ALL':
            print('계좌명: ISA')
            print('D+2 예수금: '+ str(resp['output2'][0]['prvs_rcdl_excc_amt']))
            print('금일 매수 금액: ' + str(resp['output2'][0]['thdt_buy_amt']))
            print('종목수: ' + str(len(resp['output1'])))
            print('----------------------------')
        stocks = []
        for comp in resp['output1']:
            stock_code = comp['pdno']
            stock_name = comp['prdt_name']
            stock_qty = format(int(comp['hldg_qty']), ',')
            pchs_amount = format(int(comp['pchs_amt']), ',')
            evlu_amount = format(int(comp['evlu_amt']), ',')
            if code == 'ALL':
                print(stock_code+' ('+stock_name+') : ' + stock_qty + '주')
                stocks.append({'code': stock_code,'name': stock_name, 'qty': stock_qty})
            if code == stock_code:
                return stock_name, stock_qty
        if code == 'ALL':
            return stocks
        else:
            return stock_name, 0
    except Exception as ex:
        #dbgout("sell_all() -> exception! " + str(ex))
        printlog("get_stock_balance() -> exception! " + str(ex))
#print(get_stock_balance('252670'))
#print(get_stock_balance('ALL'))

def get_stock_balance_evlu(code):
    try:
        resp = broker_isa.fetch_balance()

        if code == 'ALL':
            print('계좌명: ISA')
            tot_evlu_amt = format(int(resp['output2'][0]['tot_evlu_amt']),',')  #총평가금액 = 유가증권 평가금액 합계금액 + D+2 예수금
            evlu_amt_smtl_amt = format(int(resp['output2'][0]['evlu_amt_smtl_amt']),',') #유가증권 평가금액 합계금액
            prvs_rcdl_excc_amt = format(int(resp['output2'][0]['prvs_rcdl_excc_amt']),',') #D+2 예수금
            return tot_evlu_amt, evlu_amt_smtl_amt, prvs_rcdl_excc_amt
        stocks = []
        for comp in resp['output1']:
            stock_code = comp['pdno']
            stock_name = comp['prdt_name']
            stock_qty = format(int(comp['hldg_qty']), ',')
            evlu_pfls_rt = float(comp['evlu_pfls_rt']) #평가손익률
            evlu_pfls_amt = float(comp['evlu_pfls_amt']) #평가손익금액 (평가금액-매입금액)
            if code == stock_code:
                return stock_name, stock_qty, evlu_pfls_rt, evlu_pfls_amt
        else:
            return code, 0
    except Exception as ex:
        #dbgout("sell_all() /-> exception! " + str(ex))
        printlog("get_stock_balance_evlu() -> exception! " + str(ex))

#print(get_stock_balance_evlu('069500'))
#print(get_stock_balance_evlu('ALL'))

def get_current_cash():
    try:
        resp = broker_isa.fetch_balance()
        deposit = int(resp['output2'][0]['prvs_rcdl_excc_amt'])  #D+2 예수금으로 변경
        return deposit
    except Exception as ex:
        #dbgout("sell_all() -> exception! " + str(ex))
        printlog("get_stock_balance() -> exception! " + str(ex))
#print(get_current_cash())
# cash = format(get_current_cash(),',')
# out = str('계좌에 예수금이 '+str(cash) + ' 원 있습니다.')
# printlog(out)
#dbgout(out)

def get_target_price(code):
    try:
        time_now = datetime.now()
        str_today = time_now.strftime('%Y-%m-%d')
        ohlc = get_ohlc(code)
        if str_today == str(ohlc.iloc[0].name)[0:10]:  #수정완료
            today_open = ohlc.iloc[0].open
            lastday = ohlc.iloc[1]
        else:
            lastday = ohlc.iloc[0]
            today_open = lastday[3]
        lastday_high =lastday[1]
        lastday_low = lastday[2]
        #print(today_open, lastday_high, lastday_low)
        target_price = float(today_open) + (float(lastday_high) - float(lastday_low)) * K
        return target_price
    except Exception as ex:
        printlog("'get_target_price() -> exception! " + str(ex) + "'")
        #dbgout("'get_target_price() -> exception! " + str(ex) + "'")
        return None

#print(get_target_price('252670'))

def get_movingaverage(code, window):
    try:
        time_now = datetime.now()
        str_today = time_now.strftime('%Y-%m-%d')
        #print('today: ', str_today)
        ohlc = get_ohlc(code)
        #print('today_data: ',str(ohlc.iloc[0].name)[0:10])
        if str_today == str(ohlc.iloc[0].name)[0:10]:  # 요기확인필요
            lastday = ohlc.iloc[1].name
            #print('lastday: ',lastday)
        else:
            lastday = ohlc.iloc[0].name
        closes = ohlc['close'].sort_index() #종가 칼럼을 인덱스 날짜기준 오름차순 정렬
        ma = closes.rolling(window=window).mean() #윈도우별 이동평균
        return ma.loc[lastday]
    except Exception as ex:
        printlog("'get_movingaverage() -> exception! " + str(ex) + "'")
        #dbgout("'get_movingaverage() -> exception! " + str(ex) + "'")
        return None
#print(get_movingaverage('252670', 5))
#print(get_movingaverage('252670', 10))
#print(get_movingaverage('060150', 60))

def order_stock(code, quantity, order_type, price):
    resp = broker_isa.create_order(side='buy', symbol=code, quantity=quantity, order_type=order_type, price=price)
    print('_order_stock', resp)

#order_stock('252670', 1, '00', 14260)  # 00: 지정가
#order_stock('252670',1,'16',0)  #16: FOK최유리
#order_stock('252670', 1, '00', 2560)  # 00: 지정가

def cancel_order_stock(orno, qrty, total):
    resp = broker_isa.cancel_order(org_no='91259', order_no=orno, quantity=qrty, total=total)
    print('_cancel_order_stock', resp)
#cancel_order_stock('0000107506', 1, True)

def sell_stock(code, quantity, order_type, price):
    resp = broker_isa.create_order(side='sell', symbol=code, quantity=quantity, order_type=order_type, price=price)
    print('_sell_stock', resp)

#sell_stock('A229200',2,'16',0)

def check_balance_pfls():
    resp = broker_isa.fetch_balance_domestic()
    print('_check_balance', resp)

#check_balance_pfls()

def sell_all():
    try:
        symbol_list = ['252670', '251340', '233740', '114800', '122630', '229200', '069500', '250780', '148020', '305540']
        while True:
            stocks = get_stock_balance('ALL')
            print('stock',stocks)
            stocks_today = []
            for s in stocks:
                if s['code'] in symbol_list:
                    stocks_today.append(s)
            total_qty = 0
            print('stocks_today', stocks_today)
            for s in stocks_today:
                total_qty += int(s['qty'])
            if total_qty == 0:
                dbgout("더 이상 매도할 수량이 없습니다.")
                return True

            for s in stocks_today:
                if s['qty'] != 0:
                    sell_stock(s['code'],s['qty'],"15",0)
                    dbgout('*3* 최유리 IOC 매도 완료' + s['code']+ s['name']+ s['qty'])
                time.sleep(1)
            time.sleep(30)
    except Exception as ex:
        dbgout("sell_all() -> exception! " + str(ex))
        #printlog("sell_all() -> exception! " + str(ex))
#sell_all()


def buy_etf(code):
    try:
        global bought_list
        if code in bought_list:
            print('code: ', code, 'in', bought_list)
            stock_name, stock_qty, evlu_pfls_rt, evlu_pfls_amt = get_stock_balance_evlu(code)
            if evlu_pfls_rt > 2 & int(stock_qty) > 0:  #수익률이 2%가 넘고 수량이 1개 이상일 때만
                #dbout 해당 주식은 오늘 2%수익 넘어서 팔께~
                dbgout(stock_name+'의 주식 당일 수익률이 목표 2% 넘어서 전량 익절 시도 하겠습니다.')
                sell_stock(code,stock_qty,"15",0)
                #bought_list에서 삭제하면 안됨
            # if evlu_pfls_rt < -1 & int(stock_qty) > 0: #수익률이 -1%로 떨어지면 손절
            #     dbgout(stock_name + '의 주식 당일 수익률이 -1%이 되어 전량 손절 시도 하겠습니다.')
            #     sell_stock(code, stock_qty,"15",0)

            return False

        current_price, ask_price, bid_price = get_asking_price_direct(code)
        target_price = get_target_price(code)
        ma5_price = get_movingaverage(code,5)
        ma10_price = get_movingaverage(code,10)

        buy_qty = 0
        if ask_price > 0:
            buy_qty = buy_amount // ask_price

        #stock_name, stock_qty = get_stock_balance(code)
        print(code,' 현재가:', current_price, ' 목표가: ', target_price, ' ma5: ', ma5_price, ' ma10: ', ma10_price)

        if current_price > target_price and current_price > ma5_price and current_price > ma10_price:
            dbgout(str(code) +' '+ str(buy_qty) + '주 : ' + str(current_price) + ' 매수 조건 충족!`')
            dbgout('current price: ' + str(current_price) + ' ma5_price: ' + str(ma5_price) + ' ma10_price: '+ str(ma10_price))
            order_stock(code, int(buy_qty), '16', 0)

            stock_name, bought_qty = get_stock_balance(code)
            printlog('get_stock_balance :', stock_name, bought_qty)
            if int(bought_qty) > 0:
                bought_list.append(code)
                dbgout("`*2* buy_etf(" + str(stock_name) + ' : ' + str(code) +") = " + str(bought_qty) + "주 매수 완료!" + "`")

    except Exception as ex:
        #dbgout("`buy_etf("+ str(code) + ") -> exception! " + str(ex) + "`")
        printlog("`buy_etf("+ str(code) + ") -> exception! " + str(ex) + "`")


if __name__ == '__main__':
    try:
        symbol_list = ['252670', '251340', '233740', '114800', '122630', '229200', '069500', '250780', '148020', '305540']
        bought_list = []  # 매수 완료된 종목 리스트
        target_buy_count = 5  # 매수할 종목 수
        buy_percent = 0.19
        total_cash = int(get_current_cash())  # 100% 증거금 주문 가능 금액 조회
        buy_amount = total_cash * buy_percent  # 종목별 주문 금액 계산
        dbgout('100% 증거금 주문 가능 금액 :' + str(total_cash))
        dbgout('종목별 주문 비율 :' + str(buy_percent))
        dbgout('종목별 주문 금액 :' + str(buy_amount))
        dbgout('*1* System Trading 시작 :' + datetime.now().strftime('%m/%d %H:%M:%S'))
        soldout = False;

        init_token()

        while True:
            t_now = datetime.now()
            t_9 = t_now.replace(hour=9, minute=0, second=0, microsecond=0)
            t_start = t_now.replace(hour=9, minute=5, second=0, microsecond=0)
            t_sell = t_now.replace(hour=14, minute=15, second=0, microsecond=0)
            t_exit = t_now.replace(hour=14, minute=20, second=0, microsecond=0)
            today = datetime.today().weekday()
            if today == 5 or today == 6:  # 토요일이나 일요일이면 자동 종료
                printlog('Today is', 'Saturday.' if today == 5 else 'Sunday.')
                sys.exit(0)
            if t_9 < t_now < t_start and soldout == False:
                soldout = True
                stocks = get_stock_balance('ALL')
                #rint('stock', stocks)
                #stocks_today = []
                for s in stocks:
                    if s['code'] in symbol_list:
                        bought_list.append(s)
                #sell_all()
            if t_start < t_now < t_sell:  # AM 09:05 ~ PM 02:15 : 매수
                for sym in symbol_list:
                    if len(bought_list) < target_buy_count:
                        buy_etf(sym)
                        time.sleep(5)
                # if t_now.minute == 30 and 0 <= t_now.second <= 5:
                #     get_stock_balance('ALL')   #매 시간 30분에 DB out으로 슬랙으로 알려줌
                #     time.sleep(5)
            if t_sell < t_now < t_exit:  # PM 02:15 ~ PM 02:20 : 일괄 매도
                if sell_all() == True:
                    dbgout('*4* 전량 매도 했습니다. 프로그램 종료합니다.')
                    sys.exit(0)
            if t_exit < t_now:  # PM 02:20 ~ :프로그램 종료
                dbgout('장 마감으로 프로그램 종료합니다.')
                sys.exit(0)
            time.sleep(10)

    except Exception as ex:
        dbgout('`main -> exception! ' + str(ex) + '`')
        #printlog('`main -> exception! ' + str(ex) + '`')


