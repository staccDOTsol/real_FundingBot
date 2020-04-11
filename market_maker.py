# This code is for sample purposes only, comes as is and with no warranty or guarantee of performance
from bitmex_websocket import BitMEXWebsocket
import linecache
import sys
import threading
from datetime import timedelta
import time
from queue import Queue
from threading import Timer

import inspect  
def PrintException():
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    lineno = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno, f.f_globals)
    print ('EXCEPTION IN ({}, LINE {} "{}"): {}'.format(filename, lineno, line.strip(), exc_obj))
def extraPrint(string):
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
    #extraPrint("Please install the deribit_api pacakge", file=sys.stderr)
    #extraPrint("    pip3 install deribit_api", file=sys.stderr)
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
        self.MAX_SKEW = MIN_ORDER_SIZE * 1.5
        self.MAX_SKEW_OLD = MIN_ORDER_SIZE * 1.5

        self.bit  = bybit.bybit(test=False, api_key="wbNMbu0aTQ7SxqZe58", api_secret="wel8qs4aXR0ytJ3s4zS3AKgCcPUblCVKQFVB")
        #extraPrint(dir(bitmex))
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
        for token in self.exchangeRates:
            self.PCT_LIM_LONG[token]        = 10       # % position limit long
            self.LEV_LIM_LONG[token] = 5
            self.LEV_LIM_SHORT[token] = 5
            self.PCT_LIM_SHORT[token]       = 10     # % position limit short
        self.LEV_LIM_SHORT_OLD = 5
        self.LEV_LIM_LONG_OLD = 5
        self.PCT_LIM_LONG_OLD        = 7       # % position limit long

        self.PCT_LIM_SHORT_OLD       = 7
        self.equity_usd         = None
        self.equity_btc         = None
        self.equity_usd_init    = None
        self.equity_btc_init    = 0
        self.con_size           = float( CONTRACT_SIZE )
        self.client             = None
        self.LEV = 1
        self.IM = 1
        self.ccxt = None
        self.ws = {}
        self.tradeids = []
        self.amounts = 0
        self.fees = 0
        self.startTime = int(time.time()*1000)
        self.arbmult = {}
        self.arbmult['BTC'] = {}
        self.arbmult['ETH'] = {}
        self.totrade = ['bybit','bitmex', 'deribit']
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
        #except:
        #    PrintException()
        #try:
        #    res = requests.get("https://api-pub.bitfinex.com/v2/status/deriv?keys=ALL").json()

        #    self.exchangeRates['BTC']['bitfinex'] = res[0][9] * 3
        #    self.exchangeRates['ETH']['bitfinex'] = res[1][9] * 3

        #except:
        #    PrintException()
        try:
            res = requests.get("https://www.deribit.com/api/v2/public/get_funding_rate_value?instrument_name=BTC-PERPETUAL&start_timestamp=" + str(int(time.time() * 1000 - (60 * 60 * 8))) + "&end_timestamp=" + str(int(time.time() * 1000))).json()['result']

            self.exchangeRates['BTC']['deribit'] = res * 3
    
            res = requests.get("https://www.deribit.com/api/v2/public/get_funding_rate_value?instrument_name=ETH-PERPETUAL&start_timestamp=" + str(int(time.time() * 1000 - (60 * 60 * 8))) + "&end_timestamp=" + str(int(time.time() * 1000))).json()['result']

            self.exchangeRates['ETH']['deribit'] = res * 3

        except:
            PrintException()
        try:
            
            res = self.mex.Funding.Funding_get(symbol='XBTUSD', reverse=True, count=1).result()
            
            #extraPrint('funding')
            #extraPrint(res[0])
            res = res[0][0]['fundingRate'] * 3

            self.exchangeRates['BTC']['bitmex'] = res

            res = self.mex.Funding.Funding_get(symbol='ETHUSD', reverse=True, count=1).result()
            res = res[0][0]['fundingRate'] * 3

            self.exchangeRates['ETH']['bitmex'] = res

        except Exception as e:
            PrintException() # PrintException()
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
            PrintException() # PrintException()
        extraPrint(self.exchangeRates)
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
                
            #extraPrint('shorting n longing')
        extraPrint(self.arbmult)
        #extraPrint(self.exchangeRates)
    def calculate_eth_btc( self ):
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
        
        extraPrint('% BTC vs ETH')
        extraPrint(self.percs)
        
        for token in self.exchangeRates:
            self.PCT_LIM_LONG[token]        = 10 
            self.LEV_LIM_LONG[token] = 5
            self.LEV_LIM_SHORT[token] = 5
            self.PCT_LIM_SHORT[token]       = 10    
        for token in self.exchangeRates: 
        
            self.LEV_LIM_LONG[token] = self.LEV_LIM_LONG[token] * self.percs[token]
            self.LEV_LIM_SHORT[token] = self.LEV_LIM_SHORT[token] * self.percs[token]
            self.PCT_LIM_SHORT[token]  = self.PCT_LIM_SHORT[token] * self.percs[token]
            self.PCT_LIM_LONG[token]  = self.PCT_LIM_LONG[token] * self.percs[token]

        #0.0011
        #119068
    def update_balances( self ):
        try:
            bal = self.mex.User.User_getWalletSummary().result()[0]
        
            for b in bal:
                if b['transactType'] == 'Total':
                    bal = float(b['marginBalance'] / 100000000)
                    break
            #extraPrint(bal)
            bal = bal
            self.bals['bitmex'] = bal
        except:
            PrintException()
        try:
            bal = self.bit.Wallet.Wallet_getBalance(coin="BTC").result()[0]['result']['BTC']['equity']
            self.bals['bybit-btc'] = bal
            bal = self.bit.Wallet.Wallet_getBalance(coin="ETH").result()[0]['result']['ETH']['equity']
            extraPrint('bybit bal eth: ' + str(bal))
            self.ethrate = self.get_spot("ETH") / self.get_spot("BTC")
            self.bals['bybit-eth'] = bal * self.ethrate
        except:
            PrintException()
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
                extraPrint(bal)
                extraPrint(self.bals[bal])
                l = self.bals[bal]
            t = t + self.bals[bal]
            c = c + 1
        self.bals['total'] = t
        self.bals['effective'] = l * c
        extraPrint('total bal: ' + str(self.bals['total']))
        extraPrint('lowest bal: ' + str(l))
        extraPrint('effective trading amount: ' + str(self.bals['effective']))
        #extraPrint('balances')
        #extraPrint(self.bals)
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
                best_bid = self.get_spot('ETH')
                best_ask = best_bid
            else:
                best_bid = self.get_spot('BTC')
                best_ask = best_bid
            try:
                best_bid    = bids[0]['price']
                best_ask    = asks[0]['price']
            except:
                PrintException()
            
        if exchange == 'bitmex':
            
            t = self.ws[contract].get_ticker2()

            
            best_ask = t['sell']
            best_bid = t['buy']
            
                   
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
        return { 'bid': best_bid, 'ask': best_ask }
    
        
    def get_futures( self ): # Get all current futures instruments
        self.futures['bybit'] = ['ETHUSD-bybit','BTCUSD']
        self.futures['deribit'] = [ 'ETH-PERPETUAL','BTC-PERPETUAL']  
        self.futures['bitmex'] = [ 'ETHUSD', 'XBTUSD']

    def get_pct_delta( self ):         
        self.update_status()
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
        extraPrint( '********************************************************************' )
        extraPrint( 'Start Time:        %s' % self.start_time.strftime( '%Y-%m-%d %H:%M:%S' ))
        extraPrint( 'Current Time:      %s' % now.strftime( '%Y-%m-%d %H:%M:%S' ))
        extraPrint( 'Days:              %s' % round( days, 1 ))
        extraPrint( 'Hours:             %s' % round( days * 24, 1 ))
        extraPrint( 'Reference Spot Price BTC:        %s' % self.get_spot('BTC'))
        extraPrint( 'Reference Spot Price ETH:        %s' % self.get_spot('ETH'))
        
        
        pnl_usd = self.equity_usd - self.equity_usd_init
        pnl_btc = self.equity_btc - self.equity_btc_init
        
        extraPrint( 'Equity ($):        %7.2f'   % self.equity_usd)
        extraPrint( 'P&L ($)            %7.2f'   % pnl_usd)
        extraPrint( 'Equity (BTC):      %7.4f'   % self.equity_btc)
        extraPrint( 'P&L (BTC)          %7.4f'   % pnl_btc)

        extraPrint( '\nPositions: ')
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
            extraPrint(pos + ': ' + str( self.positions[pos]['size']))
            
        extraPrint('\nNet delta (exposure) BTC: $' + str(t))
        extraPrint('Net delta (exposure) ETH: $' + str(te))
        extraPrint('Total absolute delta (IM exposure) BTC: $' + str(a))
        extraPrint('Total absolute delta (IM exposure) ETH: $' + str(ae))
        extraPrint('Total absolute delta (IM exposure) combined: $' + str(ae + a))
        self.IM = (0.01 + (((a+ae)/self.equity_usd) *0.005))*100
        self.IM = round(self.IM * 1000)/1000
        self.LEV = (self.IM -1)* 2
        extraPrint('Actual initial margin across all accounts: ' + str(self.IM) + '% and leverage is ' + str(round(self.LEV * 1000)/1000) + 'x')
        extraPrint('Lev max short BTC: ' + str(round(self.LEV_LIM_SHORT['BTC'] * 1000) / 1000) + ' and long: ' + str(round(self.LEV_LIM_LONG['BTC'] * 1000) / 1000) + ' and percent of BTC in position out of max for short, then long: ' + str(round(self.LEV / self.LEV_LIM_SHORT['BTC'] * 1000) / 1000) + '%, ' + str(round(self.LEV / self.LEV_LIM_LONG['BTC'] * 1000) / 1000) + '%') 
        extraPrint('Lev max short ETH: ' + str(round(self.LEV_LIM_SHORT['ETH'] * 1000) / 1000) + ' and long: ' + str(round(self.LEV_LIM_LONG['ETH'] * 1000) / 1000) + ' and percent of BTC in position out of max for short, then long: ' + str(round(self.LEV / self.LEV_LIM_SHORT['ETH'] * 1000) / 1000) + '%, ' + str(round(self.LEV / self.LEV_LIM_LONG['ETH'] * 1000) / 1000) + '%') 
        
        extraPrint( '\nMean Loop Time: %s' % round( self.mean_looptime, 2 ))
            
        extraPrint( '' )

        
    def place_orders( self, ex, fut ):
        self.update_positions()
        if fut == 'ETHUSD-bybit':
            fut = 'ETHUSD'
        token = 'BTC'
        if 'ETH' in fut:
            token = 'ETH'
        if self.monitor:
            return None
        con_sz  = self.con_size        
         ## FIX THIS IN PROD

        self.PCT_LIM_SHORT[token]  = self.PCT_LIM_SHORT_OLD
        self.PCT_LIM_LONG[token]  = self.PCT_LIM_LONG_OLD
        self.LEV_LIM_SHORT[token]  = self.LEV_LIM_SHORT_OLD
        self.LEV_LIM_LONG[token]  = self.LEV_LIM_LONG_OLD
        if self.arbmult[token]['short'] == ex:
            self.MAX_SKEW = self.MAX_SKEW * 2
            self.LEV_LIM_SHORT[token] = self.LEV_LIM_SHORT[token] * 2
            self.PCT_LIM_SHORT[token]  = self.PCT_LIM_SHORT[token] * 2
        
        elif self.arbmult[token]['long'] == ex:  
            self.MAX_SKEW = self.MAX_SKEW * 2     
            self.LEV_LIM_LONG[token] = self.LEV_LIM_LONG[token] * 2
            self.PCT_LIM_LONG[token]  = self.PCT_LIM_LONG[token] * 2
        else:
            
            self.PCT_LIM_SHORT[token]  = self.PCT_LIM_SHORT_OLD
            self.PCT_LIM_LONG[token]  = self.PCT_LIM_LONG_OLD
            self.LEV_LIM_SHORT[token]  = self.LEV_LIM_SHORT_OLD
            self.LEV_LIM_LONG[token]  = self.LEV_LIM_LONG_OLD
        bal_btc         = self.bals['effective']
        #extraPrint('yo place orders ' + ex + ': ' + fut)
        
        spot            = self.get_spot(fut)
        skew_size = {}
        skew_size['BTC'] = 0
        skew_size['ETH'] = 0
        #extraPrint('skew_size[token]: ' + str(skew_size[token]))
        nbids = 1
        nasks = 1
        
        place_bids = True
        place_asks = True
        extraPrint(fut + 'im: ' + str(self.IM) + ' lim long: ' + str(self.PCT_LIM_LONG[token]) + ' lim short: ' + str(self.PCT_LIM_SHORT[token]))
        extraPrint(fut + ' lev: ' + str(self.LEV) + ' lim long: ' + str(self.LEV_LIM_LONG[token]) + ' lim short: ' + str(self.LEV_LIM_SHORT[token]))
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
        #extraPrint('qty of bal: ' + str(PCT_QTY_BASE  * bal_btc))
        #extraPrint(str(PCT_QTY_BASE  * bal_btc * spot) + '$')
        qtybtc  = float(max( PCT_QTY_BASE  * bal_btc, min_order_size_btc))
        #extraPrint('qtybtc: ' + str(qtybtc))
        #extraPrint('qty $: ' + str(qtybtc * spot))
        #extraPrint('divided: ' + str(pos_LIM_SHORT[token] / qtybtc))
        extraPrint('place_x2L ' + ex + '-' + fut)
        extraPrint(place_bids)
        extraPrint(place_asks)

    
        if not place_bids and not place_asks:
            #extraPrint( 'No bid no offer for %s' % fut, math.trunc( pos_LIM_LONG[token]  / qtybtc ) )
            return 
        #extraPrint('fut: ' + fut)    
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
                PrintException()#PrintException()
        if ex == 'bybit':
            try:
                ords = self.bit.Order.Order_getOrders(symbol=fut).result()[0]['result']
                if 'data' in ords:
                    ords2 = ords['data']
                    bid_ords        = [ o for o in ords if o[ 'side' ] == 'Buy'  ]
                
                    ask_ords        = [ o for o in ords if o[ 'side' ] == 'Sell' ]
                abc=123#extraPrint(ords2)
            except Exception as e:
                abc=123#PrintException()#PrintException()
        if ex == 'bitmex':
            #extraPrint(ords)
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
        #extraPrint(fut)
        #extraPrint(fut)
        #extraPrint(fut)
        #extraPrint(fut)
        #extraPrint(fut)
        #extraPrint(fut)
        #extraPrint(fut)

        #extraPrint(place_asks)
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
        except:
            extraPrint('no bid, returning')
            return
        qty = round ( float(prc) * qtybtc )
        if qty > self.maxqty:
            self.maxqty = qty
        
        extraPrint(token + ', ' + ex + ' qty: ' + str(qty))
        qty = round(qty)
        self.MAX_SKEW = self.MAX_SKEW_OLD
        self.MAX_SKEW = qty * 1.5

        for k in self.positions:
            if 'ETH' in k:
                skew_size['ETH'] = skew_size['ETH'] + self.positions[k]['size']
            else:
                skew_size['BTC'] = skew_size['BTC'] + self.positions[k]['size']
        if  place_asks== False and place_bids == False:
            extraPrint('bids/asks false ' + ex + ', size: ' + str(self.positions[fut]['size'] ))
            extraPrint(self.arbmult[fut])
            
            if self.positions[fut]['size'] > 0:
                # sell
                if qty + skew_size[token] * -1 <  self.MAX_SKEW:
                    if ex == 'deribit':
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            print(fut + ' DERIBIT TRADE! ' + str(qty2))
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
                            print(fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.buy( fut, qty2, self.get_bbo('deribit', fut)['bid'], 'true' )

                    if ex == 'bybit':
                        self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
        

                    if ex == 'bitmex':
                        self.mex.Order.Order_new(symbol=fut, orderQty=qty, price=self.get_bbo('bitmex', fut)['ask'],execInst="ParticipateDoNotInitiate").result()
     

        #extraPrint('skew_size[token]: ' + str(skew_size[token]))

        
        

        # bid edit
        try:
            try: 
                oid = bid_ords[ i ][ 'orderId' ]
            except:
                oid = bid_ords[ i ][ 'orderID' ]
            try:
                if ex == 'deribit':
                    self.client.edit( oid, qty, prc )
                if ex == 'bybit':
                    self.bit.Order.Order_replace(order_id=oid, symbol=fut).result()
                if ex == 'bitmex':
                    self.mex.Order.Order_amend(orderID=oid, price=prc).result()
            except:
                abc=123#PrintException()
        except:
                abc=123#PrintException()
        # ask edit
        try:
            prc = self.get_bbo(ex, fut)['ask']
        except:
            extraPrint('no ask, returning')
            return
        try:
            try: 
                oid = ask_ords[ i ][ 'orderId' ]
            except:
                oid = ask_ords[ i ][ 'orderID' ]
            try:
                if ex == 'deribit':
                    self.client.edit( oid, qty, prc )
                if ex == 'bybit':
                    self.bit.Order.Order_replace(order_id=oid, symbol=fut).result()
                if ex == 'bitmex':
                    self.mex.Order.Order_amend(orderID=oid, price=prc).result()
            except:
                abc=123#PrintException()
        except:
            abc=123#PrintException()
        
        
            
        
        self.execute_longs ( qty, ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)
        self.execute_shorts ( qty, ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)

    def execute_longs ( self, qty, ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords):
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
        extraPrint('total pos for tok2: ' + str(t))
        extraPrint('count pos for tok2: ' + str(c))

        avg = t / c
        extraPrint('avg pos for tok2: ' + str(avg))
        if self.positions[fut]['floatingPl'] > 0.01 and math.fabs(self.positions[fut]['size']) > avg * 1.05:
            extraPrint(fut + ' in profit and 1.05x average in size! Maybe reduce!')
    
    
   
        
    
    
    # short Reduce
            
            if self.positions[fut]['size'] > 0:
                if 'PERPETUAL' in fut:
                # deribit
                    qty2 = qty
                    if 'BTC' in fut:
                        qty2 = round(qty / 10)
                        print(fut + ' DERIBIT TRADE! ' + str(qty2))
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
                        print(fut + ' DERIBIT TRADE! ' + str(qty2))
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
            extraPrint('Ok! ' + ex + ' wins! They can long!')
                    
            if ex == 'deribit':
                afut = ""
                for fut in self.futures['deribit']:
                    if token in fut and qty + skew_size[token] < self.MAX_SKEW and place_bids == True:
                        afut = fut
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            print(fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.buy( fut, qty2, self.get_bbo('deribit', fut)['bid'], 'true' )
                for fut in self.futures['bybit']:
                    if token in fut and qty + skew_size[token] * -1 <  self.MAX_SKEW:
                         if 'ETH' in fut:
                            fut = 'ETHUSD'

                         r = self.bit.Order.Order_new(side="Sell",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['ask'],time_in_force="PostOnly").result()
                         extraPrint(r) 
                         if afut != "":
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint('reduced at a profit too much! We must now lose!')
                                r = self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
                         
                if token == 'BTC':
                    fut = 'XBTUSD'
                else:
                    fut = 'ETHUSD'
                if qty + skew_size[token] * -1 <  self.MAX_SKEW:
                    self.mex.Order.Order_new(symbol=fut, orderQty=-1 * qty, price=self.get_bbo('bitmex', fut)['ask'],execInst="ParticipateDoNotInitiate").result()
                    if afut != "":
                        if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                            extraPrint('reduced at a profit too much! We must now lose!')
                            self.mex.Order.Order_new(symbol=fut, orderQty=qty, price=self.get_bbo('bitmex', fut)['bid'],execInst="ParticipateDoNotInitiate").result()
                    
     
            if ex == 'bybit':
                afut = ""
                for fut in self.futures['bybit']:
                    if token in fut and qty + skew_size[token] < self.MAX_SKEW:
                        
                        afut = fut
                        if 'ETH' in fut:
                            fut = 'ETHUSD'
                        r = self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
                        extraPrint(r)
                for fut in self.futures['deribit']:
                    if token in fut and qty + skew_size[token] * -1 <  self.MAX_SKEW:
                        
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            print(fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.sell( fut, qty2, self.get_bbo('deribit', fut)['ask'], 'true' )
                        if afut != "":
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint('reduced at a profit too much! We must now lose!')
                                qty2 = qty
                                if 'BTC' in fut:
                                    qty2 = round(qty / 10)
                                    print(fut + ' DERIBIT TRADE! ' + str(qty2))
                                self.client.buy( fut, qty2, self.get_bbo('deribit', fut)['bid'], 'true' )
                        
                if token == 'BTC':
                    fut = 'XBTUSD'
                else:
                    fut = 'ETHUSD'
                if qty + skew_size[token] * -1 <  self.MAX_SKEW:
                    self.mex.Order.Order_new(symbol=fut, orderQty=-1 * qty, price=self.get_bbo('bitmex', fut)['ask'],execInst="ParticipateDoNotInitiate").result()
                    if afut != "":
                        if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                            extraPrint('reduced at a profit too much! We must now lose!')
                            self.mex.Order.Order_new(symbol=fut, orderQty=qty, price=self.get_bbo('bitmex', fut)['bid'],execInst="ParticipateDoNotInitiate").result()
                            



            if ex == 'bitmex':
                extraPrint('longing Mex')
                if token == 'BTC':
                    fut = 'XBTUSD'
                else:
                    fut = 'ETHUSD'
                afut = ""
                extraPrint(str(qty) + ' short qty ' + str(skew_size[token]) + ' skew size and ' + str(self.MAX_SKEW))
                if qty + skew_size[token] < self.MAX_SKEW:
                    afut = fut
                        
                    extraPrint('less maxskew mex')
                    self.mex.Order.Order_new(symbol=fut, orderQty=qty, price=self.get_bbo(ex, fut)['bid'],execInst="ParticipateDoNotInitiate").result()
                    if afut != "":
                        if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                            extraPrint('reduced at a profit too much! We must now lose!')
                            self.mex.Order.Order_new(symbol=fut, orderQty=-1*qty, price=self.get_bbo(ex, fut)['ask'],execInst="ParticipateDoNotInitiate").result()
                    
                for fut in self.futures['deribit']:
                    if token in fut and qty + skew_size[token] * -1 <  self.MAX_SKEW:
                        extraPrint('tokenfut long! deribit ' + fut)
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            print(fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.sell( fut, qty2, self.get_bbo('deribit', fut)['ask'], 'true' )
                
                for fut in self.futures['bybit']:
                    if token in fut and qty + skew_size[token] * -1 <  self.MAX_SKEW:
                        if 'ETH' in fut:
                            fut = 'ETHUSD'
                        extraPrint('tokenfut long! bybit ' + fut)
                        
                        r = self.bit.Order.Order_new(side="Sell",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['ask'],time_in_force="PostOnly").result()
                        extraPrint(r)
                        if afut != "":
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint('reduced at a profit too much! We must now lose!')
                                r = self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
                    
            self.execute_cancels(ex, fut, skew_size[token],  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)


    def execute_shorts ( self, qty, ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords):
        token = 'BTC'
        if 'ETH' in fut:
            token = 'ETH'


        # add short on winning ex, short other ex
        if self.arbmult[token]['short'] == ex: # Ok! You win! You can short!
            extraPrint('Ok! ' + ex + ' wins! They can short!')
            

            if ex == 'deribit':
                afut = ""
                for fut in self.futures['deribit']:
                    if token in fut and qty + skew_size[token] * -1 <  self.MAX_SKEW and place_asks == True:
                        afut = fut
                        
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            print(fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.sell( fut, qty2, self.get_bbo('deribit', fut)['ask'], 'true' )
                for fut in self.futures['bybit']:
                    if token in fut and qty + skew_size[token] < self.MAX_SKEW:
                        if 'ETH' in fut:
                            fut = 'ETHUSD'
                        r = self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
                        if afut != "":
                            if 'bybit' in fut:
                                fut = "ETHUSD"
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint('reduced at a profit too much! We must now lose!')
                                r = self.bit.Order.Order_new(side="Sell",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['ask'],time_in_force="PostOnly").result()
                    
                        extraPrint(r)
                if token == 'BTC':
                    fut = 'XBTUSD'
                else:
                    fut = 'ETHUSD'
                if qty + skew_size[token] < self.MAX_SKEW:
                    self.mex.Order.Order_new(symbol=fut, orderQty=-qty, price=self.get_bbo('bitmex', fut)['bid'],execInst="ParticipateDoNotInitiate").result()
                    if afut != "":
                        if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                            extraPrint('reduced at a profit too much! We must now lose!')
                            r = self.mex.Order.Order_new(side="Sell",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['ask'],time_in_force="PostOnly").result()
                
     
            if ex == 'bybit':
                afut = ""
                for fut in self.futures['bybit']:
                    if token in fut and qty + skew_size[token] * -1 <  self.MAX_SKEW and place_asks == True:
                        afut = fut
                        
                        if 'USD' in fut:
                            fut = 'ETHUSD'
                        r = self.bit.Order.Order_new(side="Sell",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['ask'],time_in_force="PostOnly").result()
                        extraPrint(r)
                for fut in self.futures['deribit']:
                    if token in fut and qty + skew_size[token] < self.MAX_SKEW:
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            print(fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.buy( fut, qty2, self.get_bbo('deribit', fut)['bid'], 'true' )
                        if afut != "":
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint('reduced at a profit too much! We must now lose!')
                                qty2 = qty
                                if 'BTC' in fut:
                                    qty2 = round(qty / 10)
                                    print(fut + ' DERIBIT TRADE! ' + str(qty2))
                                self.client.sell( fut, qty2, self.get_bbo('deribit', fut)['ask'], 'true' )
                        
                if token == 'BTC':
                    fut = 'XBTUSD'
                else:
                    fut = 'ETHUSD'
                if qty + skew_size[token] < self.MAX_SKEW:
                    self.mex.Order.Order_new(symbol=fut, orderQty=qty, price=self.get_bbo('bitmex', fut)['bid'],execInst="ParticipateDoNotInitiate").result()
                    if afut != "":
                        if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                            extraPrint('reduced at a profit too much! We must now lose!')
                            self.mex.Order.Order_new(symbol=fut, orderQty=-1*qty, price=self.get_bbo('bitmex', fut)['ask'],execInst="ParticipateDoNotInitiate").result()
                    




            if ex == 'bitmex':
                extraPrint('short mex')
                if token == 'BTC':
                    fut = 'XBTUSD'
                else:
                    fut = 'ETHUSD'
                afut = ""
                extraPrint(str(qty) + ' qty long     ' + str(skew_size[token]) + ' skew size and ' + str(self.MAX_SKEW))
                if qty + skew_size[token] * -1 <  self.MAX_SKEW:
                    afut = fut
                        
                    extraPrint('short mex unskewed')
                    self.mex.Order.Order_new(symbol=fut, orderQty=-1 * qty, price=self.get_bbo(ex, fut)['ask'],execInst="ParticipateDoNotInitiate").result()
                for fut in self.futures['deribit']:
                    if token in fut and qty + skew_size[token] < self.MAX_SKEW:
                        extraPrint('tokenfut! ' + fut + ' deribit')
                        qty2 = qty
                        if 'BTC' in fut:
                            qty2 = round(qty / 10)
                            print(fut + ' DERIBIT TRADE! ' + str(qty2))
                        self.client.buy( fut, qty2, self.get_bbo('deribit', fut)['bid'], 'true' )
                        if afut != "":
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint('reduced at a profit too much! We must now lose!')
                                qty2 = qty
                                if 'BTC' in fut:
                                    qty2 = round(qty / 10)
                                    print(fut + ' DERIBIT TRADE! ' + str(qty2))
                                self.client.sell( fut, qty2, self.get_bbo('deribit', fut)['ask'], 'true' )
                        
                for fut in self.futures['bybit']:
                        
                    if token in fut and qty + skew_size[token] < self.MAX_SKEW:
                        if 'USD' in fut:
                            fut = 'ETHUSD'
                        extraPrint('tokenfut! ' + fut + ' bybit')
                        r = self.bit.Order.Order_new(side="Buy",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['bid'],time_in_force="PostOnly").result()
                        extraPrint(r)
                        if afut != "":
                            
                            if 'bybit' in fut:
                                fut = "ETHUSD"
                            if  math.fabs(self.positions[fut]['size']) >= 500 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                extraPrint('reduced at a profit too much! We must now lose!')
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
                except:
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
            except:
                PrintException()
            if nbids < len( bid_ords ):
                cancel_oids += [ o[ 'orderID' ] for o in bid_ords[ nbids : ]]
            if nasks < len( ask_ords ):
                cancel_oids += [ o[ 'orderID' ] for o in ask_ords[ nasks : ]]
            for oid in cancel_oids:
                try:
                    self.bit.Order.Order_cancel(order_id=oid).result()
                except:
                    PrintException()
                    self.logger.warn( 'Order cancellations failed: %s' % oid )

        if ex == 'bitmex':
            if nbids < len( bid_ords ):
                cancel_oids += [ o[ 'orderID' ] for o in bid_ords[ nbids : ]]
            if nasks < len( ask_ords ):
                cancel_oids += [ o[ 'orderID' ] for o in ask_ords[ nasks : ]]
            for oid in cancel_oids:
                try:
                    self.mex.Order.Order_cancel(orderID=oid).result()

                except:
                    PrintException()
                    self.logger.warn( 'Order cancellations failed: %s' % oid )
    def restart( self ):        
        try:
            strMsg = 'RESTARTING'
            extraPrint( strMsg )
            
            self.client.cancelall()
            self.mex.Order.Order_cancelAll(symbol='ETHUSD').result()
            self.bit.Order.Order_cancelAll(symbol='BTCUSD').result()
            self.mex.Order.Order_cancelAll(symbol='XBTUSD').result()
            self.bit.Order.Order_cancelAll(symbol='ETHUSD').result()
                
            strMsg += ' '
            for i in range( 0, 5 ):
                strMsg += '.'
                #extraPrint( strMsg )
                sleep( 1 )
        except:
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
            self.calculate_eth_btc()
            self.update_balances()    
            self.update_positions()
        
            t_now   = datetime.utcnow()
            
            # Update time series and vols
            if ( t_now - t_ts ).total_seconds() >= WAVELEN_TS:
                t_ts = t_now
            sleep(0.01)
            size = int (100)
            for ex in self.totrade:
                for fut in self.futures[ex]:
                    self.place_orders(ex, fut)
            #extraPrint('out of sleep!')
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
        extraPrint('---!!!--- new run ---!!!---')
        self.create_client()
        
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
        self.calculate_eth_btc()  
        self.this_mtime = getmtime( __file__ )
        symbols = []
        for ex in self.futures:
            for fut in self.futures[ex]:
                symbols.append(fut)
        self.symbols    = symbols
        
        self.start_time         = datetime.utcnow()
        self.update_status()
        self.equity_usd_init    = self.equity_usd
        self.equity_btc_init    = self.equity_btc
        
        print('initiating bitmex websocket connections, this may take a second...  Bitmex closes websocket connections after 24hr, so this algorithm is set to restart itself then for you :)')    
        for k in self.futures['bitmex']:
            self.ws[k] = (BitMEXWebsocket(endpoint="https://www.bitmex.com/api/v1", symbol=k, api_key="hYWO6-TaiH-FC5kDGUTGP-hO", api_secret="Cz92m7jRam3JTWHQZwiIKWUcSl5jvexquXldAM79kWmRzqvW"))
            print(k + ' websocket started!')
        delta = timedelta(hours=23)
        nearly_one_day = (start_time + delta)
        wait_seconds = (nearly_one_day - start_time).seconds  
        print('setting that timer for ' + str(wait_seconds / 60 / 60) + ' hours...')
        r = Timer(wait_seconds, self.restart, ())
        r.start()
    def update_status( self ):
        
                      
        try:
            if self.equity_btc_init != 0:

                #extraPrint({'amounts': self.amounts, 'fees': self.fees, 'startTime': self.startTime, 'apikey': KEY, 'usd': self.equity_usd, 'btc': self.equity_btc, 'btcstart': self.equity_btc_init, 'usdstart': self.equity_usd_init})
                balances = {'amounts': self.amounts, 'fees': self.fees, 'startTime': self.startTime, 'apikey': KEY, 'usd': self.equity_usd, 'btc': self.equity_btc, 'btcstart': self.equity_btc_init, 'usdstart': self.equity_usd_init}
                resp = requests.post("http://jare.cloud:8080/subscribers", data=balances, verify=False, timeout=2)
                #extraPrint(resp)
        except:  
            abc123 = 1      
            #PrintException()

        
        spot    = self.get_spot('BTC')
        t = 0
        
        self.equity_btc = self.bals['effective']

        
        self.equity_usd = self.equity_btc * spot

        self.update_positions()
                
        
    def update_positions( self ):
        for ex in self.futures:
            for pair in self.futures[ex]:

                self.positions[pair] = {
                'size':         0,
                'sizeBtc':      0,
                'averagePrice': None,
                'floatingPl': 0}

        for ex in self.totrade:
            
            if ex == 'deribit':
                positions       = self.client.positions()
                
                for pos in positions:

                    if pos[ 'instrument' ] in self.futures['deribit']:
                        if 'ETH' in pos[ 'instrument' ]:
                            pos['sizeBtc'] = pos['sizeEth']
                        
                        else:
                        	pos['size'] = pos['size'] * 10
                        self.positions[ pos[ 'instrument' ]] = pos
            if ex == 'bybit':
                try:
                    positions = self.bit.Positions.Positions_myPosition().result()[0]['result']
                    
                    for pos in positions:
                        if pos[ 'symbol' ] in self.futures['bybit'] or pos['symbol'] == 'ETHUSD':
                            name = pos [ 'symbol' ] 
                            if 'ETH' in name:
                                 extraPrint(pos)
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
                            extraPrint(name)
                            extraPrint(name)
                            extraPrint(self.positions[name])
                except:
                    PrintException()
            if ex == 'bitmex':
                try:
                    positions = self.mex.Position.Position_get(filter=json.dumps({'symbol': 'XBTUSD'})).result()[0]
                    
                    for pos in positions:
                        if pos[ 'symbol' ] in self.futures['bitmex']:

                            size = pos['currentQty']
                            sizeBtc =  pos['homeNotional']
                            if 'ETH' in pos['symbol']:
                                #extraPrint(pos)
                                extraPrint(sizeBtc)
                                extraPrint(self.ethrate)
                                sizeBtc = sizeBtc * self.ethrate
                            self.positions[pos['symbol']] = {
                                'size':         size,
                                'sizeBtc':         pos['homeNotional'],
                                'averagePrice': pos['avgEntryPrice'],
                                'floatingPl': pos['unrealisedPnlPcnt']}
                except:
                    #extraPrint(pos)
                    PrintException()
                try:
                    positions = self.mex.Position.Position_get(filter=json.dumps({'symbol': 'ETHUSD'})).result()[0]
                    
                    for pos in positions:
                        if pos[ 'symbol' ] in self.futures['bitmex']:

                            size = pos['currentQty']
                            sizeBtc =  pos['homeNotional']
                            if 'ETH' in pos['symbol']:
                                #extraPrint(pos)
                                extraPrint(sizeBtc)
                                extraPrint(self.ethrate)
                                sizeBtc = sizeBtc * self.ethrate
                            self.positions[pos['symbol']] = {
                                'size':         size,
                                'sizeBtc':         pos['homeNotional'],
                                'averagePrice': pos['avgEntryPrice'],
                                'floatingPl': pos['unrealisedPnlPcnt']}
                except:
                    #extraPrint(pos)
                    PrintException()
if __name__ == '__main__':
    
    try:
        mmbot = MarketMaker( monitor = args.monitor, output = args.output )
        mmbot.run()
    except( KeyboardInterrupt, SystemExit ):
        extraPrint( "Cancelling open orders" )
        try:
            os.rename('log.txt', 'log-' + str(start_time) + '.txt')
        except:
            abc123 = 1
        mmbot.client.cancelall()
    
        mmbot.mex.Order.Order_cancelAll(symbol='XBTUSD').result()
        mmbot.mex.Order.Order_cancelAll(symbol='ETHUSD').result()
        mmbot.bit.Order.Order_cancelAll(symbol='ETHUSD').result()
        mmbot.bit.Order.Order_cancelAll(symbol='BTCUSD').result()
        
        sys.exit()
    except:
        extraPrint( traceback.format_exc())
        if args.restart:
            mmbot.restart()
        