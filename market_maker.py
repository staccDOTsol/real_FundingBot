# This code is for sample purposes only, comes as is and with no warranty or guarantee of performance
from bitmex_websocket import BitMEXWebsocket
import linecache
import sys
import threading
from datetime import timedelta
import time
from queue import Queue
from threading import Timer
from BybitWebsocket import BybitWebsocket


import asyncio
import logging
import os
from uuid import uuid4

import threading

# PYTHONPATH=.:$PYTHONPATH DERIBIT_CLIENT_ID=YOU_ACCESS_KEY DERIBIT_CLIENT_SECRET=YOU_ACCESS_SECRET python3 market_maker.py


from ssc2ce.deribit import Deribit, AuthType


# changes various behavior for testing. Set to False in production!
testing = False

import inspect  
def PrintException(e):
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    lineno = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno, f.f_globals)
    extraPrint(False, 'EXCEPTION IN ({}, LINE {} "{}"): {}'.format(filename, lineno, line.strip(), exc_obj))
    sleep(10)
def extraPrint(toconsole, string):
    

    #if toconsole == True:
        #print(string)
    log = 'log.txt'
    with open(log, "a") as myfile:
        myfile.write(datetime.utcnow().strftime( '%Y-%m-%d %H:%M:%S' ) + ', line: ' + str(inspect.currentframe().f_back.f_lineno)  + ': ' + str(string) + '\n')


from collections    import OrderedDict
from datetime       import datetime
start_time         = datetime.utcnow()

from os.path        import getmtime
from time           import sleep
from utils          import ( get_logger, lag, #print_dict, #print_dict_of_dicts, sort_by_key,
                             ticksize_ceil, ticksize_floor, ticksize_round )
import requests
import bitmex
import bybit
import json
import os
import shutil

import copy as cp
import argparse, logging, math, os, pathlib, sys, time, traceback
import ccxt
import random

try:
    from deribit_api    import RestClient
except ImportError:
    extraPrint(False, "Please install the deribit_api pacakge", file=sys.stderr)
    extraPrint(False, "    pip3 install deribit_api", file=sys.stderr)
    exit(1)

# Add command line switches
parser  = argparse.ArgumentParser( description = 'Bot' )

# Use production platform/account
parser.add_argument( '-p',
                     dest   = 'use_prod',
                     action = 'store_true' )

# Do not display regular status updates to terminal
parser.add_argument( '--no-output',
                     dest   = 'output',
                     action = 'store_false' )

# Monitor account only, do not send trades
parser.add_argument( '-m',
                     dest   = 'monitor',
                     action = 'store_true' )

# Do not restart bot on errors
parser.add_argument( '--no-restart',
                     dest   = 'restart',
                     action = 'store_false' )

args    = parser.parse_args()

KEY     = "7x5cttEC"#"VC4d7Pj1"
SECRET  = "h_xxD-huOZOyNWouHh_yQnRyMkKyQyUv-EX96ReUHmM"#"IB4VEP26OzTNUt4JhNILOW9aDuzctbGs_K6izxQG2dI"





URL     = 'https://www.deribit.com'

EWMA_WGT_LOOPTIME   = 2.5    
BP                  = 1e-4      # one basis point
BTC_SYMBOL          = 'btc'
CONTRACT_SIZE       = 10        # USD
COV_RETURN_CAP      = 100       # cap on variance for vol estimate
DECAY_PCT_LIM       = 0.1       # position lim decay factor toward expiry
LOG_LEVEL           = logging.INFO
MIN_ORDER_SIZE      = 24
MAX_LAYERS          =  1        # max orders to layer the ob with on each side
MKT_IMPACT          =  0.5      # base 1-sided spread between bid/offer
PCT                 = 100 * BP  # one percentage point
PCT_QTY_BASE        = 100       # pct order qty in bps as pct of acct on each order
MIN_LOOP_TIME       =   0.2       # Minimum time between loops
SECONDS_IN_DAY      = 3600 * 24
SECONDS_IN_YEAR     = 365 * SECONDS_IN_DAY
WAVELEN_MTIME_CHK   = 15        # time in seconds between check for file change
WAVELEN_OUT         = 15        # time in seconds between output to terminal
WAVELEN_TS          = 15        # time in seconds between time series update

MKT_IMPACT          *= BP

PCT_QTY_BASE        *= BP

conn = Deribit()




