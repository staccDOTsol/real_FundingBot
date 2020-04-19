# This code is for sample purposes only, comes as is and with no warranty or guarantee of performance
from bitmex_websocket import BitMEXWebsocket
import linecache
import sys
import threading
import time
from queue import Queue
import random, string
import datetime

from threading import Timer



def PrintException():
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    lineno = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno, f.f_globals)
    if 'ETHUSD' not in str(exc_obj):
        print ('EXCEPTION IN ({}, LINE {} "{}"): {}'.format(filename, lineno, line.strip(), exc_obj))


from collections    import OrderedDict
from os.path        import getmtime
from time           import sleep
from utils          import ( get_logger, lag, #print_dict, #print_dict_of_dicts, sort_by_key,
                             ticksize_ceil, ticksize_floor, ticksize_round )
import requests
import bitmex
import bybit
import json

import copy as cp
import argparse, logging, math, os, pathlib, sys, time, traceback
import ccxt
import random

try:
    from deribit_api    import RestClient
except ImportError:
    ###print("Please install the deribit_api pacakge", file=sys.stderr)
    ###print("    pip3 install deribit_api", file=sys.stderr)
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

ftxKEY     = "NqOlVRaqGM-XCX0cpf67UYxvT2tcB56SHlS-tlB-"#"VC4d7Pj1"
ftxSECRET  = "E-T228w_hSgnBQZHa8-cT1E-p0YyNqHkx9Y_8bdk"#"IB4VEP26OzTNUt4JhNILOW9aDuzctbGs_K6izxQG2dI"

binKEY     = "9mHe8kS2qvLMmOzSRxxI3NMTlkgCxJIx11EFfWD1CqnyN1GhhPpLl9o0WGGLIGwT"#"VC4d7Pj1"
binSECRET  = "tqj3y1hvr8u3Ni1ZwLkYdbJDV8AG0PZoSciW4pWzO6Ci8h6TAonvTcL8es5cmq2L"#"IB4VEP26OzTNUt4JhNILOW9aDuzctbGs_K6izxQG2dI"
URL     = 'https://www.deribit.com'

