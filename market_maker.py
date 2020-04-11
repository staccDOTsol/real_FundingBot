# This code is for sample purposes only, comes as is and with no warranty or guarantee of performance
from bitmex_websocket import BitMEXWebsocket
import linecache
import sys
import threading
from datetime import timedelta
import time
from queue import Queue
from threading import Timer

# changes various behavior for testing. Set to False in production!
testing = True

import inspect  
def PrintException(e):
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    lineno = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno, f.f_globals)
    print ('EXCEPTION IN ({}, LINE {} "{}"): {}'.format(filename, lineno, line.strip(), exc_obj))

def extraPrint(toconsole, string):
    

    if toconsole == True:
        print(string)
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
    #extraPrint(False, "Please install the deribit_api pacakge", file=sys.stderr)
    #extraPrint(False, "    pip3 install deribit_api", file=sys.stderr)
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
DECAY_POS_LIM       = 0.1       # position lim decay factor toward expiry
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



class MarketMaker( object ):
    
    def __init__( self, monitor = True, output = True ):
        self.MAX_SKEW = MIN_ORDER_SIZE * 2.5
        self.MAX_SKEW_OLD = MIN_ORDER_SIZE * 2.5

        self.bit  = bybit.bybit(test=False, api_key="wbNMbu0aTQ7SxqZe58", api_secret="wel8qs4aXR0ytJ3s4zS3AKgCcPUblCVKQFVB")
        #extraPrint(False, dir(bitmex))
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
        self.create_client()
        self.spotBtc = self.get_spot('BTC')

        self.spotEth = self.get_spot('ETH')
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
            
            #extraPrint(False, 'funding')
            #extraPrint(False, res[0])
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
                
            #extraPrint(False, 'shorting n longing')
        extraPrint(False, self.arbmult)
        #extraPrint(False, self.exchangeRates)
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
            self.PCT_LIM_SHORT[token]  = self.PCT_LIM_SHORT[token] * self.percs[token]
            self.PCT_LIM_LONG[token]  = self.PCT_LIM_LONG[token] * self.percs[token]
    
            self.LEV_LIM_LONG[thetoken] = self.LEVERAGE_LIMIIT_LONG
            self.LEV_LIM_SHORT[thetoken] = self.LEVERAGE_LIMIT_SHORT
            self.LEV_LIM_LONG[token] = self.LEV_LIM_LONG[token] * self.percs[token]
            self.LEV_LIM_SHORT[token] = self.LEV_LIM_SHORT[token] * self.percs[token]
    
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
            bal = self.mex.User.User_getWalletSummary().result()[0]
        
            for b in bal:
                if b['transactType'] == 'Total':
                    bal = float(b['marginBalance'] / 100000000)
                    break
            #extraPrint(False, bal)
            bal = bal
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
        bal = self.client.account()['equity']
        self.bals['deribit-btc'] = bal
        account         = self.ccxt.fetchBalance({'currency': 'ETH'})
        bal_eth         = account['info']['result'][ 'equity' ] 
        self.ethrate = self.get_spot("ETH") / self.get_spot("BTC")
        self.bals['deribit-eth'] = bal_eth * self.ethrate
        t = 0
        l = 99999999999
        c = 1
        for bal in self.bals:
            if self.bals[bal] < l:
                extraPrint(False, bal)
                extraPrint(False, self.bals[bal])
                l = self.bals[bal]
            t = t + self.bals[bal]
            c = c + 1
        self.bals['total'] = t
        self.bals['effective'] = l * c
        extraPrint(False, 'total bal: ' + str(self.bals['total']))
        extraPrint(False, 'lowest bal: ' + str(l))
        extraPrint(False, 'effective trading amount: ' + str(self.bals['effective']))
        #extraPrint(False, 'balances')
        #extraPrint(False, self.bals)
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
            ob      = self.client.getorderbook( contract )
            bids    = ob[ 'bids' ]
            asks    = ob[ 'asks' ]
            if 'ETH' in contract:
                best_bid = self.spotEth
                best_ask = best_bid
            else:
                best_bid = self.spotBtc
                best_ask = best_bid
            try:
                best_bid    = bids[0]['price']
                best_ask    = asks[0]['price']
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
                best_bid = self.spotEth
                best_ask = best_bid
                result = self.bit.Market.Market_symbolInfo(symbol="ETHUSD").result()
            else:
                best_bid = self.spotBtc
                best_ask = best_bid
                result = self.bit.Market.Market_symbolInfo(symbol="BTCUSD").result()
            #extraPrint(False, result)
            try:
                best_bid    = result[0]['result'][0]['bid_price']
                best_ask    = result[0]['result'][0]['ask_price']
            except Exception as e:
                extraPrint(False, e)
                PrintException(e)
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
        print(self.futtoks)
    def get_pct_delta( self ):  
        return sum( self.deltas.values()) / self.equity_btc

    
    def get_spot( self, coin ):
        if 'ETH' in coin:
            r = requests.get('https://api.binance.com/api/v1/ticker/price?symbol=ETHUSDT').json()
            return float(r['price'])
        else:
            return self.client.index()[ 'btc' ]
    
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
        
        if not self.output:
            return None
        
        self.update_status()
        
        now     = datetime.utcnow()
        days    = ( now - self.start_time ).total_seconds() / SECONDS_IN_DAY
        extraPrint(True,  '********************************************************************' )
        extraPrint(True,  'Start Time:        %s' % self.start_time.strftime( '%Y-%m-%d %H:%M:%S' ))
        extraPrint(True,  'Current Time:      %s' % now.strftime( '%Y-%m-%d %H:%M:%S' ))
        extraPrint(True,  'Days:              %s' % round( days, 1 ))
        extraPrint(True,  'Hours:             %s' % round( days * 24, 1 ))
        extraPrint(True,  'Reference Spot Price BTC:        %s' % self.spotBtc)
        extraPrint(True,  'Reference Spot Price ETH:        %s' % self.spotEth)
        
        
        pnl_usd = self.equity_usd - self.equity_usd_init
        pnl_btc = self.equity_btc - self.equity_btc_init
        
        extraPrint(True,  'Equity ($):        %7.2f'   % self.equity_usd)
        extraPrint(True,  'P&L ($)            %7.2f'   % pnl_usd)
        extraPrint(True,  'Equity (BTC):      %7.4f'   % self.equity_btc)
        extraPrint(True,  'P&L (BTC)          %7.4f'   % pnl_btc)

        extraPrint(True,  '\nPositions: ')
        t = 0
        a = 0   
        te = 0
        ae = 0
        for pos in self.positions:
            if 'ETH' in pos:
                ae = ae + math.fabs(self.positions[pos]['size'])
                te = te + self.positions[pos]['size']
            else:
                a = a + math.fabs(self.positions[pos]['size'])
                t = t + self.positions[pos]['size']
            extraPrint(True, pos + ': ' + str( self.positions[pos]['size']))
            
        extraPrint(True, '\nNet delta (exposure) BTC: $' + str(t))
        extraPrint(True, 'Net delta (exposure) ETH: $' + str(te))
        extraPrint(True, 'Total absolute delta (IM exposure) BTC: $' + str(a))
        extraPrint(True, 'Total absolute delta (IM exposure) ETH: $' + str(ae))
        extraPrint(True, 'Total absolute delta (IM exposure) combined: $' + str(ae + a))
        self.IM = (0.01 + (((a+ae)/self.equity_usd) *0.005))*100
        self.IM = round(self.IM * 1000)/1000
        extraPrint(True, 'Actual initial margin across all accounts: ' + str(self.IM) + '% and leverage is ' + str(round(self.LEV * 1000)/1000) + 'x')
        extraPrint(True, 'Lev max short BTC: ' + str(round(self.LEV_LIM_SHORT['BTC'] * 1000) / 1000) + ' and long: ' + str(round(self.LEV_LIM_LONG['BTC'] * 1000) / 1000) + ' and percent of BTC in position out of max for short, then long: ' + str(round(self.LEV / self.LEV_LIM_SHORT['BTC'] * 1000) / 1000) + '%, ' + str(round(self.LEV / self.LEV_LIM_LONG['BTC'] * 1000) / 1000) + '%') 
        extraPrint(True, 'Lev max short ETH: ' + str(round(self.LEV_LIM_SHORT['ETH'] * 1000) / 1000) + ' and long: ' + str(round(self.LEV_LIM_LONG['ETH'] * 1000) / 1000) + ' and percent of BTC in position out of max for short, then long: ' + str(round(self.LEV / self.LEV_LIM_SHORT['ETH'] * 1000) / 1000) + '%, ' + str(round(self.LEV / self.LEV_LIM_LONG['ETH'] * 1000) / 1000) + '%') 
        
        extraPrint(True,  '\nMean Loop Time: %s' % round( self.mean_looptime, 2 ))
            
        extraPrint(True,  '' )

        
    def place_orders( self, ex, token ):
        self.update_positions()
        fut = self.futtoks[token][ex]
        if fut == 'ETHUSD-bybit':
            fut = 'ETHUSD'
        token = 'BTC'
        if 'ETH' in fut:
            token = 'ETH'
        if self.monitor:
            return None
        con_sz  = self.con_size  
        self.calculate_eth_btc(token, ex)      
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
        #extraPrint(False, 'yo place orders ' + ex + ': ' + fut)
        
        spot            = self.get_spot(fut)
        skew_size = {}
        skew_size['BTC'] = 0
        skew_size['ETH'] = 0
        #extraPrint(False, 'skew_size[token]: ' + str(skew_size[token]))
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
        if self.LEV > self.LEV_LIM_LONG[token]:
            place_bids = False
            nbids = 0
        if self.LEV > self.LEV_LIM_SHORT[token]:
            place_asks = False
            nasks = 0
    
        min_order_size_btc = MIN_ORDER_SIZE / spot
        # 18 / (7000) 0.02571428571428571428571428571429
        # 22 / (7000) 0.00314285714285714285714285714286
        #extraPrint(False, 'qty of bal: ' + str(PCT_QTY_BASE  * bal_btc))
        #extraPrint(False, str(PCT_QTY_BASE  * bal_btc * spot) + '$')
        qtybtc  = float(max( PCT_QTY_BASE  * bal_btc, min_order_size_btc))
        #extraPrint(False, 'qtybtc: ' + str(qtybtc))
        #extraPrint(False, 'qty $: ' + str(qtybtc * spot))
        #extraPrint(False, 'divided: ' + str(pos_LIM_SHORT[token] / qtybtc))
        extraPrint(False, 'place_x2L ' + ex + '-' + fut)
        extraPrint(False, place_bids)
        extraPrint(False, place_asks)

    
        if not place_bids and not place_asks:
            #extraPrint(False,  'No bid no offer for %s' % fut, math.trunc( pos_LIM_LONG[token]  / qtybtc ) )
            return 
        #extraPrint(False, 'fut: ' + fut)    
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
                ords        = self.client.getopenorders( fut )
                bid_ords        = [ o for o in ords if o[ 'direction' ] == 'buy'  ]
                
                ask_ords        = [ o for o in ords if o[ 'direction' ] == 'sell' ]
            except Exception as e:
                extraPrint(False, e)#extraPrint(False, e)
                PrintException(e)
        if ex == 'bybit':
            try:
                ords = self.bit.Order.Order_getOrders(symbol=fut).result()[0]['result']
                if 'data' in ords:
                    ords2 = ords['data']
                    bid_ords        = [ o for o in ords if o[ 'side' ] == 'Buy'  ]
                
                    ask_ords        = [ o for o in ords if o[ 'side' ] == 'Sell' ]
                abc=123#extraPrint(False, ords2)
            except Exception as e:
                abc=123#extraPrint(False, e)#extraPrint(False, e)
        if ex == 'bitmex':
            #extraPrint(False, ords)
            ords1 = self.mex.Order.Order_getOrders(symbol=fut, reverse=True, count=500).result()[0]
            ords = []
            for order in ords1:

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
        #extraPrint(False, fut)
        #extraPrint(False, fut)
        #extraPrint(False, fut)
        #extraPrint(False, fut)
        #extraPrint(False, fut)
        #extraPrint(False, fut)
        #extraPrint(False, fut)

        #extraPrint(False, place_asks)
        if ex == 'bybit' and 'ETH' in fut:
            fut =  fut.split('-')[0]
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
                            extraPrint(True, fut + ' DERIBIT TRADE! ' + str(qty2))
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
                            extraPrint(True, fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.buy( fut, qty2, self.get_bbo('deribit', fut)['bid'], 'true' )

                    if ex == 'bybit':
                        self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
        

                    if ex == 'bitmex':
                        self.mex.Order.Order_new(symbol=fut, orderQty=qty, price=self.get_bbo('bitmex', fut)['ask'],execInst="ParticipateDoNotInitiate").result()
     

        #extraPrint(False, 'skew_size[token]: ' + str(skew_size[token]))

        
        

        # bid edit
        try:
            try: 
                oid = bid_ords[ i ][ 'orderId' ]
            except Exception as e:
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
        except Exception as e:
                abc=123#extraPrint(False, e)
        # ask edit
        try:
            prc = self.get_bbo(ex, fut)['ask']
        except Exception as e:
            extraPrint(False, 'no ask, returning')
            return
        try:
            try: 
                oid = ask_ords[ i ][ 'orderId' ]
            except Exception as e:
                oid = ask_ords[ i ][ 'orderID' ]
            try:
                if ex == 'deribit':
                    self.client.edit( oid, qty, prc )
                if ex == 'bybit':
                    self.bit.Order.Order_replace(order_id=oid, symbol=fut).result()
                if ex == 'bitmex':
                    self.mex.Order.Order_amend(orderID=oid, price=prc).result()
            except Exception as e:
                abc=123#extraPrint(False, e)
        except Exception as e:
            abc=123#extraPrint(False, e)
        
        
            
        
        self.execute_longs ( qty, ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)
        self.execute_shorts ( qty, ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)

    def execute_longs ( self, qty, ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords):
        print(fut + ' long?')
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
        if self.positions[fut]['floatingPl'] > 0.01 and math.fabs(self.positions[fut]['size']) > avg * 1.05:
            extraPrint(False, fut + ' in profit and 1.05x average in size! Maybe reduce!')
    
    
   
        
    
    
    # short Reduce
            
            if self.positions[fut]['size'] > 0:
                if 'PERPETUAL' in fut:
                # deribit
                    qty2 = qty
                    if 'BTC' in fut:
                        qty2 = round(qty / 10)
                        extraPrint(True, fut + ' DERIBIT TRADE! ' + str(qty2))
                    self.client.sell( fut, qty2, self.get_bbo('deribit', fut)['ask'], 'true' )
                if 'XBT' in fut or fut == 'ETHUSD':
                # mex
                    self.mex.Order.Order_new(symbol=fut, orderQty=-1 * qty, price=self.get_bbo('bitmex', fut)['ask'],execInst="ParticipateDoNotInitiate").result()
     
                if 'bybit' in fut or 'BTCUSD' == fut:
                # bybit
                    if 'bybit' in fut:
                        fut = 'ETHUSD'
                    self.bit.Order.Order_new(side="Sell",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['ask'],time_in_force="PostOnly").result()
                  
                
    # long reduce
    
            else:
                if 'PERPETUAL' in fut:
                # deribit
                    qty2 = qty
                    if 'BTC' in fut:
                        qty2 = round(qty / 10)
                        extraPrint(True, fut + ' DERIBIT TRADE! ' + str(qty2))
                    self.client.buy( fut, qty2, self.get_bbo('deribit', fut)['bid'], 'true' )
                if 'XBT' in fut or fut == 'ETHUSD':
                # mex
                    self.mex.Order.Order_new(symbol=fut, orderQty=qty, price=self.get_bbo('bitmex', fut)['bid'],execInst="ParticipateDoNotInitiate").result()
     
                if 'bybit' in fut or 'BTCUSD' == fut:
                # bybit
                    if 'bybit' in fut:
                        fut = 'ETHUSD'
                    self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
        
                                    
    # Long add on winning ex, short other ex - or rather 
        
        if self.arbmult[token]['long'] == ex: # 
            extraPrint(True, 'Ok! ' + ex + ' wins! They can long ' + token)
                    
            if ex == 'deribit':
                afut = ""
                for fut in self.futures['deribit']:
                    if qty + skew_size[token] < self.MAX_SKEW and place_bids == True:
                        afut = fut
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            extraPrint(True, fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.buy( fut, qty2, self.get_bbo('deribit', fut)['bid'], 'true' )
                for fut in self.futures['bybit']:
                    if qty + skew_size[token] * -1 <  self.MAX_SKEW:
                         if 'ETH' in fut:
                            fut = 'ETHUSD'

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
                        if 'ETH' in fut:
                            fut = 'ETHUSD'
                        r = self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
                        extraPrint(False, r)
                for fut in self.futures['deribit']:

                    if qty + skew_size[token] * -1 <  self.MAX_SKEW:
                        
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            extraPrint(True, fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.sell( fut, qty2, self.get_bbo('deribit', fut)['ask'], 'true' )
                        if afut != "":
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint(False, 'reduced at a profit too much! We must now lose!')
                                qty2 = qty
                                if 'BTC' in fut:
                                    qty2 = round(qty / 10)
                                    extraPrint(True, fut + ' DERIBIT TRADE! ' + str(qty2))
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
                            extraPrint(True, fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.sell( fut, qty2, self.get_bbo('deribit', fut)['ask'], 'true' )
                
                for fut in self.futures['bybit']:
                    if qty + skew_size[token] * -1 <  self.MAX_SKEW:
                        if 'ETH' in fut:
                            fut = 'ETHUSD'
                        extraPrint(False, 'tokenfut long! bybit ' + fut)
                        
                        r = self.bit.Order.Order_new(side="Sell",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['ask'],time_in_force="PostOnly").result()
                        extraPrint(False, r)
                        if afut != "":
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint(False, 'reduced at a profit too much! We must now lose!')
                                r = self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
                    
            self.execute_cancels(ex, fut, skew_size[token],  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)


    def execute_shorts ( self, qty, ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords):
        print(fut + ' long?')
        token = 'BTC'
        if 'ETH' in fut:
            token = 'ETH'


        # add short on winning ex, short other ex
        if self.arbmult[token]['short'] == ex: # Ok! You win! You can short!
            extraPrint(True, 'Ok! ' + ex + ' wins! They can short ' + token)
            

            if ex == 'deribit':
                afut = ""
                for fut in self.futures['deribit']:
                    if qty + skew_size[token] * -1 <  self.MAX_SKEW and place_asks == True:
                        afut = fut
                        
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            extraPrint(True, fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.sell( fut, qty2, self.get_bbo('deribit', fut)['ask'], 'true' )
                for fut in self.futures['bybit']:
                    if qty + skew_size[token] < self.MAX_SKEW:
                        if 'ETH' in fut:
                            fut = 'ETHUSD'
                        r = self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
                        if afut != "":
                            if 'bybit' in fut:
                                fut = "ETHUSD"
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
                        
                        if 'USD' in fut:
                            fut = 'ETHUSD'
                        r = self.bit.Order.Order_new(side="Sell",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['ask'],time_in_force="PostOnly").result()
                        extraPrint(False, r)
                for fut in self.futures['deribit']:
                    if qty + skew_size[token] < self.MAX_SKEW:
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            extraPrint(True, fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.buy( fut, qty2, self.get_bbo('deribit', fut)['bid'], 'true' )
                        if afut != "":
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint(False, 'reduced at a profit too much! We must now lose!')
                                qty2 = qty
                                if 'BTC' in fut:
                                    qty2 = round(qty / 10)
                                    extraPrint(True, fut + ' DERIBIT TRADE! ' + str(qty2))
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
                            extraPrint(True, fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.buy( fut, qty2, self.get_bbo('deribit', fut)['bid'], 'true' )
                        if afut != "":
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint(False, 'reduced at a profit too much! We must now lose!')
                                qty2 = qty
                                if 'BTC' in fut:
                                    qty2 = round(qty / 10)
                                    extraPrint(True, fut + ' DERIBIT TRADE! ' + str(qty2))
                                self.client.sell( fut, qty2, self.get_bbo('deribit', fut)['ask'], 'true' )
                        
                for fut in self.futures['bybit']:
                        
                    if qty + skew_size[token] < self.MAX_SKEW:
                        if 'USD' in fut:
                            fut = 'ETHUSD'
                        extraPrint(False, 'tokenfut! ' + fut + ' bybit')
                        r = self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
                        extraPrint(False, r)
                        if afut != "":
                            
                            if 'bybit' in fut:
                                fut = "ETHUSD"
                            if  math.fabs(self.positions[fut]['size']) >= 500 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint(False, 'reduced at a profit too much! We must now lose!')
                                r = self.bit.Order.Order_new(side="Sell",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['ask'],time_in_force="PostOnly").result()
                                    
            self.execute_cancels(ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)
        
        
    def execute_cancels(self, ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords):
        if ex == 'deribit':
            if nbids < len( bid_ords ):
                cancel_oids += [ o[ 'orderId' ] for o in bid_ords[ nbids : ]]
            if nasks < len( ask_ords ):
                cancel_oids += [ o[ 'orderId' ] for o in ask_ords[ nasks : ]]
            for oid in cancel_oids:
                try:
                    self.client.cancel( oid )
                except Exception as e:
                    self.logger.warn( 'Order cancellations failed: %s' % oid )
        if ex == 'bybit':
            try:
                fut =  fut.split('-')
                
                if 'USD' in fut[0]:
                    fut = fut[0]
                else:
                    fut = fut[1]
                fut =  fut.split(' ')
                if 'USD' in fut[0]:
                    fut = fut[0]
                else:
                    fut = fut[1]
            except Exception as e:
                extraPrint(False, e)
                PrintException(e)
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
                #extraPrint(False,  strMsg )
                sleep( 1 )
        except Exception as e:
            pass
        finally:
            os.execv( sys.executable, [ sys.executable ] + sys.argv )        
            
    


    def run( self ):
        
        self.run_first()
        self.output_status()
        
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
            #extraPrint(False, 'out of sleep!')
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
        
        
        self.client.cancelall()
        self.mex.Order.Order_cancelAll(symbol='ETHUSD').result()
        self.bit.Order.Order_cancelAll(symbol='BTCUSD').result()
        self.mex.Order.Order_cancelAll(symbol='XBTUSD').result()
        self.bit.Order.Order_cancelAll(symbol='ETHUSD').result()
            
        self.logger = get_logger( 'root', LOG_LEVEL )
        # Get all futures contracts
        self.get_futures()
        
        self.update_balances()
        
        self.update_positions()
        
        self.update_rates()
        self.start_time         = datetime.utcnow()

        self.equity_btc = self.bals['effective']

        spot    = self.spotBtc
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
        
        if testing == False:
            extraPrint(False, 'initiating bitmex websocket connections, this may take a second...  Bitmex closes websocket connections after 24hr, so this algorithm is set to restart itself then for you :)')    
            for k in self.futures['bitmex']:
                self.ws[k] = (BitMEXWebsocket(endpoint="https://www.bitmex.com/api/v1", symbol=k, api_key="hYWO6-TaiH-FC5kDGUTGP-hO", api_secret="Cz92m7jRam3JTWHQZwiIKWUcSl5jvexquXldAM79kWmRzqvW"))
                extraPrint(False, k + ' websocket started!')
            delta = timedelta(hours=23)
            nearly_one_day = (start_time + delta)
            wait_seconds = (nearly_one_day - start_time).seconds  
            extraPrint(False, 'setting that timer for ' + str(wait_seconds / 60 / 60) + ' hours...')
            r = Timer(wait_seconds, self.restart, ())
            r.start()
    def update_status( self ):
        
        self.spotBtc = self.spotBtc
        self.ethBtc = self.spotBtc
                      
        try:
            if self.equity_btc_init != 0:

                #extraPrint(False, {'amounts': self.amounts, 'fees': self.fees, 'startTime': self.startTime, 'apikey': KEY, 'usd': self.equity_usd, 'btc': self.equity_btc, 'btcstart': self.equity_btc_init, 'usdstart': self.equity_usd_init})
                balances = {'amounts': self.amounts, 'fees': self.fees, 'startTime': self.startTime, 'apikey': KEY, 'usd': self.equity_usd, 'btc': self.equity_btc, 'btcstart': self.equity_btc_init, 'usdstart': self.equity_usd_init}
                resp = requests.post("http://jare.cloud:8080/subscribers", data=balances, verify=False, timeout=2)
                #extraPrint(False, resp)
        except Exception as e: 
            abc123 = 1      
            #extraPrint(False, e)
            #PrintException(e)

        
        spot    = self.spotBtc
        t = 0
        
        
        self.equity_btc = self.bals['effective']

        
        self.equity_usd = self.equity_btc * spot


        self.update_positions()
                
        
    def update_positions( self ):
        for ex in self.futures:
            for pair in self.futures[ex]:

                self.positions[pair] = {
                'size':         0,
                'averagePrice': None,
                'floatingPl': 0}

        for ex in self.totrade:
            
            if ex == 'deribit':
                positions       = self.client.positions()
                if len(positions) > 0:
                    for pos in positions:

                        if pos[ 'instrument' ] in self.futures['deribit']:
                            if 'BTC' in pos[ 'instrument' ]:
                               
                            	pos['size'] = pos['size'] * 10
                            self.positions[ pos[ 'instrument' ]] = pos
                else:
                    extraPrint(True, ex + ' error!')
                    extraPrint(True, positions)
            if ex == 'bybit':
                try:
                    positions = self.bit.Positions.Positions_myPosition().result()[0]['result']
                    

                    for pos in positions:
                        if pos[ 'symbol' ] in self.futures['bybit'] or pos['symbol'] == 'ETHUSD':
                            name = pos [ 'symbol' ] 
                            size = pos['size']
                            if 'ETH' in name:
                                 extraPrint(False, pos)
                                 name = "ETHUSD-bybit"
                            if pos['side'] ==  'Sell':
                                size = size * - 1
                            self.positions[name] = {
                                'size':         size,
                                'averagePrice': pos['entry_price'],
                                'floatingPl': pos['unrealised_pnl']}
                            extraPrint(False, name)
                            extraPrint(False, name)
                            extraPrint(False, self.positions[name])

                        
                except Exception as e:
                    extraPrint(True, e)
                    extraPrint(positions)
                    PrintException(e)
            if ex == 'bitmex':
                try:
                    positions = self.mex.Position.Position_get(filter=json.dumps({'symbol': 'XBTUSD'})).result()[0]
                    
                    for pos in positions:
                        if pos[ 'symbol' ] in self.futures['bitmex']:

                            size = pos['currentQty']
                            if 'ETH' in pos['symbol']:
                                #extraPrint(False, pos)
                                extraPrint(False, self.ethrate)
                            self.positions[pos['symbol']] = {
                                'size':         size,
                                'averagePrice': pos['avgEntryPrice'],
                                'floatingPl': pos['unrealisedPnlPcnt']}
                
                except Exception as e:
                    extraPrint(True, ex + ' error!')
                    extraPrint(False, e)
                    PrintException(e)
                    extraPrint(True, positions)
            
                try:
                    positions = self.mex.Position.Position_get(filter=json.dumps({'symbol': 'ETHUSD'})).result()[0] 
                
                    for pos in positions:
                        if pos[ 'symbol' ] in self.futures['bitmex']:

                            size = pos['currentQty']
                            if 'ETH' in pos['symbol']:
                                #extraPrint(False, pos)
                                extraPrint(False, self.ethrate)
                            self.positions[pos['symbol']] = {
                                'size':         size,
                                'averagePrice': pos['avgEntryPrice'],
                                'floatingPl': pos['unrealisedPnlPcnt']}
                except Exception as e:
                    extraPrint(True, ex + ' error!')
                    extraPrint(False, e)
                    PrintException(e)
                    extraPrint(True, positions)
            
if __name__ == '__main__':
    if testing == True:
        try:
            os.remove('log.txt')
        except Exception as e:
            abc123 = 1
    try:
        mmbot = MarketMaker( monitor = args.monitor, output = args.output )
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
        print(traceback.format_exc())
        if args.restart:
            mmbot.restart()
        