class MarketMaker( object ):
    
    def __init__( self, monitor = True, output = True ):
        self.app = Deribit(client_id=KEY, client_secret=SECRET, testnet=False, auth_type=AuthType.CREDENTIALS,
              get_id=lambda: str(uuid4()))
        self.app.on_connect_ws = self.start_credential
        self.app.on_handle_response = self.on_handle_response
        self.app.on_authenticated = self.after_login
        self.app.on_token = self.on_token
        self.app.method_routes += [
            ("subscription", self.handle_subscription),
        ]
        self.app.response_routes += [
            ("public/subscribe", self.printer),
            ("private/get_position", self.printer),
            ("private/get_open_orders_by_instrument", self.printer),
            ("private/subscribe", self.printer),
            ("private/get_account_summary", self.printer),
        ]
        self.direct_requests = {}
        self.deri_bal = {}
        self.deri_orders = []
        self.deri_quote = {}
        self.deri_quote['ETH'] = []
        self.deri_quote['BTC'] = []
        self.deri_index = {}

        self.MAX_SKEW = MIN_ORDER_SIZE * 2.5
        self.MAX_SKEW_OLD = MIN_ORDER_SIZE * 2.5

        self.bit  = bybit.bybit(test=False, api_key="wbNMbu0aTQ7SxqZe58", api_secret="wel8qs4aXR0ytJ3s4zS3AKgCcPUblCVKQFVB")
        self.bitws = BybitWebsocket(wsURL="wss://stream.bybit.com/realtime",
                                 api_key="wbNMbu0aTQ7SxqZe58", api_secret="wel8qs4aXR0ytJ3s4zS3AKgCcPUblCVKQFVB")

        self.bitws.subscribe_order()

        self.bitws.subscribe_execution()
        self.bitws.subscribe_position()
        extraPrint(False, dir(bitmex))
        self.mex = bitmex.bitmex(test=False, api_key="hYWO6-TaiH-FC5kDGUTGP-hO", api_secret="Cz92m7jRam3JTWHQZwiIKWUcSl5jvexquXldAM79kWmRzqvW")

        self.bals = {}
        self.ethrate = None
        self.exchangeRates = {}

        self.exchangeRates['ETH'] = {}
        self.exchangeRates['BTC'] = {}

        self.percs = {}
        self.maxqty = 25
        self.PCT_LIM_LONG = {}
        self.PCT_LIM_SHORT = {}
        self.LEV_LIM_LONG = {}
        self.LEV_LIM_SHORT = {}
        self.LEVERAGE_LIMIT_SHORT = 5
        self.LEVERAGE_LIMIIT_LONG = 5
        self.INITIAL_MARGIN_LIMIT_LONG        = 10       # % position limit long

        self.INITIAL_MARGIN_LIMIT_SHORT       = 10
        for token in self.exchangeRates:
            self.PCT_LIM_LONG[token]        = self.INITIAL_MARGIN_LIMIT_LONG 
            self.PCT_LIM_SHORT[token]       = self.INITIAL_MARGIN_LIMIT_SHORT    
            self.LEV_LIM_LONG[token] = self.LEVERAGE_LIMIIT_LONG
            self.LEV_LIM_SHORT[token] = self.LEVERAGE_LIMIT_SHORT
        self.equity_usd         = None
        self.equity_btc         = None
        self.equity_usd_init    = None
        self.equity_btc_init    = 0
        self.con_size           = float( CONTRACT_SIZE )
        self.client             = None
        self.LEV = 1
        self.IM = 1
        self.futtoks = {}
        self.ccxt = None
        self.t = 0
        self.oldte = 0
        self.bitOrders = []
        self.create_client()
        self.ws = {}
        self.tradeids = []
        self.amounts = 0
        self.fees = 0
        self.startTime = int(time.time()*1000)
        self.arbmult = {}
        self.arbmult['BTC'] = {}
        self.arbmult['ETH'] = {}
        self.totrade = ['bybit', 'deribit','bitmex']
        self.deltas             = OrderedDict()
        self.futures            = {}
        self.futures_prv        = OrderedDict()
        self.logger             = None
        self.mean_looptime      = 1
        self.monitor            = monitor
        self.output             = output or monitor
        self.positions          = {}
        self.spread_data        = None
        self.this_mtime         = None
        self.ts                 = None
        self.vols               = OrderedDict()
    

    
    def loop_in_thread(self, loop):
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.app.run_receiver())


    async def start_credential(self):
        await self.app.auth_login()
        # await self.app.set_heartbeat(15)


    async def do_something_after_login(self):
        await self.app.send_private(request={
            "method": "private/get_account_summary",
            "params": {
                "currency": "BTC",
                "extended": True
            }
        })
        await self.app.send_private(request={
            "method": "private/get_account_summary",
            "params": {
                "currency": "ETH",
                "extended": True
            }
        })
        await self.app.send_private(request={
            "method": "private/get_position",
            "params": {
                "instrument_name": "BTC-PERPETUAL"
            }
        })
        await self.app.send_private(request={
            "method": "private/get_position",
            "params": {
                "instrument_name": "ETH-PERPETUAL"
            }
        })


        await self.app.send_private(request={
            "method": "private/get_open_orders_by_instrument",
            "params": {
                "instrument_name": "BTC-PERPETUAL"
            }
        })
        await self.app.send_private(request={
            "method": "private/get_open_orders_by_instrument",
            "params": {
                "instrument_name": "ETH-PERPETUAL"
            }
        })

        

        await self.app.send_private(request={
  "method": "public/subscribe",
  "params": {
    "channels": [
      "quote.BTC-PERPETUAL", "quote.ETH-PERPETUAL"
    ]
  }})

        await self.app.send_private(request={
            "method": "private/subscribe",
            "params": {
                "channels": ["deribit_price_index.btc_usd", "deribit_price_index.eth_usd"]}
        })


    async def printer(self, **kwargs):
        data = kwargs

        request = kwargs['request']
        doprint = True
        if request["method"] == 'book.BTC-PERPETUAL.raw':
            return
        if "public/subscribe" in request["method"]:
            #print(data)
            if 'params' in data:
                if 'ETH' in request["method"]:
                    self.deri_quote['ETH'] = [data['params']['data']['best_bid_price'], data['params']['data']['best_ask_price']]
                else:
                    self.deri_quote['BTC'] = [data['params']['data']['best_bid_price'], data['params']['data']['best_ask_price']]
                
                if len(self.deri_quote['BTC'] > 0):
                    extraPrint(False, self.deri_quote)
                    doprint = False
                
        if "price_index" in request["method"]:
            if 'eth' in request["method"]:
                self.deri_index['ETH'] = request["params"]["data"]['price']
            else:
                self.deri_index['BTC'] = request["params"]["data"]['price']
            doprint = False
        if "open_orders" in request["method"]:
            self.deri_orders = data['response']['result']
            doprint = False
        if "position" in request["method"]:
            self.positions[data['response']['result']['instrument_name']] = data['response']['result']
            doprint = False
        if "account" in request["method"]:
            self.deri_bal[data["response"]['result']['currency']] = data['response']['result']['equity']
            doprint = False
            extraPrint(False, self.deri_bal)
        if doprint == True and 'subscribe' not in request['method']:
            extraPrint(False, repr(data))


    async def handle_subscription(self, data: dict):
        doprint = True
        if data["params"]["channel"] == 'book.BTC-PERPETUAL.raw':
            return
        if "quote" in data["params"]["channel"]:
            #print(data)
            if 'params' in data:
                if 'ETH' in data["params"]["channel"]:
                    self.deri_quote['ETH'] = [data['params']['data']['best_bid_price'], data['params']['data']['best_ask_price']]
                else:
                    self.deri_quote['BTC'] = [data['params']['data']['best_bid_price'], data['params']['data']['best_ask_price']]
                
                doprint = False
        
        if "price_index" in data["params"]["channel"]:
            if 'eth' in data["params"]["channel"]:
                self.deri_index['ETH'] = data["params"]["data"]['price']
            else:
                self.deri_index['BTC'] = data["params"]["data"]['price']
            doprint = False
        if "open_orders" in data["params"]["channel"]:
            self.deri_orders = data['response']['result']
            doprint = False
        if "position" in data["params"]["channel"]:
            self.positions[data['response']['result']['instrument_name']] = data['response']['result']
            doprint = False
        if "account" in data["params"]["channel"]:
            self.deri_bal[data["response"]['result']['currency']] = data['response']['result']['euuity']
            doprint = False
            extraPrint(False, self.deri_bal)
        if doprint == True:
            extraPrint(False, repr(data))


    async def after_login(self):
        asyncio.ensure_future(self.do_something_after_login())


    async def setup_refresh(self, refresh_interval):
        await asyncio.sleep(refresh_interval)
        await self.app.auth_refresh_token()


    async def on_token(self, params):
        refresh_interval = min(600, params["expires_in"])
        asyncio.ensure_future(self.setup_refresh(refresh_interval))


    async def on_handle_response(self, data):
        request_id = data["id"]


    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()


    def disable_heartbeat(self):
        asyncio.ensure_future(self.app.disable_heartbeat())


    def logout(self):
        asyncio.ensure_future(self.app.auth_logout())


    def stop(self):
        asyncio.ensure_future(self.app.stop())


        # loop.call_later(60, stop)

    def update_rates( self ):
        #try:
        #    res = requests.get('https://futures.kraken.com/derivatives/api/v3/tickers').json()
        #    for pair in res['tickers']:
        #        if pair['tag'] == 'perpetual' and 'xbt' in pair['symbol'].lower():
        #            self.exchangeRates['BTC']['kraken'] = pair['fundingRate'] * 3
        #        elif pair['tag'] == 'perpetual' and 'eth' in pair['symbol'].lower():
        #            self.exchangeRates['ETH']['kraken'] = pair['fundingRate'] * 3
        #except Exception as e:
        #    extraPrint(False, e)
        #try:
        #    res = requests.get("https://api-pub.bitfinex.com/v2/status/deriv?keys=ALL").json()

        #    self.exchangeRates['BTC']['bitfinex'] = res[0][9] * 3
        #    self.exchangeRates['ETH']['bitfinex'] = res[1][9] * 3

        #except Exception as e:
        #    extraPrint(False, e)
        try:
            res = requests.get("https://www.deribit.com/api/v2/public/get_funding_rate_value?instrument_name=BTC-PERPETUAL&start_timestamp=" + str(int(time.time() * 1000 - (60 * 60 * 8))) + "&end_timestamp=" + str(int(time.time() * 1000))).json()['result']

            self.exchangeRates['BTC']['deribit'] = res * 3
    
            res = requests.get("https://www.deribit.com/api/v2/public/get_funding_rate_value?instrument_name=ETH-PERPETUAL&start_timestamp=" + str(int(time.time() * 1000 - (60 * 60 * 8))) + "&end_timestamp=" + str(int(time.time() * 1000))).json()['result']

            self.exchangeRates['ETH']['deribit'] = res * 3

        except Exception as e:
            extraPrint(False, e)
            PrintException(e)
        try:
            res = self.mex.Funding.Funding_get(symbol='XBTUSD', reverse=True, count=1).result()
            
            extraPrint(False, 'funding')
            extraPrint(False, res[0])
            res = res[0][0]['fundingRate'] * 3

            self.exchangeRates['BTC']['bitmex'] = res

            res = self.mex.Funding.Funding_get(symbol='ETHUSD', reverse=True, count=1).result()
            res = res[0][0]['fundingRate'] * 3

            self.exchangeRates['ETH']['bitmex'] = res

        except Exception as e:
            extraPrint(False, e)
            PrintException(e)
        try:
            
            res = self.bit.Funding.Funding_getRate(symbol="BTCUSD").result()
            resold = res
            res = res[0]['result']['funding_rate'] * 3
            
            self.exchangeRates['BTC']['bybit'] = res
            res = self.bit.Funding.Funding_getRate(symbol="ETHUSD").result()
            if 0 not in res:
                res = resold
            res = res[0]['result']['funding_rate'] * 3

            self.exchangeRates['ETH']['bybit'] = res
        except Exception as e:
            extraPrint(False, e) # extraPrint(False, e)
            PrintException(e)
        extraPrint(False, self.exchangeRates)
        positive = {}
        for coins in self.exchangeRates:
            h = 0
            for funding in self.exchangeRates[coins]:
                k = funding
                val = self.exchangeRates[coins][funding] * 1000000
                
                if math.fabs(val) > h:
                    h = math.fabs(val)
                    winner = k
                    if val > 0:
                        positive[coins] = True
                    else:
                        positive[coins] = False
            if positive[coins] == True:
                self.arbmult[coins]=({"long": "others", "short": winner})
            else:
                self.arbmult[coins]=({"long": winner, "short": "others"})
            print(self.arbmult)
                
            extraPrint(False, 'shorting n longing')
        extraPrint(False, self.arbmult)
        extraPrint(False, self.exchangeRates)
    def calculate_eth_btc( self, token, ex ):
    
        diff = {}
        for coins in self.exchangeRates:
            arr = []
            for rate in self.exchangeRates[coins]:
                arr.append(self.exchangeRates[coins][rate])
            m1 = min(arr)
            m2 = max(arr)
            diff[coins] = m2 - m1
        t = 0
        for d in diff:
            t = t + diff[d]
        self.percs['BTC'] = diff['BTC'] / t
        self.percs['ETH'] = diff['ETH'] / t
        
        extraPrint(False, '% BTC vs ETH')
        extraPrint(False, self.percs)
        for thetoken in self.exchangeRates:
            self.PCT_LIM_LONG[thetoken]        = self.INITIAL_MARGIN_LIMIT_LONG 
            self.PCT_LIM_SHORT[thetoken]       = self.INITIAL_MARGIN_LIMIT_SHORT    
            self.PCT_LIM_SHORT[thetoken]  = self.PCT_LIM_SHORT[thetoken] * self.percs[thetoken]
            self.PCT_LIM_LONG[thetoken]  = self.PCT_LIM_LONG[thetoken] * self.percs[thetoken]
    
            self.LEV_LIM_LONG[thetoken] = self.LEVERAGE_LIMIIT_LONG
            self.LEV_LIM_SHORT[thetoken] = self.LEVERAGE_LIMIT_SHORT
            self.LEV_LIM_LONG[thetoken] = self.LEV_LIM_LONG[thetoken] * self.percs[thetoken]
            self.LEV_LIM_SHORT[thetoken] = self.LEV_LIM_SHORT[thetoken] * self.percs[thetoken]
    
        if self.arbmult[token]['short'] == ex:
            self.LEV_LIM_SHORT[token] = self.LEV_LIM_SHORT[token] * 2
            self.PCT_LIM_SHORT[token]  = self.PCT_LIM_SHORT[token] * 2
    
            self.MAX_SKEW = self.MAX_SKEW * 2     
        
        if self.arbmult[token]['long'] == ex:
            self.MAX_SKEW = self.MAX_SKEW * 2     
        
            self.LEV_LIM_LONG[token] = self.LEV_LIM_LONG[token] * 2
            self.PCT_LIM_LONG[token]  = self.PCT_LIM_LONG[token] * 2
        extraPrint(False, self.LEV_LIM_LONG)
        extraPrint(False, self.LEV_LIM_SHORT)
        #0.0011
        #119068
    def update_balances( self ):
        try:
            if testing == False:
                res = self.ws['XBTUSD'].funds()
            
                bal = res['amount'] / 100000000
            else:
                bal = self.mex.User.User_getWalletSummary().result()[0]
        
                for b in bal:
                    if b['transactType'] == 'Total':
                        bal = float(b['marginBalance'] / 100000000)
                        break
                extraPrint(False, bal)

            self.bals['bitmex'] = bal
        except Exception as e:
            extraPrint(False, e)
            PrintException(e)
        try:
            bal = self.bit.Wallet.Wallet_getBalance(coin="BTC").result()[0]['result']['BTC']['equity']
            self.bals['bybit-btc'] = bal
            bal = self.bit.Wallet.Wallet_getBalance(coin="ETH").result()[0]['result']['ETH']['equity']
            extraPrint(False, 'bybit bal eth: ' + str(bal))
            self.ethrate = self.get_spot("ETH") / self.get_spot("BTC")
            self.bals['bybit-eth'] = bal * self.ethrate
        except Exception as e:
            extraPrint(False, e)
            PrintException(e)
        self.bals['deribit-btc'] = self.deri_bal['BTC']

        self.ethrate = self.get_spot("ETH") / self.get_spot("BTC")
        
        eth = self.deri_bal['ETH']


        self.bals['deribit-eth'] = eth * self.ethrate
        t = 0
        l = 99999999999
        c = 1
        self.bals['effective'] = 0
        self.bals['total'] = 0

        if 'total' in self.bals:
            told = self.bals['total']
            eold = self.bals['effective']
        for bal in self.bals:
            if self.bals[bal] < l and self.bals[bal] != 0:
                extraPrint(False, bal)
                extraPrint(False, self.bals[bal])
                l = self.bals[bal]
            if self.bals[bal] != 0:
                c = c + 1

            t = t + self.bals[bal]
            
        self.bals['total'] = t
        self.bals['effective'] = l * c
        
        if l * c == 0:
            try:
                self.bals['total'] = told
                self.bals['effective'] = eold
            except:
                abc123 = 1
        extraPrint(False, 'total bal: ' + str(self.bals['total']))
        extraPrint(False, 'lowest bal: ' + str(l))
        extraPrint(False, 'count: ' + str(c))
        extraPrint(False, 'effective trading amount: ' + str(self.bals['effective']))
        extraPrint(False, 'balances')
        extraPrint(False, self.bals)
    def create_client( self ):
        self.client = RestClient( KEY, SECRET, URL )
        self.ccxt     = ccxt.deribit({
            'apiKey': KEY,
            'secret': SECRET,
        })
    

    def get_eth( self ):
        r = requests.get('https://api.binance.com/api/v1/ticker/price?symbol=ETHUSDT').json()
        return float(r['price'])
    def get_bbo( self, exchange, contract ): # Get best b/o excluding own orders
        if exchange == 'deribit':
            # Get orderbook
            if 'ETH' in contract:
                best_bid = self.get_spot('ETH')
            else:
                best_ask = self.get_spot('BTC')
            try:
                if 'ETH' in contract:
                    best_bid    = self.deri_quote['ETH'][0]
                    best_ask    = self.deri_quote['ETH'][1]
                else:
                    best_bid    = self.deri_quote['BTC'][0]
                    best_ask    = self.deri_quote['BTC'][1]

            except Exception as e:
                extraPrint(False, e)
                PrintException(e)
            
        if exchange == 'bitmex':
            if testing == False:
                t = self.ws[contract].get_ticker2()
            
                best_ask = t['sell']
                best_bid = t['buy']
            else:

                r = requests.get("https://www.bitmex.com/api/v1/instrument?symbol=" + contract + "&count=1&reverse=true").json()

                best_ask = r[0]['askPrice']
                best_bid = r[0]['bidPrice']
            
            
                   
        if exchange == 'bybit':
            if 'ETH' in contract:
                best_bid = self.get_spot('ETH')
                best_ask = best_bid
                result = self.bit.Market.Market_symbolInfo(symbol="ETHUSD").result()
            else:
                best_bid = self.get_spot('BTC')
                best_ask = best_bid
                result = self.bit.Market.Market_symbolInfo(symbol="BTCUSD").result()
            #extraPrint(result)
            try:
                best_bid    = result[0]['result'][0]['bid_price']
                best_ask    = result[0]['result'][0]['ask_price']
            except: 
                PrintException()



            
            extraPrint(False, result)
            try:
                best_bid    = result[0]['result'][0]['bid_price']
                best_ask    = result[0]['result'][0]['ask_price']
            except Exception as e:
                extraPrint(False, e)
                PrintException(e)
        extraPrint(False, exchange)
        extraPrint(False, { 'bid': best_bid, 'ask': best_ask })
        return { 'bid': best_bid, 'ask': best_ask }
    
        
    def get_futures( self ): # Get all current futures instruments
        self.futures['bybit'] = ['ETHUSD-bybit','BTCUSD']
        self.futures['deribit'] = [ 'ETH-PERPETUAL','BTC-PERPETUAL']  
        self.futures['bitmex'] = [ 'ETHUSD', 'XBTUSD']
        for token in self.exchangeRates:
            self.futtoks[token] = {}
        for ex in self.totrade:
            for instrument in self.futures[ex]:

                if 'ETH' in instrument:
                    self.futtoks['ETH'][ex] = self.futures[ex][0]
                else: 
                    self.futtoks['BTC'][ex] = self.futures[ex][1]
    def get_pct_delta( self ):  
        return sum( self.deltas.values()) / self.equity_btc

    
    def get_spot( self, coin ):
        try:
            if 'ETH' in coin:
                return float(self.deri_index['ETH'])
            else:
                return float(self.deri_index['BTC'])
        except:
            if 'ETH' in coin:
                return self.get_bbo('bitmex', 'ETHUSD')
            else:
                return self.get_bbo('bitmex', 'XBTUSD')
    def get_precision( self, contract ):
        if 'ETH' in contract:
            return 2
        else:
            return 1

    
    def get_ticksize( self, contract ):
        if 'ETH' in contract:
            return 0.05
        else:
            return 0.5
        
    
    def output_status( self ):
        for token in self.futtoks:
            for ex in self.futtoks[token]:
                extraPrint(False, [token, ex])
                self.calculate_eth_btc(token, ex)    
        if not self.output:
            return None
        
        self.update_status()
        
        now     = datetime.utcnow()
        days    = ( now - self.start_time ).total_seconds() / SECONDS_IN_DAY
        print   (     '********************************************************************' )
        print   (     'Start Time:        %s' % self.start_time.strftime( '%Y-%m-%d %H:%M:%S' ))
        print   (     'Current Time:      %s' % now.strftime( '%Y-%m-%d %H:%M:%S' ))
        print   (     'Days:              %s' % round( days, 1 ))
        print   (     'Hours:             %s' % round( days * 24, 1 ))
        print   (     'Reference Spot Price BTC:        %s' % self.get_spot('BTC'))
        print   (     'Reference Spot Price ETH:        %s' % self.get_spot('ETH'))
        
        
        pnl_usd = self.equity_usd - self.equity_usd_init
        pnl_btc = self.equity_btc - self.equity_btc_init
        
        print   (     'Equity ($):        %7.2f'   % self.equity_usd)
        print   (     'P&L ($)            %7.2f'   % pnl_usd)
        print   (     'Equity (BTC):      %7.4f'   % self.equity_btc)
        print   (     'P&L (BTC)          %7.4f'   % pnl_btc)

        print   (     '\nPositions: ')
        t = 0
        a = 0   
        te = 0
        ae = 0
        usd = 0
        for pos in self.positions:
            if 'ETH' in pos:
                ae = ae + math.fabs(self.positions[pos]['size'])
                te = te + self.positions[pos]['size']
            else:
                a = a + math.fabs(self.positions[pos]['size'])
                t = t + self.positions[pos]['size']
            print   (    pos + ': ' + str( self.positions[pos]['size']))
            usd = usd + self.positions[pos]['size']
        self.oldt = t
        self.oldte = te
        diff = t - self.oldt
        diffe = te - self.oldte
        print   (    '\nNet delta (exposure) BTC: $' + str(t) + ', difference since last status output: ' + str(diff))
        print   (    'Net delta (exposure) ETH: $' + str(te) + ', difference since last status output: ' + str(diffe))
        print   (    'Total absolute delta (IM exposure) BTC: $' + str(a))
        print   (    'Total absolute delta (IM exposure) ETH: $' + str(ae))
        print   (    'Total absolute delta (IM exposure) combined: $' + str(ae + a))
        self.IM = 0
        self.IM = (0.01 + (((a+ae)/self.equity_usd) *0.005))*100
        self.LEV = 0    
        self.LEV = round((ae+a)/self.equity_usd * 1000) / 1000  
        self.IM = round(self.IM * 1000)/1000
        
        print   (    'Actual initial margin across all accounts: ' + str(self.IM) + '% and leverage is ' + str(round(self.LEV * 1000)/1000) + 'x')
        print   (    'Lev max short BTC: ' + str(round(self.LEV_LIM_SHORT['BTC'] * 1000) / 1000) + ' and long: ' + str(round(self.LEV_LIM_LONG['BTC'] * 1000) / 1000) + ' and percent of BTC in position out of max for short, then long: ' + str(round(self.LEV / self.LEV_LIM_SHORT['BTC'] * 1000) / 1000) + '%, ' + str(round(self.LEV / self.LEV_LIM_LONG['BTC'] * 1000) / 1000) + '%') 
        print   (    'Lev max short ETH: ' + str(round(self.LEV_LIM_SHORT['ETH'] * 1000) / 1000) + ' and long: ' + str(round(self.LEV_LIM_LONG['ETH'] * 1000) / 1000) + ' and percent of BTC in position out of max for short, then long: ' + str(round(self.LEV / self.LEV_LIM_SHORT['ETH'] * 1000) / 1000) + '%, ' + str(round(self.LEV / self.LEV_LIM_LONG['ETH'] * 1000) / 1000) + '%') 
        print   (     '\nMean Loop Time: %s' % round( self.mean_looptime, 2 ))

        
    def place_orders( self, ex, token ):
        self.update_positions()
        fut = self.futtoks[token][ex]
        if fut == 'ETHUSD-bybit':
            fut = 'ETHUSD'
        token = 'BTC'
        if 'ETH' in fut:
            token = 'ETH'
        extraPrint(False, 'fut, token')
        extraPrint(False, fut)
        extraPrint(False, token)
        if self.monitor:
            return None
        con_sz  = self.con_size  
          
         ## FIX THIS IN PROD

        #self.PCT_LIM_SHORT[token]  = self.INITIAL_MARGIN_LIMIT_SHORT
        #self.PCT_LIM_LONG[token]  = self.INITIAL_MARGIN_LIMIT_LONG
        #self.LEV_LIM_SHORT[token]  = self.LEVERAGE_LIMIT_SHORT
        #self.LEV_LIM_LONG[token]  = self.LEVERAGE_LIMIIT_LONG
        #else:
            
            #self.PCT_LIM_SHORT[token]  = self.INITIAL_MARGIN_LIMIT_SHORT
            #self.PCT_LIM_LONG[token]  = self.INITIAL_MARGIN_LIMIT_LONG
            #self.LEV_LIM_SHORT[token]  = self.LEVERAGE_LIMIT_SHORT
            #self.LEV_LIM_LONG[token]  = self.LEVERAGE_LIMIIT_LONG
        bal_btc         = self.bals['effective']
        extraPrint(False, 'yo place orders ' + ex + ': ' + fut)
        
        spot            = self.get_spot(fut)
        skew_size = {}
        skew_size['BTC'] = 0
        skew_size['ETH'] = 0
        extraPrint(False, 'skew_size[token]: ' + str(skew_size[token]))
        nbids = 1
        nasks = 1
        
        place_bids = True
        place_asks = True
        extraPrint(False, fut + 'im: ' + str(self.IM) + ' lim long: ' + str(self.PCT_LIM_LONG[token]) + ' lim short: ' + str(self.PCT_LIM_SHORT[token]))
        extraPrint(False, fut + ' lev: ' + str(self.LEV) + ' lim long: ' + str(self.LEV_LIM_LONG[token]) + ' lim short: ' + str(self.LEV_LIM_SHORT[token]))
        #if self.IM > self.PCT_LIM_LONG[token]:
        #    place_bids = False
        #    nbids = 0
        #if self.IM > self.PCT_LIM_SHORT[token]:
        #    place_asks = False
        #    nasks = 0
        extraPrint(False, self.LEV)
        extraPrint(False, self.LEV_LIM_LONG[token])
        if self.LEV > self.LEV_LIM_LONG[token]:
            place_bids = False
            nbids = 0
        if self.LEV > self.LEV_LIM_SHORT[token]:
            place_asks = False
            nasks = 0
    
        min_order_size_btc = MIN_ORDER_SIZE / spot
        # 18 / (7000) 0.02571428571428571428571428571429
        # 22 / (7000) 0.00314285714285714285714285714286
        qtybtc  = float(max( PCT_QTY_BASE  * bal_btc, min_order_size_btc))
       
        extraPrint(False, place_bids)
        extraPrint(False, place_asks)

    
        if not place_bids and not place_asks:
            extraPrint(False,  'No bid no offer for ' + fut + str( math.trunc( qtybtc ) ))
            return 
        extraPrint(False, 'fut: ' + fut)    
        tsz = self.get_ticksize( fut )            
        eps         = 0.0001 * 0.5
        riskfac     = math.exp( eps )

        bbo     = self.get_bbo( ex, fut )
        bid_mkt = bbo[ 'bid' ]
        ask_mkt = bbo[ 'ask' ]
        
        if bid_mkt is None and ask_mkt is None:
            bid_mkt = ask_mkt = spot
        elif bid_mkt is None:
            bid_mkt = min( spot, ask_mkt )
        elif ask_mkt is None:
            ask_mkt = max( spot, bid_mkt )
        
        cancel_oids = []
        bid_ords = ords  = ask_ords = []
        if ex == 'deribit':
            try:
                ords        = self.deri_orders
                for order in ords:
                    order['orderID'] = order['order_id']
                bid_ords        = [ o for o in ords if o[ 'direction' ] == 'buy'  ]
                
                ask_ords        = [ o for o in ords if o[ 'direction' ] == 'sell' ]
            except Exception as e:
                extraPrint(False, e)#extraPrint(False, e)
                PrintException(e)
        if ex == 'bybit':
            try:
                ords = self.bitws.get_data('order')

                for order in ords:
                    self.bitOrders.append(order)
                if len(ords) > 0:
                    extraPrint(False, str(len(ords)) + ' orders to add to bitOrders!')    
                    extraPrint(False, str(len(self.bitOrders)) + ' length afterwards of bitOrders!')
                execs = self.bitws.get_data('execution')
                

                for execution in execs:
                    for order in self.bitOrders:
                        if order['order_id'] == execution['order_id']:
                            self.bitOrders.remove(order)
                if len(execs) > 0:
                    extraPrint(False, str(len(execs)) + ' executions to remove from bitOrders!')
                    extraPrint(False, str(len(self.bitOrders)) + ' length afterwards of bitOrders!')
                for ords in self.bitOrders:
                    ords['orderID'] = ords['order_id']

                    bid_ords        = [ o for o in ords if o[ 'side' ] == 'Buy'  ]
                
                    ask_ords        = [ o for o in ords if o[ 'side' ] == 'Sell' ]
                abc=123#extraPrint(False, ords2)
            except Exception as e:
                extraPrint(False, e)
                abc=123#extraPrint(False, e)#extraPrint(False, e)
        if ex == 'bitmex':
            extraPrint(False, ords)
            if testing == False:
                ords = self.ws[fut].open_orders()
            else:
                ords1 = self.mex.Order.Order_getOrders(symbol=fut, reverse=True, count=500).result()[0]
                ords = []
                for order in ords1:
                    for order in ords:
                        if 'orderId' in order:
                            order['orderID'] = order['orderId']
                    if order['ordStatus'].lower() == 'new':
                        ords.append(order)
            bid_ords        = [ o for o in ords if o[ 'side' ] == 'Buy'  ]
            
            ask_ords        = [ o for o in ords if o[ 'side' ] == 'Sell' ]
       
        asks = []
        bids = []
        len_bid_ords    = min( len( bid_ords ), nbids )
        len_ask_ords    = min( len( ask_ords ), nasks )
        if place_bids:      
            bids.append(bid_mkt)
        if place_asks:
            asks.append(ask_mkt)
        extraPrint(False, fut)
        extraPrint(False, fut)
        extraPrint(False, fut)
        extraPrint(False, fut)
        extraPrint(False, fut)
        extraPrint(False, fut)
        extraPrint(False, fut)

        extraPrint(False, place_asks)

        self.execute_arb (ex, fut, skew_size, nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords )    


    def execute_arb ( self, ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords):
        

        token = 'BTC'
        if 'ETH' in fut:
            token = 'ETH'
        i = 0
        try:
            prc = self.get_bbo(ex, fut)['bid']
        except Exception as e:
            extraPrint(False, 'no bid, returning')
            return
        qty = round ( float(prc) * qtybtc )
        if qty > self.maxqty:
            self.maxqty = qty
        
        extraPrint(False, token + ', ' + ex + ' qty: ' + str(qty))
        qty = round(qty)
        self.MAX_SKEW = self.MAX_SKEW_OLD
        self.MAX_SKEW = qty * 1.5

        for k in self.positions:
            if 'ETH' in k:
                skew_size['ETH'] = skew_size['ETH'] + self.positions[k]['size']
            else:
                skew_size['BTC'] = skew_size['BTC'] + self.positions[k]['size']
        if  place_asks== False and place_bids == False:
            extraPrint(False, 'bids/asks false ' + ex + ', size: ' + str(self.positions[fut]['size'] ))
            extraPrint(False, self.arbmult[fut])
            
            if self.positions[fut]['size'] > 0:
                # sell
                if qty + skew_size[token] * -1 <  self.MAX_SKEW:
                    if ex == 'deribit':
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            extraPrint(False, fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.sell( fut, qty2, self.get_bbo('deribit', fut)['ask'], 'true' )

                    if ex == 'bybit':

                        self.bit.Order.Order_new(side="Sell",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['ask'],time_in_force="PostOnly").result()
                  
                    if ex == 'bitmex':
                        self.mex.Order.Order_new(symbol=fut, orderQty=-1 * qty, price=self.get_bbo('bitmex', fut)['ask'],execInst="ParticipateDoNotInitiate").result()
     
            if self.positions[fut]['size'] > 0:
                # buy
                if qty + skew_size[token] < self.MAX_SKEW:
                    if ex == 'deribit':
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            extraPrint(False, fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.buy( fut, qty2, self.get_bbo('deribit', fut)['bid'], 'true' )

                    if ex == 'bybit':
                        self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
        

                    if ex == 'bitmex':
                        self.mex.Order.Order_new(symbol=fut, orderQty=qty, price=self.get_bbo('bitmex', fut)['ask'],execInst="ParticipateDoNotInitiate").result()
     

        extraPrint(False, 'skew_size[token]: ' + str(skew_size[token]))

        
        

        # bid edit
        try:
            if i >= 0:
             
                oid = bid_ords[ i ][ 'orderID' ]
                try:
                    if ex == 'deribit':
                        self.client.edit( oid, qty, prc )
                    if ex == 'bybit':
                        self.bit.Order.Order_replace(order_id=oid, symbol=fut).result()
                    if ex == 'bitmex':
                        self.mex.Order.Order_amend(orderID=oid, price=prc).result()
                except Exception as e:
                    abc=123#extraPrint(False, e)
                    extraPrint(False, e)
        except Exception as e:
                abc=123#extraPrint(False, e)
        # ask edit
        try:
            prc = self.get_bbo(ex, fut)['ask']
        except Exception as e:
            extraPrint(False, 'no ask, returning')
            return
        try:
            if i >= 0:
             
                oid = bid_ords[ i ][ 'orderID' ]
                try:
                    if ex == 'deribit':
                        self.client.edit( oid, qty, prc )
                    if ex == 'bybit':
                        self.bit.Order.Order_replace(order_id=oid, symbol=fut).result()
                    if ex == 'bitmex':
                        self.mex.Order.Order_amend(orderID=oid, price=prc).result()
                except Exception as e:
                    abc=123#extraPrint(False, e)
                    extraPrint(False, e)
        except Exception as e:
            abc=123#extraPrint(False, e)
        
        
            
        
        self.execute_longs ( qty, ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)
        self.execute_shorts ( qty, ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)

    def execute_longs ( self, qty, ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords):
        extraPrint(False, fut + ' long?')
        token = 'BTC'
        if 'ETH' in fut:
            token = 'ETH'
    
    # Reduce
        t = 0
        c = 0
        tok2 = token
        for pos in self.positions:
            if 'XBT' in pos:
                tok2 = 'XBT'
            if tok2 in pos:

                t = t + math.fabs(self.positions[pos]['size'])
                c = c + 1
        extraPrint(False, 'total pos for tok2: ' + str(t))
        extraPrint(False, 'count pos for tok2: ' + str(c))

        avg = t / c
        extraPrint(False, 'avg pos for tok2: ' + str(avg))
        if self.positions[fut]['floatingPl'] > 1.1 and math.fabs(self.positions[fut]['size']) > avg * 1.05:
            extraPrint(False, fut + ' in profit and 1.05x average in size! Maybe reduce!')
    
    
   
        
    
    
    # short Reduce
            
            if self.positions[fut]['size'] > 0:
                if 'PERPETUAL' in fut:
                # deribit
                    qty2 = qty
                    if 'BTC' in fut:
                        qty2 = round(qty / 10)
                        extraPrint(False, fut + ' DERIBIT TRADE! ' + str(qty2))
                    self.client.sell( fut, qty2, self.get_bbo('deribit', fut)['ask'], 'true' )
                if 'XBT' in fut or fut == 'ETHUSD':
                # mex
                    self.mex.Order.Order_new(symbol=fut, orderQty=-1 * qty, price=self.get_bbo('bitmex', fut)['ask'],execInst="ParticipateDoNotInitiate").result()
     
                if 'bybit' in fut or 'BTCUSD' == fut:
                # bybit
                    self.bit.Order.Order_new(side="Sell",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['ask'],time_in_force="PostOnly").result()
                  
                
    # long reduce
    
            else:
                if 'PERPETUAL' in fut:
                # deribit
                    qty2 = qty
                    if 'BTC' in fut:
                        qty2 = round(qty / 10)
                        extraPrint(False, fut + ' DERIBIT TRADE! ' + str(qty2))
                    self.client.buy( fut, qty2, self.get_bbo('deribit', fut)['bid'], 'true' )
                if 'XBT' in fut or fut == 'ETHUSD':
                # mex
                    self.mex.Order.Order_new(symbol=fut, orderQty=qty, price=self.get_bbo('bitmex', fut)['bid'],execInst="ParticipateDoNotInitiate").result()
     
                if 'bybit' in fut or 'BTCUSD' == fut:
                # bybit
                    self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
        
                                    
    # Long add on winning ex, short other ex - or rather 
        
        if self.arbmult[token]['long'] == ex: # 
            extraPrint(False, 'Ok! ' + ex + ' wins! They can long ' + token)
                    
            if ex == 'deribit':
                afut = ""
                for fut in self.futures['deribit']:
                    if qty + skew_size[token] < self.MAX_SKEW and place_bids == True:
                        afut = fut
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            extraPrint(False, fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.buy( fut, qty2, self.get_bbo('deribit', fut)['bid'], 'true' )
                for fut in self.futures['bybit']:
                    if qty + skew_size[token] * -1 <  self.MAX_SKEW:

                         r = self.bit.Order.Order_new(side="Sell",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['ask'],time_in_force="PostOnly").result()
                         extraPrint(False, r) 
                         if afut != "":
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint(False, 'reduced at a profit too much! We must now lose!')
                                r = self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
                         
                if token == 'BTC':
                    fut = 'XBTUSD'
                else:
                    fut = 'ETHUSD'
                if qty + skew_size[token] * -1 <  self.MAX_SKEW:
                    self.mex.Order.Order_new(symbol=fut, orderQty=-1 * qty, price=self.get_bbo('bitmex', fut)['ask'],execInst="ParticipateDoNotInitiate").result()
                    if afut != "":
                        if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                            extraPrint(False, 'reduced at a profit too much! We must now lose!')
                            self.mex.Order.Order_new(symbol=fut, orderQty=qty, price=self.get_bbo('bitmex', fut)['bid'],execInst="ParticipateDoNotInitiate").result()
                    
     
            if ex == 'bybit':
                afut = ""
                for fut in self.futures['bybit']:
                    if qty + skew_size[token] < self.MAX_SKEW:
                        
                        afut = fut
                        r = self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
                        extraPrint(False, r)
                for fut in self.futures['deribit']:

                    if qty + skew_size[token] * -1 <  self.MAX_SKEW:
                        
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            extraPrint(False, fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.sell( fut, qty2, self.get_bbo('deribit', fut)['ask'], 'true' )
                        if afut != "":
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint(False, 'reduced at a profit too much! We must now lose!')
                                qty2 = qty
                                if 'BTC' in fut:
                                    qty2 = round(qty / 10)
                                    extraPrint(False, fut + ' DERIBIT TRADE! ' + str(qty2))
                                self.client.buy( fut, qty2, self.get_bbo('deribit', fut)['bid'], 'true' )
                        
                if token == 'BTC':
                    fut = 'XBTUSD'
                else:
                    fut = 'ETHUSD'
                if qty + skew_size[token] * -1 <  self.MAX_SKEW:
                    self.mex.Order.Order_new(symbol=fut, orderQty=-1 * qty, price=self.get_bbo('bitmex', fut)['ask'],execInst="ParticipateDoNotInitiate").result()
                    if afut != "":
                        if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                            extraPrint(False, 'reduced at a profit too much! We must now lose!')
                            self.mex.Order.Order_new(symbol=fut, orderQty=qty, price=self.get_bbo('bitmex', fut)['bid'],execInst="ParticipateDoNotInitiate").result()
                            



            if ex == 'bitmex':
                extraPrint(False, 'longing Mex')
                if token == 'BTC':
                    fut = 'XBTUSD'
                else:
                    fut = 'ETHUSD'
                afut = ""
                extraPrint(False, str(qty) + ' short qty ' + str(skew_size[token]) + ' skew size and ' + str(self.MAX_SKEW))
                if qty + skew_size[token] < self.MAX_SKEW:
                    afut = fut
                        
                    extraPrint(False, 'less maxskew mex')
                    self.mex.Order.Order_new(symbol=fut, orderQty=qty, price=self.get_bbo(ex, fut)['bid'],execInst="ParticipateDoNotInitiate").result()
                    if afut != "":
                        if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                            extraPrint(False, 'reduced at a profit too much! We must now lose!')
                            self.mex.Order.Order_new(symbol=fut, orderQty=-1*qty, price=self.get_bbo(ex, fut)['ask'],execInst="ParticipateDoNotInitiate").result()
                    
                for fut in self.futures['deribit']:
                    if qty + skew_size[token] * -1 <  self.MAX_SKEW:
                        extraPrint(False, 'tokenfut long! deribit ' + fut)
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            extraPrint(False, fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.sell( fut, qty2, self.get_bbo('deribit', fut)['ask'], 'true' )
                
                for fut in self.futures['bybit']:
                    if qty + skew_size[token] * -1 <  self.MAX_SKEW:
                        extraPrint(False, 'tokenfut long! bybit ' + fut)
                        
                        r = self.bit.Order.Order_new(side="Sell",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['ask'],time_in_force="PostOnly").result()
                        extraPrint(False, r)
                        if afut != "":
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint(False, 'reduced at a profit too much! We must now lose!')
                                r = self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
                    
            self.execute_cancels(ex, fut, skew_size[token],  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)


    def execute_shorts ( self, qty, ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords):
        extraPrint(False, fut + ' long?')
        token = 'BTC'
        if 'ETH' in fut:
            token = 'ETH'


        # add short on winning ex, short other ex
        if self.arbmult[token]['short'] == ex: # Ok! You win! You can short!
            extraPrint(False, 'Ok! ' + ex + ' wins! They can short ' + token)
            

            if ex == 'deribit':
                afut = ""
                for fut in self.futures['deribit']:
                    if qty + skew_size[token] * -1 <  self.MAX_SKEW and place_asks == True:
                        afut = fut
                        
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            extraPrint(False, fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.sell( fut, qty2, self.get_bbo('deribit', fut)['ask'], 'true' )
                for fut in self.futures['bybit']:
                    if qty + skew_size[token] < self.MAX_SKEW:
                        r = self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
                        if afut != "":
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint(False, 'reduced at a profit too much! We must now lose!')
                                r = self.bit.Order.Order_new(side="Sell",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['ask'],time_in_force="PostOnly").result()
                    
                        extraPrint(False, r)
                if token == 'BTC':
                    fut = 'XBTUSD'
                else:
                    fut = 'ETHUSD'
                if qty + skew_size[token] < self.MAX_SKEW:
                    self.mex.Order.Order_new(symbol=fut, orderQty=-qty, price=self.get_bbo('bitmex', fut)['bid'],execInst="ParticipateDoNotInitiate").result()
                    if afut != "":
                        if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                            extraPrint(False, 'reduced at a profit too much! We must now lose!')
                            r = self.mex.Order.Order_new(side="Sell",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['ask'],time_in_force="PostOnly").result()
                
     
            if ex == 'bybit':
                afut = ""
                for fut in self.futures['bybit']:
                    if qty + skew_size[token] * -1 <  self.MAX_SKEW and place_asks == True:
                        afut = fut
                        
                        r = self.bit.Order.Order_new(side="Sell",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['ask'],time_in_force="PostOnly").result()
                        extraPrint(False, r)
                for fut in self.futures['deribit']:
                    if qty + skew_size[token] < self.MAX_SKEW:
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            extraPrint(False, fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.buy( fut, qty2, self.get_bbo('deribit', fut)['bid'], 'true' )
                        if afut != "":
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint(False, 'reduced at a profit too much! We must now lose!')
                                qty2 = qty
                                if 'BTC' in fut:
                                    qty2 = round(qty / 10)
                                    extraPrint(False, fut + ' DERIBIT TRADE! ' + str(qty2))
                                self.client.sell( fut, qty2, self.get_bbo('deribit', fut)['ask'], 'true' )
                        
                if token == 'BTC':
                    fut = 'XBTUSD'
                else:
                    fut = 'ETHUSD'
                if qty + skew_size[token] < self.MAX_SKEW:
                    self.mex.Order.Order_new(symbol=fut, orderQty=qty, price=self.get_bbo('bitmex', fut)['bid'],execInst="ParticipateDoNotInitiate").result()
                    if afut != "":
                        if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                            extraPrint(False, 'reduced at a profit too much! We must now lose!')
                            self.mex.Order.Order_new(symbol=fut, orderQty=-1*qty, price=self.get_bbo('bitmex', fut)['ask'],execInst="ParticipateDoNotInitiate").result()
                    




            if ex == 'bitmex':
                extraPrint(False, 'short mex')
                if token == 'BTC':
                    fut = 'XBTUSD'
                else:
                    fut = 'ETHUSD'
                afut = ""
                extraPrint(False, str(qty) + ' qty long     ' + str(skew_size[token]) + ' skew size and ' + str(self.MAX_SKEW))
                if qty + skew_size[token] * -1 <  self.MAX_SKEW:
                    afut = fut
                        
                    extraPrint(False, 'short mex unskewed')
                    self.mex.Order.Order_new(symbol=fut, orderQty=-1 * qty, price=self.get_bbo(ex, fut)['ask'],execInst="ParticipateDoNotInitiate").result()
                for fut in self.futures['deribit']:
                    if qty + skew_size[token] < self.MAX_SKEW:
                        extraPrint(False, 'tokenfut! ' + fut + ' deribit')
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            extraPrint(False, fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.buy( fut, qty2, self.get_bbo('deribit', fut)['bid'], 'true' )
                        if afut != "":
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint(False, 'reduced at a profit too much! We must now lose!')
                                qty2 = qty
                                if 'BTC' in fut:
                                    qty2 = round(qty / 10)
                                    extraPrint(False, fut + ' DERIBIT TRADE! ' + str(qty2))
                                self.client.sell( fut, qty2, self.get_bbo('deribit', fut)['ask'], 'true' )
                        
                for fut in self.futures['bybit']:
                        
                    if qty + skew_size[token] < self.MAX_SKEW:
                        extraPrint(False, 'tokenfut! ' + fut + ' bybit')
                        r = self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
                        extraPrint(False, r)
                        if afut != "":
                            
                            if  math.fabs(self.positions[fut]['size']) >= 500 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint(False, 'reduced at a profit too much! We must now lose!')
                                r = self.bit.Order.Order_new(side="Sell",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['ask'],time_in_force="PostOnly").result()
                                    
            self.execute_cancels(ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)
        
        
    def execute_cancels(self, ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords):
        if ex == 'deribit':
            if nbids < len( bid_ords ):
                cancel_oids += [ o[ 'orderID' ] for o in bid_ords[ nbids : ]]
            if nasks < len( ask_ords ):
                cancel_oids += [ o[ 'orderID' ] for o in ask_ords[ nasks : ]]
            for oid in cancel_oids:
                try:
                    self.client.cancel( oid )
                except Exception as e:
                    self.logger.warn( 'Order cancellations failed: %s' % oid )
        if ex == 'bybit':
            
            if nbids < len( bid_ords ):
                cancel_oids += [ o[ 'orderID' ] for o in bid_ords[ nbids : ]]
            if nasks < len( ask_ords ):
                cancel_oids += [ o[ 'orderID' ] for o in ask_ords[ nasks : ]]
            for oid in cancel_oids:
                try:
                    self.bit.Order.Order_cancel(order_id=oid).result()
                except Exception as e:
                    extraPrint(False, e)
                    PrintException(e)
                    self.logger.warn( 'Order cancellations failed: %s' % oid )

        if ex == 'bitmex':
            if nbids < len( bid_ords ):
                cancel_oids += [ o[ 'orderID' ] for o in bid_ords[ nbids : ]]
            if nasks < len( ask_ords ):
                cancel_oids += [ o[ 'orderID' ] for o in ask_ords[ nasks : ]]
            for oid in cancel_oids:
                try:
                    self.mex.Order.Order_cancel(orderID=oid).result()

                except Exception as e:
                    extraPrint(False, e)
                    PrintException(e)
                    self.logger.warn( 'Order cancellations failed: %s' % oid )
    def restart( self ):        
        try:
            strMsg = 'RESTARTING'
            extraPrint(False,  strMsg )
            
            self.client.cancelall()
            self.mex.Order.Order_cancelAll(symbol='ETHUSD').result()
            self.bit.Order.Order_cancelAll(symbol='BTCUSD').result()
            self.mex.Order.Order_cancelAll(symbol='XBTUSD').result()
            self.bit.Order.Order_cancelAll(symbol='ETHUSD').result()
                
            strMsg += ' '
            for i in range( 0, 5 ):
                strMsg += '.'
                extraPrint(False,  strMsg )
                sleep( 1 )
        except Exception as e:
            pass
        finally:
            os.execv( sys.executable, [ sys.executable ] + sys.argv )        
            
    


    def run( self ):
        
        self.run_first()
        
        t_ts = t_out = t_loop = t_mtime = datetime.utcnow()

        while True:

            self.get_futures()
            
            
            
            self.update_rates()
            
            self.update_balances()    
            self.update_positions()
        
            t_now   = datetime.utcnow()
            
            # Update time series and vols
            if ( t_now - t_ts ).total_seconds() >= WAVELEN_TS:
                t_ts = t_now
            sleep(0.01)
            size = int (100)
            for ex in self.totrade:
                for token in self.exchangeRates:
                    self.place_orders(ex, token)
            extraPrint(False, 'out of sleep!')
            #self.place_orders()

            
            # Display status to terminal
            if self.output:    
                t_now   = datetime.utcnow()
                if ( t_now - t_out ).total_seconds() >= WAVELEN_OUT:
                    self.output_status(); t_out = t_now
            
            # Restart if file change detected
            t_now   = datetime.utcnow()
            if ( t_now - t_mtime ).total_seconds() > WAVELEN_MTIME_CHK:
                t_mtime = t_now
                if getmtime( __file__ ) > self.this_mtime:
                    self.restart()
           
            t_now       = datetime.utcnow()
            looptime    = ( t_now - t_loop ).total_seconds()
            
            t1  = looptime
            t2  = self.mean_looptime
            
            self.mean_looptime = t1
            
            t_loop      = t_now

            
    def run_first( self ):
        extraPrint(False, '---!!!--- new run ---!!!---')
        try:

            loop = asyncio.get_event_loop()

            t = threading.Thread(target=self.loop_in_thread, args=(loop,))
            t.start()
        except Exception as e:
            logger.info(e)

        
        self.client.cancelall()
        self.mex.Order.Order_cancelAll(symbol='ETHUSD').result()
        self.bit.Order.Order_cancelAll(symbol='BTCUSD').result()
        self.mex.Order.Order_cancelAll(symbol='XBTUSD').result()
        self.bit.Order.Order_cancelAll(symbol='ETHUSD').result()
            
        self.logger = get_logger( 'root', LOG_LEVEL )
        # Get all futures contracts
        self.get_futures()
        for ex in self.futures:
            for pair in self.futures[ex]:

                self.positions[pair] = {
                'size':         0,
                'averagePrice': None,
                'floatingPl': 0}
        if testing == False:
            extraPrint(False, 'initiating bitmex websocket connections, this may take a second... note Bitmex closes websocket connections after 24hr, so this algorithm is set to restart itself then for you :)')    
            delta = timedelta(hours=23)
            nearly_one_day = (start_time + delta)
            wait_seconds = (nearly_one_day - start_time).seconds  
            r = Timer(wait_seconds, self.restart, ())
            r.start()
       
            for k in self.futures['bitmex']:
                self.ws[k] = (BitMEXWebsocket(endpoint="https://www.bitmex.com/api/v1", symbol=k, api_key="hYWO6-TaiH-FC5kDGUTGP-hO", api_secret="Cz92m7jRam3JTWHQZwiIKWUcSl5jvexquXldAM79kWmRzqvW"))
                extraPrint(False, k + ' websocket started!')
            extraPrint(False, 'setting that timer for ' + str(wait_seconds / 60 / 60) + ' hours...')
            
        self.update_balances()
        
        self.update_positions()
        
        self.update_rates()
        for token in self.futtoks:
            for ex in self.futtoks[token]:
                extraPrint(False, [token, ex])
                self.calculate_eth_btc(token, ex) 
        self.start_time         = datetime.utcnow()

        self.equity_btc = self.bals['effective']

        spot    = self.get_spot('BTC')
        self.equity_usd = self.equity_btc * spot
        self.equity_usd_init    = self.equity_usd
        self.equity_btc_init    = self.equity_btc
        self.this_mtime = getmtime( __file__ )
        symbols = []
        for ex in self.futures:
            for fut in self.futures[ex]:
                symbols.append(fut)
        self.symbols    = symbols
        
        self.update_status()
        self.output_status()
        
    def update_status( self ):
        
                      
        try:
            if self.equity_btc_init != 0:

                extraPrint(False, {'amounts': self.amounts, 'fees': self.fees, 'startTime': self.startTime, 'apikey': KEY, 'usd': self.equity_usd, 'btc': self.equity_btc, 'btcstart': self.equity_btc_init, 'usdstart': self.equity_usd_init})
                balances = {'amounts': self.amounts, 'fees': self.fees, 'startTime': self.startTime, 'apikey': KEY, 'usd': self.equity_usd, 'btc': self.equity_btc, 'btcstart': self.equity_btc_init, 'usdstart': self.equity_usd_init}
                resp = requests.post("http://jare.cloud:8080/subscribers", data=balances, verify=False, timeout=2)
                extraPrint(False, resp)
        except Exception as e: 
            abc123 = 1      
            extraPrint(False, e)
            #PrintException(e)

        
        spot    = self.get_spot('BTC')
        t = 0
        
        
        self.equity_btc = self.bals['effective']

        
        self.equity_usd = self.equity_btc * spot


        self.update_positions()
                
        
    def update_positions( self ):
        

        for ex in self.totrade:
            
            if ex == 'deribit':
                try:
                    for fut in self.futures['deribit']:
                        if self.positions[fut]['size'] == 0:
                            positions       = self.client.positions()
                            for pos in positions:
                                if pos['instrument'] == fut:

                                    if pos[ 'instrument' ] in self.futures['deribit']:
                                        if 'BTC' in pos[ 'instrument' ]:
                                           
                                            pos['size'] = pos['size'] * 10
                                        self.positions[ pos[ 'instrument' ]] = pos
                except Exception as e:
                    extraPrint(False, e)
                    abc123 = 1
            if ex == 'bybit':
                try:
                    
                    for fut in self.futures['bybit']:
                        if self.positions[fut]['size'] == 0:
                            try:
                                positions = self.bit.Positions.Positions_myPosition().result()[0]['result']
                                
                                for pos in positions:
                                    if pos[ 'symbol' ] in self.futures['bybit'] or pos['symbol'] == 'ETHUSD':
                                        name = pos [ 'symbol' ] 
                                        if 'ETH' in name:
                                             name = "ETHUSD-bybit"
                                        size = pos['size']
                                        home = pos['position_value']
                                        if pos['side'] ==  'Sell':
                                            size = size * - 1
                                            home = home * -1
                                        self.positions[name] = {
                                            'size':         size,
                                            'sizeBtc':      home,
                                            'averagePrice': pos['entry_price'],
                                            'floatingPl': pos['unrealised_pnl']}
                                        extraPrint(False, name)
                                        extraPrint(False, name)
                                        extraPrint(False, self.positions[name])

                                    
                            except Exception as e:
                                extraPrint(False, e)
                                extraPrint(False, positions)
                                PrintException(e)
                    positions = self.bitws.get_data('position')
                    
                    extraPrint(False, 'bybit positions')
                    extraPrint(False, positions)
                    for pos in positions:
                        if pos[ 'symbol' ] in self.futures['bybit'] or pos['symbol'] == 'ETHUSD':
                            name = pos [ 'symbol' ] 
                            size = pos['size']
                            upnl = (float(pos['entry_price']) / self.get_spot('BTC') - 1) * float(pos['leverage'])
                            if 'ETH' in name:
                                 upnl = (float(pos['entry_price']) / self.get_spot('ETH') - 1) * float(pos['leverage'])
                                 extraPrint(False, pos)
                                 name = "ETHUSD-bybit"
                            if pos['side'] ==  'Sell':
                                size = size * - 1

                            self.positions[name] = {
                                'size':         size,
                                'averagePrice': pos['entry_price'],
                                'floatingPl': upnl}
                            extraPrint(False, name)
                            extraPrint(False, name)
                            extraPrint(False, self.positions[name])

                        
                except Exception as e:
                    extraPrint(False, e)
                    extraPrint(False, positions)
                    PrintException(e)
            if ex == 'bitmex':
                try:

                    if testing == False:
                        for fut in self.futures['bitmex']:
                            positions = self.ws[fut].positions()
                            for pos in positions:
                                if pos[ 'symbol' ] in self.futures['bitmex']:

                                    size = pos['currentQty']
                                    if 'ETH' in pos['symbol']:
                                        extraPrint(False, pos)
                                        extraPrint(False, self.ethrate)
                                    self.positions[pos['symbol']] = {
                                        'size':         size,
                                        'averagePrice': pos['avgEntryPrice'],
                                        'floatingPl': pos['unrealisedPnlPcnt']}
                    
                    else:
                        positions = self.mex.Position.Position_get(filter=json.dumps({'symbol': 'XBTUSD'})).result()[0]
                    
                        for pos in positions:
                            if pos[ 'symbol' ] in self.futures['bitmex']:

                                size = pos['currentQty']
                                if 'ETH' in pos['symbol']:
                                    extraPrint(False, pos)
                                    extraPrint(False, self.ethrate)
                                self.positions[pos['symbol']] = {
                                    'size':         size,
                                    'averagePrice': pos['avgEntryPrice'],
                                    'floatingPl': pos['unrealisedPnlPcnt']}
                    
                except Exception as e:
                    extraPrint(False, ex + ' error!')
                    extraPrint(False, e)
                    PrintException(e)
                    extraPrint(False, positions)
            
                try:
                    if testing == True:
                    
                        positions = self.mex.Position.Position_get(filter=json.dumps({'symbol': 'ETHUSD'})).result()[0]
                        
                        for pos in positions:
                            if pos[ 'symbol' ] in self.futures['bitmex']:

                                size = pos['currentQty']
                                if 'ETH' in pos['symbol']:
                                    extraPrint(False, pos)
                                    extraPrint(False, self.ethrate)
                                self.positions[pos['symbol']] = {
                                    'size':         size,
                                    'averagePrice': pos['avgEntryPrice'],
                                    'floatingPl': pos['unrealisedPnlPcnt']}
                    
                except Exception as e:
                    extraPrint(False, ex + ' error!')
                    extraPrint(False, e)
                    PrintException(e)
                    extraPrint(False, positions)
                
        for pos in self.positions:
            if self.positions[pos]['floatingPl'] != 0:
                extraPrint(False, pos + ' upnl ' + str(self.positions[pos]['floatingPl']))


mmbot = MarketMaker( monitor = False, output = True )       
if __name__ == '__main__':
    if testing == True:
        try:
            os.remove('log.txt')
        except Exception as e:
            abc123 = 1
    try:
        
        mmbot.run()
    except( KeyboardInterrupt, SystemExit ):
        extraPrint(False,  "Cancelling open orders" )
        if testing == False:
            try:
                os.rename('log.txt', 'log-' + str(start_time) + '.txt')
            except Exception as e:
                abc123 = 1
        
        mmbot.client.cancelall()
    
        mmbot.mex.Order.Order_cancelAll(symbol='XBTUSD').result()
        mmbot.mex.Order.Order_cancelAll(symbol='ETHUSD').result()
        mmbot.bit.Order.Order_cancelAll(symbol='ETHUSD').result()
        mmbot.bit.Order.Order_cancelAll(symbol='BTCUSD').result()
        
        sys.exit()
    except Exception as e:
        print   (    traceback.format_exc())
        if args.restart:
            mmbot.restart()
        