EWMA_WGT_LOOPTIME   = 2.5    
BP                  = 1e-4      # one basis point
BTC_SYMBOL          = 'btc'
CONTRACT_SIZE       = 10        # USD
COV_RETURN_CAP      = 100       # cap on variance for vol estimate
DECAY_POS_LIM       = 0.1       # position lim decay factor toward expiry
LOG_LEVEL           = logging.INFO
MIN_ORDER_SIZE      = 2
MAX_LAYERS          =  2        # max orders to layer the ob with on each side
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

        
        self.bals = {}
        self.ethrate = None
        self.rates = {}

        self.rates['binance'] = {}
        self.rates['ftx'] = {}

        self.maxqty = 1
        self.PCT_LIM_LONG = {}
        self.PCT_LIM_SHORT = {}
        self.LEV_LIM_LONG = {}
        self.LEV_LIM_SHORT = {}
        
        self.LEV_LIM_SHORT_OLD = 15
        self.LEV_LIM_LONG_OLD = 15
        self.PCT_LIM_LONG_OLD        = 30       # % position limit long

        self.PCT_LIM_SHORT_OLD       = 30
        self.equity_usd         = None
        self.equity_btc         = None
        self.equity_usd_init    = None
        self.equity_btc_init    = 0
        self.con_size           = float( CONTRACT_SIZE )
        self.arbmult = {}
        self.binance = None
        self.place_bids = {}
        self.place_asks = {}
        self.place_bids2 = {}
        self.place_asks2 = {}
        ##print("x-v0tiKJjj-" + self.randomword(15))
        self.ftx = None
        self.LEV = 1
        self.IM = 1
        self.ccxt = None
        self.ws = {}
        self.tradeids = []
        self.amounts = 0
        self.fees = 0
        self.startTime = int(time.time()*1000)
        self.totrade = ['ftx','binance']
        self.deltas             = OrderedDict()
        self.futures            = []
        self.active = []
        self.futures_prv        = OrderedDict()
        self.logger             = None
        self.mean_looptime      = 1
        self.monitor            = monitor
        self.output             = output or monitor
        self.positions          = {}
        self.spread_data        = None
        self.this_mtime         = None
        self.ts                 = None
        self.blockers = {}

        self.maybes = {}
        self.vols               = OrderedDict()
    def resetBlocker(self,token):
        print('unblock ' + token)
        self.blockers[token] = False

    def randomword(self, length):
       letters = string.ascii_lowercase
       return ''.join(random.choice(letters) for i in range(length))

    def compounding(self, intervals, amt, rate):
        while intervals > 0:
            intervals = intervals - 1
            amt = amt + (rate * amt)
        return amt
    def update_rates( self ):
        binance = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex").json()  
        for rate in binance:
            self.rates['binance'][rate['symbol'].replace('USDT', '')] = float(rate['lastFundingRate']) * 3
        ftx = requests.get("https://ftx.com/api/funding_rates").json()['result']
        doneFtx = {}
        for rate in ftx:
            doneFtx[rate['future'].replace('-PERP', '')] = False
        for rate in ftx:
            if rate['future'].replace('-PERP', '') != 'BTC':
                if doneFtx[rate['future'].replace('-PERP', '')] == False:
                    doneFtx[rate['future'].replace('-PERP', '')] = True
                    self.rates['ftx'][rate['future'].replace('-PERP', '')] = rate['rate'] * 24
        coins = {}
        coins['ftx'] = {}
        coins['binance'] = {}    
        
        for ex in self.rates:
            for rate in self.rates[ex]:
                coins[ex][rate] = self.rates[ex][rate]

        arbs = {}
        arbsf = {}
        for coin in coins:
            for fut in coins[coin]:
                arbs[fut] = {}
        for coin in coins:
            for fut in coins[coin]:
                arbs[fut][coin] = coins[coin][fut]
        ##print('arb now')
        arbmultold = self.arbmult
        self.arbmult = {}

        for token in self.positions:
            self.arbmult[token.split('-')[0]] = {}
        for token in self.positions:
            self.arbmult[token.split('-')[0]]['perc'] = 0
            self.arbmult[token.split('-')[0]]['arb'] = 0
        minArb = (0.0002 * 1 + 0.0002 * 1) / 2 * 2
        self.active = []
        ftxmarkets = requests.get("https://ftx.com/api/futures").json()['result']
        expis = []
        allfuts = []
        for market in ftxmarkets:
            if market['perpetual'] == False:
                if market['name'].split('-')[0] in arbs:
                    if 'MOVE' not in market['name']:
                        expis.append(market['name'].split('-')[1])
                        allfuts.append(market['name'])
        exps = {}
        for exp in expis:
            exps[exp] = 0
        for exp in expis:
            exps[exp] = exps[exp] + 1
        futlist = {}
        h = 0

        for exp in exps:
            if exps[exp] > h:
                h = exps[exp]
                w = exp
        for ftxfut in allfuts:
            if w in ftxfut:
                futlist[ftxfut.split('-')[0]] =  ftxfut
        #print(futlist)    
        
        for arb in arbs:
            
            if len(arbs[arb]) > 1:
                binance = arbs[arb]['binance']
                ftx = arbs[arb]['ftx']
                
                if (ftx < binance and ftx <=0 and binance >= 0 and ftx != binance) and (binance - ftx > minArb):        
                        self.arbmult[arb] = ({'coin': arb, 'long': 'ftx', 'short': 'binance', 'arb': binance - ftx})
                        self.futures.append(arb)
                        self.active.append(arb)
                elif (ftx > binance and ftx >=0 and binance <= 0 and ftx != binance) and (ftx - binance > minArb):
                        self.arbmult[arb] = ({'coin': arb, 'long': 'binance', 'short': 'ftx', 'arb': ftx - binance})
                        self.futures.append(arb)
                        self.active.append(arb)
                elif (ftx < 0 or ftx > 0 and math.fabs(ftx) > math.fabs(binance)) and math.fabs(ftx) > minArb:
                    if ftx > minArb:
                        self.arbmult[arb] = ({'coin': arb, 'long': futlist[arb], 'short': 'ftx', 'arb': ftx})
                        
                        self.futures.append(arb)
                        self.active.append(arb)
                    if ftx < -1 * minArb:
                        self.arbmult[arb] = ({'coin': arb, 'long': 'ftx', 'short': futlist[arb], 'arb': -1 * ftx})
                        self.futures.append(arb)
                        self.active.append(arb)
                elif (binance < 0 or binance > 0 and math.fabs(binance) > math.fabs(ftx)) and math.fabs(binance) > minArb:
                    if binance > minArb:
                        self.arbmult[arb] = ({'coin': arb, 'long': futlist[arb], 'short': 'binance', 'arb': binance})
                        self.futures.append(arb)
                        self.active.append(arb)
                    if binance < -1 * minArb:
                        self.arbmult[arb] = ({'coin': arb, 'long': 'binance', 'short': futlist[arb], 'arb': -1 * binance})
                        self.futures.append(arb)
                        self.active.append(arb)
                else:
                    print('loser ' + arb)
                    print(ftx - minArb)
                    print(binance - minArb)
        print(minArb)
        for ex123 in self.totrade:
            print(ex123)
            print(self.rates[ex123]['BCH'])
        print(self.arbmult)
        for fut in arbmultold:
            if fut not in self.arbmult:
                self.arbmult[fut] = arbmultold[fut]
                self.arbmult[fut]['arb'] = 0
        print(minArb) 
        print(self.arbmult)
        t = 0
        c = 0
        bal = self.bals['total']
        lev = 5
        exposure = bal * lev
        fees = (0.02/100 + (0.02*0.7)/100) * 2
        for arb in self.arbmult:
            if self.arbmult[arb]['arb'] > 0:
                t = t + self.arbmult[arb]['arb']

                c = c + 1
        tdaily = 0
        test = 0
        for arb in self.arbmult:
            self.arbmult[arb]['perc'] = round(self.arbmult[arb]['arb'] / t * 1000) / 1000 #* 1.41425
            self.arbmult[arb]['amt'] = round(exposure * self.arbmult[arb]['perc'] * 1000) / 1000
            self.arbmult[arb]['daily'] = round(self.arbmult[arb]['amt'] * self.arbmult[arb]['arb'] * 1000) / 1000
            
            self.arbmult[arb]['daily fees'] = self.arbmult[arb]['daily'] * fees
            self.arbmult[arb]['daily - fees'] = self.arbmult[arb]['daily'] - self.arbmult[arb]['daily fees']
            tdaily = tdaily + self.arbmult[arb]['daily - fees']
        returns = round((tdaily / bal) * 1000000) / 10000
        ##print('assuming $' + str(bal) + ' balance and ' + str(lev) + 'x leverage, and ' + str(fees * 100) + '% fees for a roundtrip as maker to buy/sell the exposure: ')
        ##print(self.arbmult)
        ##print('that would be ' + str(returns) + '% daily returns')
        annualret = (self.compounding(365, bal, returns / 100) * 1000) / 1000
        roe = ((((annualret / bal) * 1000) / 10) * 1000) / 1000
        apr = (returns * 365 * 1000) / 1000
        ##print('that is $' + str(annualret) + ' annualized, ' + str(roe) + '% ROE and ' + str(apr) + '% APR')
        for coin in self.positions:
            coin = coin.split('-')[0]
            self.PCT_LIM_LONG[coin]        = 15      # % position limit long
            self.LEV_LIM_LONG[coin] = 30
            self.LEV_LIM_SHORT[coin] = 30
            self.PCT_LIM_SHORT[coin]       = 15    # % position limit short
        for token in self.positions:
            token = token.split('-')[0]
            self.LEV_LIM_LONG[token] = self.LEV_LIM_LONG[token] * self.arbmult[token]['perc'] 
            self.LEV_LIM_SHORT[token] = self.LEV_LIM_SHORT[token] * self.arbmult[token]['perc'] 
            self.PCT_LIM_SHORT[token]  = self.PCT_LIM_SHORT[token] * self.arbmult[token]['perc'] 
            self.PCT_LIM_LONG[token]  = self.PCT_LIM_LONG[token] * self.arbmult[token]['perc'] 
        for coin in self.futures:
            coin = coin.split('-')[0]
            self.PCT_LIM_LONG[coin]        = 15      # % position limit long
            self.LEV_LIM_LONG[coin] = 30
            self.LEV_LIM_SHORT[coin] = 30
            self.PCT_LIM_SHORT[coin]       = 15    # % position limit short
        for token in self.futures:
            token = token.split('-')[0]
            self.LEV_LIM_LONG[token] = self.LEV_LIM_LONG[token] * self.arbmult[token]['perc'] 
            self.LEV_LIM_SHORT[token] = self.LEV_LIM_SHORT[token] * self.arbmult[token]['perc'] 
            self.PCT_LIM_SHORT[token]  = self.PCT_LIM_SHORT[token] * self.arbmult[token]['perc'] 
            self.PCT_LIM_LONG[token]  = self.PCT_LIM_LONG[token] * self.arbmult[token]['perc'] 
        #0.0011
        #119068
        print(self.LEV_LIM_SHORT)
    def update_balances( self ):
        
        bal2 = self.ftx.fetchBalance()
        bal = bal2[ 'USDT' ] [ 'total' ]
        marginftx = 0.1
        marginbinance = 0.1
        
        if self.ftx.privateGetAccount()['result']['marginFraction'] is not None:
            marginftx = (1 / self.ftx.privateGetAccount()['result']['marginFraction']) 
            #print(marginftx)

        ##print('bals')
        self.bals['ftx'] = bal
        ##print(bal)
        
        #if bal['info']['totalInitialMargin'] is not None:
           # marginbinance = float(bal['info']['totalInitialMargin']) / float(bal['info'][ 'totalMarginBalance' ]) * 100
            ##print(marginbinance)
        #if marginftx != 0.1 and marginbinance != 0.1:
        self.IM = marginftx / 2 #(marginbinance + marginftx) / 2
        self.LEV = self.IM * 2
        bal = self.binance.fetchBalance()
        bal = bal['info'] [ 'totalMarginBalance' ]
        self.bals['binance'] = bal
        t = 0
        ##print(bal)
        ##print(self.bals['binance'])
        self.bals['total'] = 0
        for bal in self.bals:
            t = t + float(self.bals[bal])
        self.bals['total'] = t
        ###print('balances')
        ###print(self.bals)
    def create_client( self ):
        self.ftx     = ccxt.ftx({
            'enableRateLimit': True,
            'apiKey': ftxKEY,
            'secret': ftxSECRET,
        })
        self.binance     = ccxt.binance({
            'enableRateLimit': True,
            'apiKey': binKEY,
            'secret': binSECRET,
            "options":{"defaultMarket":"futures"},
            'urls': {'api': {
                                     'public': 'https://fapi.binance.com/fapi/v1',
                                     'private': 'https://fapi.binance.com/fapi/v1',},}
 })
       
    

    def get_eth( self ):
        r = requests.get('https://api.binance.com/api/v1/ticker/price?symbol=ETHUSDT').json()
        return float(r['price'])
    def get_bbo( self, exchange, contract ): # Get best b/o excluding own orders
        if exchange == 'binance':
            # Get orderbook
            ob      = self.binance.fetchOrderBook( contract + '/USDT' )
            bids    = ob[ 'bids' ]
            asks    = ob[ 'asks' ]
       
            best_bid = self.get_spot(contract)
            best_ask = best_bid
            try:
                best_bid    = bids[0][0]
                best_ask    = asks[0][0]
            except:
                PrintException()
            
        if exchange == 'ftx':
            ob      = self.ftx.fetchOrderBook( contract + '-PERP')
            bids    = ob[ 'bids' ]
            asks    = ob[ 'asks' ]
       
            best_bid = self.get_spot(contract)
            best_ask = best_bid
            try:
                best_bid    = bids[0][0]
                best_ask    = asks[0][0]
            except:
                PrintException()
            
                   
        return { 'bid': best_bid, 'ask': best_ask }
    
        
        
    def get_pct_delta( self ):         
        self.update_status()
        return sum( self.deltas.values()) / self.equity_btc

    
    def get_spot( self, contract ):
        r = requests.get('https://api.binance.com/api/v1/ticker/price?symbol=' + contract + 'USDT').json()
        return float(r['price'])
    
    def get_precision( self, ex, contract ):
        if 'binance' in ex:
            return self.futures[ contract ] ['info'] [ 'pricePrecision' ]

        else:
            return float(self.futures[ contract ]['precision'][ 'amount' ])
        
    
    def get_ticksize( self, ex, contract ):
        if 'binance' in ex:
            return self.futures[ contract ] ['info'] ['filters'] [ 0 ] [ 'tickSize' ]
        else:
            return float(self.futures[ contract ]['precision']['price' ])
        
    
    def output_status( self ):
        
        if not self.output:
            return None
        
        self.update_status()
        print( '\nPositions: ')
        t = 0
        a = 0
        te = 0
        ae = 0
        for pos in self.positions:
        
            a = a + math.fabs(self.positions[pos]['size'])
        
            t = t + self.positions[pos]['size'] 
            print(pos + ': ' + str( self.positions[pos]['size'] ))
            
        print('\nNet delta (exposure) USD: $' + str(t))
        ##print('Net delta (exposure) ETH: $' + str(te))
        print('Total absolute delta (IM exposure) USD: $' + str(a))
        ##print('Total absolute delta (IM exposure) ETH: $' + str(ae))
        ##print('Total absolute delta (IM exposure) combined: $' + str(ae + a))
        print('Actual initial margin across all accounts: ' + str(self.IM) + '% and leverage is ' + str(round(self.LEV * 1000)/1000) + 'x')
        print(' ')    
        now     = datetime.datetime.utcnow()
        days    = ( now - self.start_time ).total_seconds() / SECONDS_IN_DAY
        #print( '********************************************************************' )
        #print( 'Start Time:        %s' % self.start_time.strftime( '%Y-%m-%d %H:%M:%S' ))
        #print( 'Current Time:      %s' % now.strftime( '%Y-%m-%d %H:%M:%S' ))
        #print( 'Days:              %s' % round( days, 1 ))
        #print( 'Hours:             %s' % round( days * 24, 1 ))
        #print( 'Reference Spot Price BTC:        %s' % self.get_spot('BTC'))
        #print( 'Reference Spot Price ETH:        %s' % self.get_spot('ETH'))
        
        
        pnl_usd = self.equity_usd - self.equity_usd_init
        pnl_btc = self.equity_btc - self.equity_btc_init
        
        print( 'Equity ($):        %7.2f'   % self.equity_usd)
        print( 'P&L ($)            %7.2f'   % pnl_usd)
        print( 'Equity (BTC):      %7.4f'   % self.equity_btc)
        print( 'P&L (BTC)          %7.4f'   % pnl_btc)

        
        print( '' )

        
    def place_orders( self, ex, token ):
        ##print('place_orders')
        ##print(self.arbmult)
        up = 0
        if True:
            up = up + 1
            if up == 5:
                up = 0
                self.update_positions()
            if token in self.blockers:
                if self.blockers[token] == True:
                    print('blocked..return')
                    return
            ##print(token)
            if self.monitor:
                return None
            con_sz  = self.con_size        
             ## FIX THIS IN PROD
            bal_btc         = self.bals['total']
            ###print('yo place orders ' + ex + ': ' + token)
            
            spot            = self.get_spot('BTC')
            skew_size = {}

            skew_size[token] = 0
            nbids = 1
            nasks = 1
            
            self.place_bids[token] = True
            self.place_asks[token] = True
            #print(self.PCT_LIM_LONG)
            a = {}
            for pos in self.positions:
                a[pos.split('-')[0]] = 0
            
            for pos in self.positions:
                a[pos.split('-')[0]] = a[pos.split('-')[0]] + math.fabs(self.positions[pos]['size'])
            for pos in self.positions:
                #print(pos)
                #print(a[pos.split('-')[0]])
                # ((158 / 100) / 4 * 1000)/10*4)=
                # ((30/1) / 15) * 1000) / 10=
                #print((((a[pos.split('-')[0]] / self.equity_usd) / self.LEV_LIM_SHORT[pos.split('-')[0]] * 1000 ) / 10 * len(self.active)))
                if self.LEV_LIM_SHORT[pos.split('-')[0]] == 0:
                    self.place_asks[pos.split('-')[0]] = False
                elif (((a[pos.split('-')[0]] / self.equity_usd) / self.LEV_LIM_SHORT[pos.split('-')[0]] * 1000 ) / 10  * len(self.active)) > 100:
                    self.place_asks[pos.split('-')[0]]= False
                    nasks = 0
                
                if self.LEV_LIM_LONG[pos.split('-')[0]] == 0:
                    self.place_bids[pos.split('-')[0]] = False
                elif (((a[pos.split('-')[0]] / self.equity_usd) / self.LEV_LIM_LONG[pos.split('-')[0]] * 1000 ) / 10  * len(self.active)) > 100:
                    self.place_bids[pos.split('-')[0]] = False
                    nbids = 0

            
            print(self.place_bids)
            min_order_size_btc = MIN_ORDER_SIZE 
            # 18 / (7000) 0.02571428571428571428571428571429
            # 22 / (7000) 0.00314285714285714285714285714286
            ###print('qty of bal: ' + str(PCT_QTY_BASE  * bal_btc))
            ###print(str(PCT_QTY_BASE  * bal_btc * spot) + '$')
            bbo     = self.get_bbo( ex, token )
            qtybtc  = float(max( PCT_QTY_BASE  * (bal_btc / spot), (min_order_size_btc / spot)))
            ###print('qty $: ' + str(qtybtc * spot))
            ###print('divided: ' + str(pos_LIM_SHORT[token] / qtybtc))
            ##print('place_x2L ' + ex + '-' + token)
            ##print(self.place_bids[token])
            ##print(self.place_asks[token])

        

            ###print('token: ' + token)    
            eps         = 0.0001 * 0.5
            riskfac     = math.exp( eps )

            
            bid_mkt = bbo[ 'bid' ]
            ask_mkt = bbo[ 'ask' ]
            
            cancel_oids = []
            bid_ords = ords  = ask_ords = []
            if ex == 'binance':
                try:
                    ords        = self.binance.fetchOpenOrders( token + '/USDT' )
                    bid_ords    = [ o for o in ords if o ['info'] [ 'side' ] == 'buy'  ]
                    ask_ords    = [ o for o in ords if o ['info'] [ 'side' ] == 'sell' ]

                except Exception as e:
                    PrintException()#PrintException()
            if ex == 'ftx':
                try:
                    ords        = self.ftx.fetchOpenOrders( token + '-PERP' )
                    bid_ords    = [ o for o in ords if o ['info'] [ 'side' ] == 'buy'  ]
                    ask_ords    = [ o for o in ords if o ['info'] [ 'side' ] == 'sell' ]

                except Exception as e:
                    PrintException()#PrintException()
           
            asks = []
            bids = []
            len_bid_ords    = min( len( bid_ords ), nbids )
            len_ask_ords    = min( len( ask_ords ), nasks )
            if self.place_bids[token]:      
                bids.append(bid_mkt)
            if self.place_asks[token]:
                asks.append(ask_mkt)
           
            ###print(self.place_asks[token])
            self.execute_arb (token, ex, token, skew_size, nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords )    


    def execute_arb ( self, token, ex, fut, skew_size,  nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords):
        fut = token
        print(fut)
        try:
            prc = self.get_bbo(ex, fut)['ask']
        except Exception as e:
            print(e)
            print('no bid, returning')
            return
        if prc > 5000:
            print('prc too high, returning')
            return
        #print('token token ' + fut)
        for ex2 in self.totrade:
            skew_size[token] = skew_size[token] + self.positions[fut + '-' + ex2]['size'] 
            #print('skew_size[token]: ' + str(skew_size[token]))
        
        i = 0
                    ##BTC     ##USD                   
        qty = (( qtybtc * self.get_spot('BTC')) / self.get_bbo(ex, fut)['ask'])
        if qty < 0.001:
            qty = 0.001
        self.MAX_SKEW = qty * prc * 1.1
        c = 1
        for block in self.blockers:
            if self.blockers[block] == True:
                c = c * 1.25

        qty = qty * c
        self.MAX_SKEW = self.MAX_SKEW * c
        print('qty: ' + fut + ': ' + str(qty))
        #qty = int(qty)

        #print('skew_size[token]: ' + str(skew_size[token]))
        #print('MAX SKEW ' + str(self.MAX_SKEW))
        #print('qty ' + str(qty))
        #print('calc ' +str( qty * prc + skew_size[token] ))
        #print(self.arbmult[fut])
        #print(self.place_asks)
        #print(self.place_bids)
        #print(self.PCT_LIM_LONG)
        #print(self.PCT_LIM_SHORT)
        
            #print('greater 15 ' + fut + ' and bids/asks false')
            #print(self.arbmult[fut])
            #print(self.place_asks)
            #print(self.place_bids)
            #print(self.PCT_LIM_LONG)
            #print(self.PCT_LIM_SHORT)
        gogo = False
        print('blockers')
        print(self.blockers)
        if token in self.blockers:
            if self.blockers[token] == False:
                gogo = True

        else:
            gogo = True
        if gogo == True:
            if self.positions[fut + '-binance']['size'] > self.MAX_SKEW * 2 and self.place_bids[token] == False and self.place_asks[token] == False:
                self.binance.createOrder(  fut + '/USDT', "Limit", 'sell', qty, self.get_bbo('binance', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                print('sell bin, return')
                
            if self.positions[fut + '-binance']['size'] < -1 * self.MAX_SKEW * 2 and self.place_bids[token] == False and self.place_asks[token] == False:
                self.binance.createOrder(  fut + '/USDT', "Limit", 'buy', qty, self.get_bbo('binance', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                print('buy bin, return')
                
            if self.positions[fut + '-ftx']['size'] > self.MAX_SKEW * 2 and self.place_bids[token] == False and self.place_asks[token] == False:
                self.ftx.createOrder(  fut + '-PERP', "limit", 'sell', qty, self.get_bbo('ftx', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                print('sell ftx, return')
                
            if self.positions[fut + '-ftx']['size'] < -1 * self.MAX_SKEW * 2 and self.place_bids[token] == False and self.place_asks[token] == False:
                self.ftx.createOrder(  fut + '-PERP', "limit", 'buy', qty, self.get_bbo('ftx', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                print('buy ftx, return')
                
            if self.place_asks[token] == False and self.place_bids[token] == False and (math.fabs(self.positions[fut+'-binance']['size']) > 15 or math.fabs(self.positions[fut+'-ftx']['size']) > 15):
                

                self.maybes[token] = True
                

        # bid edit
        try:
            try: 
                oid = bid_ords[ i ]['info'][ 'id' ]
            except:
                oid = bid_ords[ i ][ 'id' ]
            try:
                if ex == 'binance':
                    self.binance.editOrder( oid, qty, prc )
                if ex == 'ftx':
                    side = bid_ords[ i ][ 'side' ]
                    self.ftx.editOrder( oid, fut + '-PERP', 'limit', side, qty, prc, {'leverage': 10})
            except:
                abc=123#PrintException()
        except:
                abc=123#PrintException()
        # ask edit
        try:
            prc = self.get_bbo(ex, fut)['bid']
        except:
            print('no ask, returning')
            return
        try:
            try: 
                oid = ask_ords[ i ]['info'][ 'id' ]
            except:
                oid = ask_ords[ i ][ 'id' ]
            try:
                if ex == 'binance':
                    self.binance.editOrder( oid, qty, prc )
                if ex == 'ftx':
                    side = ask_ords[ i ][ 'side' ]
                    self.ftx.editOrder( oid, fut + '-PERP', 'limit', side, qty, prc, {'leverage': 10})
            except:
                abc=123#PrintException()
        except:
            abc=123#PrintException()
        
        
            
        if 'long' in self.arbmult[token]:
            self.execute_longs ( prc, token, qty, ex, fut, skew_size,  nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords)
            self.execute_shorts ( prc, token, qty, ex, fut, skew_size,  nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords)

    def execute_longs ( self, prc, token, qty, ex, fut, skew_size,  nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords):
        delta = datetime.timedelta(hours=1)
        now = datetime.datetime.now()
        next_hour = (now + delta).replace(microsecond=0, second=0, minute=2)
        fut = token
        wait_seconds = (next_hour - now).seconds  
         
        try:
        # Reduce
            reducing = False
            if self.positions[fut + '-' + ex]['floatingPl'] > 0.01 and math.fabs(self.positions[fut + '-' + ex]['size']) > 150:
                #print(fut + ' in profit! Gonna reduce!')
        
                reducing = True
        
       
            
        
        
        # short Reduce
                
                if self.positions[fut + '-' + ex]['size'] > 0:
                    if ex == 'binance':
                    # deribit
                        print('bin 1')
                        self.binance.createOrder(  fut + '/USDT', "Limit", 'sell', qty, self.get_bbo('binance', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                        self.ftx.createOrder(  fut + '-PERP', "limit", 'buy', qty / 3, self.get_bbo('ftx', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})    
                        
                    if ex == 'ftx':
                    # bybit
                        print('ftx 1')
                        self.ftx.createOrder(  fut + '-PERP', "limit", 'sell', qty, self.get_bbo('ftx', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})    
                        self.binance.createOrder(  fut + '/USDT', "Limit", 'buy', qty / 3, self.get_bbo('binance', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                        
                    
        # long reduce
        
                else:
                    if ex == 'binance':
                    # deribit
                        print('bin 2')
                        self.binance.createOrder(  fut + '/USDT', "Limit", 'buy', qty, self.get_bbo('binance', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                        self.ftx.createOrder(  fut + '-PERP', "limit", 'sell', qty / 3, self.get_bbo('ftx', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})    
                        
                    if ex == 'ftx':
                    # bybit
                        print('ftx 2')
                        self.ftx.createOrder(  fut + '-PERP', "limit", 'buy', qty, self.get_bbo('ftx', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})    
                        self.binance.createOrder(  fut + '/USDT', "Limit", 'sell', qty / 3, self.get_bbo('binance', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                        
            print(ex)
            # long fut short ex?

            if self.arbmult[token]['long'] not in self.totrade:
                print('long fut ' + self.arbmult[token]['long'] + ' short ex: ' + self.arbmult[token]['short'])
                if ex == 'binance' and self.arbmult[token]['short'] == 'binance':
                    afut = ""
                    print(self.MAX_SKEW)
                    print(qty * prc + skew_size[token])

                    if (reducing == False and token in fut and  qty * prc + (skew_size[token]) > -1 *  self.MAX_SKEW  and self.place_asks[token] == True) and (math.fabs(self.positions[token + '-ftx']['size']) / math.fabs(self.positions[token + '-binance']['size']) > 0.75):
                        afut = fut
                        if fut in self.maybes :
                            if self.maybes[fut] == True and self.place_bids[token] == True:
                                self.blockers[fut] = True
                                self.maybes[fut] = False
                                r = Timer(wait_seconds, self.resetBlocker, (token))
                                print('block ' + token + ' for ' + str(wait_seconds))
                                r.start()    
                                
                        print('binbin sell a fut')
                        gogo = False
                        if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                        else: 
                            gogo = True    
                        if gogo == True: 
                            self.binance.createOrder(  fut + '/USDT', "Limit", 'sell', qty, self.get_bbo('binance', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                        
                    print(qty * prc + -1 * skew_size[token])
                    if  token in fut and  qty * prc + (skew_size[token]) <  self.MAX_SKEW and self.place_bids[token] == True and math.fabs(self.positions[token + '-ftx']['size']) / math.fabs(self.positions[token + '-binance']['size']) < 1.33:
                         gogo = False
                         if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                         else: 
                            gogo = True    
                         if gogo == True:
                            print('ftxftx fut buy')
                            self.ftx.createOrder( self.arbmult[token]['short'], "limit", 'buy', qty, self.get_bbo('ftx', self.arbmult[token]['short'])['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)}   )
                             
                #print(str(self.PCT_LIM_LONG[token]) + ' Ok! ' + ex + ' wins! They can long! ' + str(self.place_bids[token]) + ' ' + str(self.IM))
                if ex == 'ftx' and self.arbmult[token]['short'] == 'ftx':
                    afut = ""
                    print(self.MAX_SKEW)
                    print(qty * prc + skew_size[token])
                    if (reducing == False and token in fut and  qty * prc + (skew_size[token]) > -1 * self.MAX_SKEW  and self.place_asks[token] == True) and (math.fabs(self.positions[token + '-ftx']['size']) / math.fabs(self.positions[token + '-binance']['size']) > 0.75):
                        afut = fut
                        if fut in self.maybes :
                            if self.maybes[fut] == True and self.place_bids[token] == True:
                                self.blockers[fut] = True
                                self.maybes[fut] = False
                                r = Timer(wait_seconds, self.resetBlocker, (token))
                                print('block ' + token + ' for ' + str(wait_seconds))
                                r.start()    
                                
                        print('ftx buy')
                        gogo = False
                        if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                        else: 
                            gogo = True    
                        if gogo == True: 
                            self.ftx.createOrder(  fut + '-PERP', "limit", 'sell', qty, self.get_bbo('ftx', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)}   )
                            
                    
                    print(qty * prc + -1 * skew_size[token])
                    if  token in fut and  qty * prc + (skew_size[token]) <  self.MAX_SKEW and self.place_bids[token] == True and math.fabs(self.positions[token + '-ftx']['size']) / math.fabs(self.positions[token + '-binance']['size']) < 1.33:
                         gogo = False
                         if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                         else: 
                            gogo = True    
                         if gogo == True:
                            print('ftxftx fut buy')
                            self.ftx.createOrder( self.arbmult[token]['short'], "limit", 'buy', qty, self.get_bbo('ftx', self.arbmult[token]['short'])['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)}   )
            # short fut long ex?
            if self.arbmult[token]['short'] not in self.totrade:
                print('short fut ' + self.arbmult[token]['short'] + ' long ex: ' + self.arbmult[token]['long'])
                if ex == 'binance' and self.arbmult[token]['long'] == 'binance':
                    afut = ""
                    print(self.MAX_SKEW)
                    print(qty * prc + skew_size[token])

                    if (reducing == False and token in fut and  qty * prc + (skew_size[token]) <  self.MAX_SKEW  and self.place_bids[token] == True) and (math.fabs(self.positions[token + '-ftx']['size']) / math.fabs(self.positions[token + '-binance']['size']) < 1.33):
                        afut = fut
                        if fut in self.maybes :
                            if self.maybes[fut] == True and self.place_bids[token] == True:
                                self.blockers[fut] = True
                                self.maybes[fut] = False
                                r = Timer(wait_seconds, self.resetBlocker, (token))
                                print('block ' + token + ' for ' + str(wait_seconds))
                                r.start()    
                                
                        print('binbin buy a fut')
                        gogo = False
                        if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                        else: 
                            gogo = True    
                        if gogo == True: 
                            self.binance.createOrder(  fut + '/USDT', "Limit", 'buy', qty, self.get_bbo('binance', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                        
                    print(qty * prc + -1 * skew_size[token])
                    if  token in fut and self.place_asks[token] == True and  qty * prc + (skew_size[token]) > -1 *  self.MAX_SKEWe and math.fabs(self.positions[token + '-ftx']['size']) / math.fabs(self.positions[token + '-binance']['size']) > 0.75:
                         gogo = False
                         if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                         else: 
                            gogo = True    
                         if gogo == True:
                            print('ftxftx fut sell')
                            self.ftx.createOrder( self.arbmult[token]['short'], "limit", 'sell', qty, self.get_bbo('ftx', self.arbmult[token]['short'])['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)}   )
                             
                #print(str(self.PCT_LIM_LONG[token]) + ' Ok! ' + ex + ' wins! They can long! ' + str(self.place_bids[token]) + ' ' + str(self.IM))
                if ex == 'ftx' and self.arbmult[token]['long'] == 'ftx':
                    afut = ""
                    print(self.MAX_SKEW)
                    print(qty * prc + skew_size[token])
                    if (reducing == False and token in fut and  qty * prc + (skew_size[token]) <  self.MAX_SKEW  and self.place_bids[token] == True) and (math.fabs(self.positions[token + '-ftx']['size']) / math.fabs(self.positions[token + '-binance']['size']) < 1.33):
                        afut = fut
                        if fut in self.maybes :
                            if self.maybes[fut] == True and self.place_bids[token] == True:
                                self.blockers[fut] = True
                                self.maybes[fut] = False
                                r = Timer(wait_seconds, self.resetBlocker, (token))
                                print('block ' + token + ' for ' + str(wait_seconds))
                                r.start()    
                                
                        print('ftx buy')
                        gogo = False
                        if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                        else: 
                            gogo = True    
                        if gogo == True: 
                            self.ftx.createOrder(  fut + '-PERP', "limit", 'buy', qty, self.get_bbo('ftx', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)}   )
                            
                    
                    print(qty * prc + -1 * skew_size[token])
                    if  token in fut and self.place_asks[token] == True and  qty * prc + (skew_size[token]) > -1 *  self.MAX_SKEW and math.fabs(self.positions[token + '-ftx']['size']) / math.fabs(self.positions[token + '-binance']['size']) > 0.75:
                         gogo = False
                         if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                         else: 
                            gogo = True    
                         if gogo == True:
                            print('ftxftx fut sell')
                            self.ftx.createOrder( self.arbmult[token]['short'], "limit", 'sell', qty, self.get_bbo('ftx', self.arbmult[token]['short'])['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)}   )
                               
        # Long add on winning ex, short other ex - or rather 
            if ex == self.arbmult[token]['long']:     
                #print(str(self.PCT_LIM_LONG[token]) + ' Ok! ' + ex + ' wins! They can long! ' + str(self.place_bids[token]) + ' ' + str(self.IM))
                if ex == 'binance':
                    afut = ""
                    print(self.MAX_SKEW)
                    print(qty * prc + skew_size[token])

                    if (reducing == False and token in fut and  qty * prc + (skew_size[token]) <  self.MAX_SKEW  and self.place_bids[token] == True) and (math.fabs(self.positions[token + '-ftx']['size']) / math.fabs(self.positions[token + '-binance']['size']) < 1.33):
                        afut = fut
                        if fut in self.maybes :
                            if self.maybes[fut] == True and self.place_bids[token] == True:
                                self.blockers[fut] = True
                                self.maybes[fut] = False
                                r = Timer(wait_seconds, self.resetBlocker, (token))
                                print('block ' + token + ' for ' + str(wait_seconds))
                                r.start()    
                                
                        print('binbin buy')
                        gogo = False
                        if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                        else: 
                            gogo = True    
                        if gogo == True: 
                            self.binance.createOrder(  fut + '/USDT', "Limit", 'buy', qty, self.get_bbo('binance', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                        
                    print(qty * prc + -1 * skew_size[token])
                    if  token in fut and self.place_asks[token] == True and  qty * prc + (skew_size[token]) > -1 *  self.MAX_SKEW and math.fabs(self.positions[token + '-ftx']['size']) / math.fabs(self.positions[token + '-binance']['size']) > 0.75:
                         gogo = False
                         if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                         else: 
                            gogo = True    
                         if gogo == True:
                            print('ftxftx sell')
                            self.ftx.createOrder(  fut + '-PERP', "limit", 'sell', qty, self.get_bbo('ftx', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)}   )
                             
                #print(str(self.PCT_LIM_LONG[token]) + ' Ok! ' + ex + ' wins! They can long! ' + str(self.place_bids[token]) + ' ' + str(self.IM))
                if ex == 'ftx':
                    afut = ""
                    print(self.MAX_SKEW)
                    print(qty * prc + skew_size[token])
                    if (reducing == False and token in fut and  qty * prc + (skew_size[token]) <  self.MAX_SKEW  and self.place_bids[token] == True) and (math.fabs(self.positions[token + '-ftx']['size']) / math.fabs(self.positions[token + '-binance']['size']) < 1.33):
                        afut = fut
                        if fut in self.maybes :
                            if self.maybes[fut] == True and self.place_bids[token] == True:
                                self.blockers[fut] = True
                                self.maybes[fut] = False
                                r = Timer(wait_seconds, self.resetBlocker, (token))
                                print('block ' + token + ' for ' + str(wait_seconds))
                                r.start()    
                                
                        print('ftx buy')
                        gogo = False
                        if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                        else: 
                            gogo = True    
                        if gogo == True: 
                            self.ftx.createOrder(  fut + '-PERP', "limit", 'buy', qty, self.get_bbo('ftx', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)}   )
                            
                    
                    print(qty * prc + -1 * skew_size[token])
                    if  token in fut and self.place_asks[token] == True and  qty * prc + (skew_size[token]) > -1 *  self.MAX_SKEW and math.fabs(self.positions[token + '-ftx']['size']) / math.fabs(self.positions[token + '-binance']['size']) > 0.75:
                         gogo = False
                         if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                         else: 
                            gogo = True    
                         if gogo == True:
                            print('bin sell')
                            self.binance.createOrder(  fut + '/USDT', "Limit", 'sell', qty, self.get_bbo('binance', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)}) 
                                    
        except:
            PrintException()
            self.execute_cancels(ex, fut, skew_size,  nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords)


    def execute_shorts ( self, prc, token, qty, ex, fut, skew_size,  nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords):
        delta = datetime.timedelta(hours=1)
        now = datetime.datetime.now()
        next_hour = (now + delta).replace(microsecond=0, second=0, minute=7)

        self.execute_cancels(ex, fut, skew_size,  nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords)
        
    def cancelall(self, pair, ex ):
        if ex == 'binance':
            ords        = self.binance.fetchOpenOrders( pair + '/USDT' )
            
            for order in ords:
                ###print(order)
                oid = order ['info'] ['orderId']
               # ##print(order)
                try:
                    self.binance.cancelOrder( oid , pair + '/USDT' )
                except Exception as e:
                    print(e)
        if ex == 'ftx':
            ords        = self.ftx.fetchOpenOrders( pair + '-PERP')
            for order in ords:
                ###print(order)
                oid = order ['info'] ['id']
               # ##print(order)
                try:
                    self.ftx.cancelOrder( oid , pair )
                except Exception as e:
                    print(e)
    def execute_cancels(self, ex, fut, skew_size,  nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords):
        if ex == 'binance':
            if nbids < len( bid_ords ):
                if ex == 'binance':
                    cancel_oids += [ o['info'][ 'id' ] for o in bid_ords[ nbids : ]]
                if ex == 'ftx':
                    cancel_oids += [ o[ 'id' ] for o in bid_ords[ nbids : ]]
               
            if nasks < len( ask_ords ):
                if ex == 'binance':
                    #print(ask_ords[0])
                    cancel_oids += [ o['info'][ 'id' ] for o in ask_ords[ nasks : ]]
                if ex == 'ftx':
                    cancel_oids += [ o[ 'id' ] for o in ask_ords[ nasks : ]]
            for oid in cancel_oids:
                try:
                    self.binance.cancel( oid )
                except:
                    self.logger.warn( 'Order cancellations failed: %s' % oid )
        if ex == 'ftx':
            
            if nbids < len( bid_ords ):
                cancel_oids += [ o[ 'id' ] for o in bid_ords[ nbids : ]]
            if nasks < len( ask_ords ):
                cancel_oids += [ o[ 'id' ] for o in ask_ords[ nasks : ]]
            for oid in cancel_oids:
                try:
                    self.ftx.cancelOrder( oid, fut )
            
                except:
                    PrintException()
                    self.logger.warn( 'Order cancellations failed: %s' % oid )

    def restart( self ):        
        try:
            strMsg = 'RESTARTING'
            ##print( strMsg )
            
            for fut in self.futures:
                self.cancelall(fut, 'ftx')
            for fut in self.futures:
                self.cancelall(fut, 'binance')
            
            strMsg += ' '
            for i in range( 0, 5 ):
                strMsg += '.'
                ###print( strMsg )
                sleep( 1 )
        except:
            pass
        finally:
            os.execv( sys.executable, [ sys.executable ] + sys.argv )        
            
    


    def run( self ):
        
        self.run_first()
        self.output_status()
        ##print('run')    
        t_ts = t_out = t_loop = t_mtime = datetime.datetime.utcnow()

        while True:

            for fut in self.futures:
                self.cancelall(fut, 'ftx')
            for fut in self.futures:
                self.cancelall(fut, 'binance')
            self.update_rates()
            self.update_balances()    
            self.update_positions()
        
            t_now   = datetime.datetime.utcnow()
            
            # Update time series and vols
            for token in self.positions:
                token = token.split('-')[0]
                self.place_orders('binance', token)
                
                self.place_orders('ftx', token)
            self.update_positions()
            for token in self.futures:
                token = token.split('-')[0]
                self.place_orders('binance', token)
                
                self.place_orders('ftx', token)
            ###print('out of sleep!')
            #self.place_orders()

            
            self.output_status(); 
            
    def run_first( self ):
        
        self.create_client()
        self.update_balances()
        
        
                
        self.logger = get_logger( 'root', LOG_LEVEL )
        # Get all futures contracts
        
        self.update_rates() 
        
        for fut in self.futures:
            self.cancelall(fut, 'ftx')
        for fut in self.futures:
            self.cancelall(fut, 'binance')
        self.update_positions()  
        self.this_mtime = getmtime( __file__ )
        
        self.start_time         = datetime.datetime.utcnow()
        self.update_status()
        
        self.equity_usd_init    = self.equity_usd
        self.equity_btc_init    = self.equity_btc
        
    def update_status( self ):
        
                      
        
        spot    = self.get_spot('BTC')
        t = 0
        ##print('set bals')
        ##print(self.bals['total'])   
        self.equity_usd = self.bals['total']
        self.equity_btc = self.bals['total'] / spot

                
        
    def update_positions( self ):
        ##print('update_positions')
        for pair in self.futures:

                self.positions[pair + '-binance'] = {
                'size':         1,
                'sizeBtc':      0,
                'averagePrice': None,
                'floatingPl': 0}
                self.positions[pair + '-ftx'] = {
                'size':         2,
                'sizeBtc':      0,
                'averagePrice': None,
                'floatingPl': 0}

        for ex in self.totrade:
            
            if ex == 'binance':
                positions       = self.binance.fapiPrivateGetPositionRisk()
                ###print('lala')
                ###print(positions)
                ###print(self.futures)
                for pos in positions:
                    ###print('binance pos')
                    ###print(pos)
                    pos['symbol'] = pos['symbol'].replace('USDT', '').replace('USD', '')
                    pos['size'] = float(pos['positionAmt']) * self.get_spot(pos['symbol'])
                    #if pos['size'] == 0:
                    #    pos['size'] = 1
                    pos['floatingPl'] = float(pos['unRealizedProfit']) 
                    if pos['size'] != 0:
                        self.positions[ pos[ 'symbol' ] + '-binance'] = pos
            if ex == 'ftx':
                try:
                    positions       = self.ftx.privateGetPositions()['result']
                    ###print(self.futures)
                    spot = self.get_spot('BTC')
                    for pos in positions:
                        ###print('ftx pos')
                        
                        pos['future'] = pos['future'].replace('-PERP', '')
                        pos['floatingPl'] = pos['unrealizedPnl']
                        pos['size'] = float(pos['netSize']) * self.get_spot(pos['future'])
                        #if pos['size'] == 0:
                        #    pos['size'] = 2
                        if pos['size'] != 0:
                            self.positions[ pos[ 'future' ] + '-ftx'] = pos
                except:
                    PrintException()
                
if __name__ == '__main__':
    
    ##print('hello world')
    try:
        mmbot = MarketMaker( monitor = args.monitor, output = args.output )
        mmbot.run()
    except( KeyboardInterrupt, SystemExit ):
        ###print( "Cancelling open orders" )
        for fut in mmbot.futures:
            mmbot.cancelall(fut, 'ftx')
            mmbot.cancelall(fut, 'binance')
        
        sys.exit()
    except:
        print ( traceback.format_exc())
        if args.restart:
            mmbot.restart()
        