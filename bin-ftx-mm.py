# This code is for sample purposes only, comes as is and with no warranty or guarantee of performance
from bitmex_websocket import BitMEXWebsocket
import linecache
import sys
import threading
import time
from queue import Queue
import random, string

def PrintException():
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    lineno = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno, f.f_globals)
    print ('EXCEPTION IN ({}, LINE {} "{}"): {}'.format(filename, lineno, line.strip(), exc_obj))


from collections    import OrderedDict
from datetime       import datetime
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
    #print("Please install the deribit_api pacakge", file=sys.stderr)
    #print("    pip3 install deribit_api", file=sys.stderr)
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

ftxKEY     = "Zs9lCqYM_Qce9MsfZ7kP97lfXQ6yImU3-Ts-7RJk"#"VC4d7Pj1"
ftxSECRET  = "l3lrdUaWYpsNZ0ZtwRD4gSSUfoexk3CzEcLvPOWy"#"IB4VEP26OzTNUt4JhNILOW9aDuzctbGs_K6izxQG2dI"

binKEY     = "M9LOn9wdpCZUMOL5dQ1uShuBjf6yJX0619eqF15bjXOH8OCuCr8Hx0afz69JCrW8 "#"VC4d7Pj1"
binSECRET  = "3mlb8uEBRSZGw60wPsZcO5NVqpcpApD1oZkWOqgiRCSuvCXgYh0rukEiZjJNRZAZ"#"IB4VEP26OzTNUt4JhNILOW9aDuzctbGs_K6izxQG2dI"
URL     = 'https://www.deribit.com'

EWMA_WGT_LOOPTIME   = 2.5    
BP                  = 1e-4      # one basis point
BTC_SYMBOL          = 'btc'
CONTRACT_SIZE       = 10        # USD
COV_RETURN_CAP      = 100       # cap on variance for vol estimate
DECAY_POS_LIM       = 0.1       # position lim decay factor toward expiry
LOG_LEVEL           = logging.INFO
MIN_ORDER_SIZE      = 1
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
        
        self.LEV_LIM_SHORT_OLD = 3
        self.LEV_LIM_LONG_OLD = 3
        self.PCT_LIM_LONG_OLD        = 7       # % position limit long

        self.PCT_LIM_SHORT_OLD       = 7
        self.equity_usd         = None
        self.equity_btc         = None
        self.equity_usd_init    = None
        self.equity_btc_init    = 0
        self.con_size           = float( CONTRACT_SIZE )
        self.arbmult = {}
        self.binance = None
        self.place_bids = {}
        self.place_asks = {}
        print("x-GYswxDoF-" + self.randomword(20))
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
        
        for rate in ftx:
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
        print('arb now')
        for arb in arbs:
            
            if len(arbs[arb]) > 1:
                binance = arbs[arb]['binance']
                ftx = arbs[arb]['ftx']
                
                if ftx < 0 and binance < 0:
                    print('ftx and bin below 0')
                    print({'coin': arb, 'long': 'ftx', 'short': 'binance', 'arb': binance + ftx})
                if binance > 0 and ftx > 0:
                    print('ftx and bin above 0')
                    print({'coin': arb, 'long': 'ftx', 'short': 'binance', 'arb': binance + ftx})
                if ftx < binance and ftx <=0 and binance >= 0 and ftx != binance:
                    
                    self.arbmult[arb] = ({'coin': arb, 'long': 'ftx', 'short': 'binance', 'arb': binance - ftx})
                    self.futures.append(arb)
            
                if ftx > binance and ftx >=0 and binance <= 0 and ftx != binance:
                    self.arbmult[arb] = ({'coin': arb, 'long': 'binance', 'short': 'ftx', 'arb': ftx - binance})
                    self.futures.append(arb)
            
        t = 0
        c = 0
        bal = self.bals['total']
        lev = 5
        exposure = bal * lev
        fees = (0.02/100 + (0.02*0.7)/100) * 2
        for arb in self.arbmult:
            t = t + self.arbmult[arb]['arb']
            c = c + 1
        tdaily = 0
        test = 0
        for arb in self.arbmult:
            self.arbmult[arb]['perc'] = round(self.arbmult[arb]['arb'] / t * 1000) / 1000
            self.arbmult[arb]['amt'] = round(exposure * self.arbmult[arb]['perc'] * 1000) / 1000
            self.arbmult[arb]['daily'] = round(self.arbmult[arb]['amt'] * self.arbmult[arb]['arb'] * 1000) / 1000
            
            self.arbmult[arb]['daily fees'] = self.arbmult[arb]['daily'] * fees
            self.arbmult[arb]['daily - fees'] = self.arbmult[arb]['daily'] - self.arbmult[arb]['daily fees']
            tdaily = tdaily + self.arbmult[arb]['daily - fees']
        returns = round((tdaily / bal) * 1000000) / 10000
        print('assuming $' + str(bal) + ' balance and ' + str(lev) + 'x leverage, and ' + str(fees * 100) + '% fees for a roundtrip as maker to buy/sell the exposure: ')
        print(self.arbmult)
        print('that would be ' + str(returns) + '% daily returns')
        annualret = (self.compounding(365, bal, returns / 100) * 1000) / 1000
        roe = ((((annualret / bal) * 1000) / 10) * 1000) / 1000
        apr = (returns * 365 * 1000) / 1000
        print('that is $' + str(annualret) + ' annualized, ' + str(roe) + '% ROE and ' + str(apr) + '% APR')
        for coin in self.arbmult:
            self.PCT_LIM_LONG[coin]        = 7       # % position limit long
            self.LEV_LIM_LONG[coin] = 3
            self.LEV_LIM_SHORT[coin] = 3
            self.PCT_LIM_SHORT[coin]       = 7     # % position limit short
        for token in self.arbmult:
            self.LEV_LIM_LONG[token] = self.LEV_LIM_LONG[token] * self.arbmult[token]['perc']
            self.LEV_LIM_SHORT[token] = self.LEV_LIM_SHORT[token] * self.arbmult[token]['perc']
            self.PCT_LIM_SHORT[token]  = self.PCT_LIM_SHORT[token] * self.arbmult[token]['perc']
            self.PCT_LIM_LONG[token]  = self.PCT_LIM_LONG[token] * self.arbmult[token]['perc']
        #0.0011
        #119068
    def update_balances( self ):
        
        bal = self.ftx.fetchBalance()
        bal = bal[ 'USDT' ] [ 'total' ]
        print('bals')
        self.bals['ftx'] = bal
        print(bal)
        bal = self.binance.fetchBalance()[ 'info' ] [ 'totalMarginBalance' ]
        self.bals['binance'] = bal
        t = 0
        print(bal)
        print(self.bals['binance'])
        self.bals['total'] = 0
        for bal in self.bals:
            t = t + float(self.bals[bal])
        self.bals['total'] = t
        #print('balances')
        #print(self.bals)
    def create_client( self ):
        self.ftx     = ccxt.ftx({
            'apiKey': ftxKEY,
            'secret': ftxSECRET,
        })
        self.binance     = ccxt.binance({
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
        
        now     = datetime.utcnow()
        days    = ( now - self.start_time ).total_seconds() / SECONDS_IN_DAY
        print( '********************************************************************' )
        print( 'Start Time:        %s' % self.start_time.strftime( '%Y-%m-%d %H:%M:%S' ))
        print( 'Current Time:      %s' % now.strftime( '%Y-%m-%d %H:%M:%S' ))
        print( 'Days:              %s' % round( days, 1 ))
        print( 'Hours:             %s' % round( days * 24, 1 ))
        print( 'Reference Spot Price BTC:        %s' % self.get_spot('BTC'))
        print( 'Reference Spot Price ETH:        %s' % self.get_spot('ETH'))
        
        
        pnl_usd = self.equity_usd - self.equity_usd_init
        pnl_btc = self.equity_btc - self.equity_btc_init
        
        print( 'Equity ($):        %7.2f'   % self.equity_usd)
        print( 'P&L ($)            %7.2f'   % pnl_usd)
        print( 'Equity (BTC):      %7.4f'   % self.equity_btc)
        print( 'P&L (BTC)          %7.4f'   % pnl_btc)

        print( '\nPositions: ')
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
            print(pos + ': ' + str( self.positions[pos]['size']))
            
        print('\nNet delta (exposure) BTC: $' + str(t))
        print('Net delta (exposure) ETH: $' + str(te))
        print('Total absolute delta (IM exposure) BTC: $' + str(a))
        print('Total absolute delta (IM exposure) ETH: $' + str(ae))
        print('Total absolute delta (IM exposure) combined: $' + str(ae + a))
        self.IM = (0.01 + (((a+ae)/self.equity_usd) *0.005))*100
        self.IM = round(self.IM * 1000)/1000
        self.LEV = (a+ae) / self.equity_usd
        print('Actual initial margin across all accounts: ' + str(self.IM) + '% and leverage is ' + str(round(self.LEV * 1000)/1000) + 'x')
        print( '\nMean Loop Time: %s' % round( self.mean_looptime, 2 ))
            
        print( '' )

        
    def place_orders( self, ex ):
        print('place_orders')
        print(self.arbmult)
        for token in self.arbmult:
            print(token)
            if self.monitor:
                return None
            con_sz  = self.con_size        
             ## FIX THIS IN PROD
            bal_btc         = self.bals['total']
            #print('yo place orders ' + ex + ': ' + token)
            
            spot            = self.get_spot(token)
            skew_size = 0
            #print('skew_size: ' + str(skew_size))
            nbids = 1
            nasks = 1
            
            self.place_bids[token] = True
            self.place_asks[token] = True
            if self.IM > self.PCT_LIM_LONG[token]:
                self.place_bids[token] = False
                nbids = 0
            if self.IM > self.PCT_LIM_SHORT[token]:
                self.place_asks[token] = False
                nasks = 0
            if self.LEV > self.LEV_LIM_LONG[token]:
                self.place_bids[token] = False
                nbids = 0
            if self.LEV > self.LEV_LIM_SHORT[token]:
                self.place_asks[token] = False
                nasks = 0
        
            min_order_size_btc = MIN_ORDER_SIZE / spot
            # 18 / (7000) 0.02571428571428571428571428571429
            # 22 / (7000) 0.00314285714285714285714285714286
            #print('qty of bal: ' + str(PCT_QTY_BASE  * bal_btc))
            #print(str(PCT_QTY_BASE  * bal_btc * spot) + '$')
            qtybtc  = float(max( PCT_QTY_BASE  * bal_btc, min_order_size_btc))
            #print('qtybtc: ' + str(qtybtc))
            #print('qty $: ' + str(qtybtc * spot))
            #print('divided: ' + str(pos_LIM_SHORT[token] / qtybtc))
            print('place_x2L ' + ex + '-' + token)
            print(self.place_bids[token])
            print(self.place_asks[token])

        

            #print('token: ' + token)    
            eps         = 0.0001 * 0.5
            riskfac     = math.exp( eps )

            bbo     = self.get_bbo( ex, token )
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
            if ex == 'binance':
                try:
                    ords        = self.binance.fetchOpenOrders( token + '/USDT' )
                    bid_ords    = [ o for o in ords if o ['info'] [ 'side' ] == 'buy'  ]
                    ask_ords    = [ o for o in ords if o ['info'] [ 'side' ] == 'sell' ]

                except Exception as e:
                    PrintException()#PrintException()
            if ex == 'ftx':
                try:
                    ords        = self.binance.fetchOpenOrders( token + '-PERP' )
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
            #print(fut)
            #print(fut)
            #print(fut)
            #print(fut)
            #print(fut)
            #print(fut)
            #print(fut)

            #print(self.place_asks[token])
            self.execute_arb (token, ex, token, skew_size, nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords )    


    def execute_arb ( self, token, ex, fut, skew_size,  nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords):
        skew_size = skew_size + self.positions[fut]['size']
        #print('skew_size: ' + str(skew_size))
        i = 0
        try:
            prc = self.get_bbo(ex, fut)['bid']
        except:
            print('no bid, returning')
            return
        qty = round ( float(prc) * qtybtc ) / self.get_spot(fut)
        
        #qty = int(qty)
        self.MAX_SKEW = self.MAX_SKEW_OLD
        self.MAX_SKEW = qty * 1.5
        
        

        # bid edit
        try:
            try: 
                oid = bid_ords[ i ][ 'orderId' ]
            except:
                oid = bid_ords[ i ][ 'orderID' ]
            try:
                if ex == 'binance':
                    self.binance.editOrder( oid, qty, prc )
                if ex == 'ftx':
                    self.ftx.editOrder( oid, qty, prc )
            except:
                PrintException()
        except:
                PrintException()
        # ask edit
        try:
            prc = self.get_bbo(ex, fut)['ask']
        except:
            print('no ask, returning')
            return
        try:
            try: 
                oid = ask_ords[ i ][ 'orderId' ]
            except:
                oid = ask_ords[ i ][ 'orderID' ]
            try:
                if ex == 'binance':
                    self.binance.editOrder( oid, qty, prc )
                if ex == 'ftx':
                    self.ftx.editOrder( oid, qty, prc )
            except:
                PrintException()
        except:
            PrintException()
        
        
            
        
        self.execute_longs ( token, qty, ex, fut, skew_size,  nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords)
        self.execute_shorts ( token, qty, ex, fut, skew_size,  nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords)

    def execute_longs ( self, token, qty, ex, fut, skew_size,  nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords):
        
    # Reduce

        if self.positions[fut]['floatingPl'] > 0.01 and math.fabs(self.positions[fut]['size']) > 500:
            print(fut + ' in profit! Gonna reduce!')
    
    
   
        
    
    
    # short Reduce
            
            if self.positions[fut]['size'] > 0:
                if ex == 'binance':
                # deribit
                    self.binance.createOrder(  fut + '/USDT', "Limit", 'sell', qty, self.get_bbo('binance', fut)['ask'], {"newClientOrderId": "x-GYswxDoF-" + self.randomword(20)})
     
                if ex == 'ftx':
                # bybit
                    self.bit.Order.Order_new(side="Sell",symbol=fut,order_type="Limit",qty=qty,price=self.get_bbo('bybit', fut)['ask'],time_in_force="PostOnly").result()
                  
                
    # long reduce
    
            else:
                if ex == 'binance':
                # deribit
                    self.binance.createOrder(  fut + '/USDT', "Limit", 'buy', qty, self.get_bbo('binance', fut)['bid'], {"newClientOrderId": "x-GYswxDoF-" + self.randomword(20)})
     
                if ex == 'ftx':
                # bybit
                    self.ftx.createOrder(  fut + '-PERP', "Limit", 'buy', qty, self.get_bbo('ftx', fut)['bid'], {"newClientOrderId": "x-GYswxDoF-" + self.randomword(20)})    
                    
        
                                    
    # Long add on winning ex, short other ex - or rather 
        
        if self.arbmult[token]['long'] == ex: # 
            print('Ok! ' + ex + ' wins! They can long!')
                    
            if ex == 'binance':
                afut = ""
                for fut in self.futures:
                    if token in fut and qty + skew_size < self.MAX_SKEW and self.place_bids[token] == True:
                        afut = fut
                        self.binance.createOrder(  fut + '/USDT', "Limit", 'buy', qty, self.get_bbo('binance', fut)['bid'], {"newClientOrderId": "x-GYswxDoF-" + self.randomword(20)})
                for fut in self.futures:
                    if token in fut and qty + skew_size * -1 <  self.MAX_SKEW and self.place_asks[token] == True or (self.place_bids[token] == False and self.place_asks[token] == False and math.fabs(positions[token]['size'] > 10)):
                         
                            
                         self.ftx.createOrder(  fut + '-PERP', "Limit", 'sell', qty, self.get_bbo('ftx', fut)['ask'], {"newClientOrderId": "x-GYswxDoF-" + self.randomword(20)}   )
                         print(r) 
                         if afut != "":
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                print('reduced at a profit too much! We must now lose!')
                                r = self.ftx.createOrder(  fut + '-PERP', "Limit", 'buy', qty, self.get_bbo('ftx', fut)['bid'], {"newClientOrderId": "x-GYswxDoF-" + self.randomword(20)})
                         
                    
     
            if ex == 'bybit':
                afut = ""
                for fut in self.futures:
                    if token in fut and qty + skew_size < self.MAX_SKEW and self.place_bids[token] == True or (self.place_bids[token] == False and self.place_asks[token] == False and math.fabs(positions[token]['size'] > 10)):
                        
                        afut = fut
                        
                            
                        r = self.ftx.createOrder(  fut + '-PERP', "Limit", 'buy', qty, self.get_bbo('ftx', fut)['bid'], {"newClientOrderId": "x-GYswxDoF-" + self.randomword(20)})
                        print(r)
                for fut in self.futures:
                    if token in fut and qty + skew_size * -1 <  self.MAX_SKEW and self.place_asks[token] == True or (self.place_bids[token] == False and self.place_asks[token] == False and math.fabs(positions[token]['size'] > 10)):
                        
                        self.binance.createOrder(  fut + '/USDT', "Limit", 'sell', qty, self.get_bbo('binance', fut)['ask'], {"newClientOrderId": "x-GYswxDoF-" + self.randomword(20)})
                        if afut != "":
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                print('reduced at a profit too much! We must now lose!')
                                self.binance.createOrder(  fut + '/USDT', "Limit", 'buy', qty, self.get_bbo('binance', fut)['bid'], {"newClientOrderId": "x-GYswxDoF-" + self.randomword(20)})
                    
               
            self.execute_cancels(ex, fut, skew_size,  nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords)


    def execute_shorts ( self, token, qty, ex, fut, skew_size,  nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords):


        # add short on winning ex, short other ex
        if self.arbmult[token]['short'] == ex: # Ok! You win! You can short!
            print('Ok! ' + ex + ' wins! They can short!')
            

            if ex == 'binance':
                afut = ""
                for fut in self.futures:
                    if token in fut and qty + skew_size * -1 <  self.MAX_SKEW and self.place_asks[token] == True:
                        afut = fut
                        
                        self.binance.createOrder(  fut + '/USDT', "Limit", 'sell', qty, self.get_bbo('binance', fut)['ask'], {"newClientOrderId": "x-GYswxDoF-" + self.randomword(20)})
                for fut in self.futures:
                    if token in fut and qty + skew_size < self.MAX_SKEW and self.place_bids[token] == True or (self.place_bids[token] == False and self.place_asks[token] == False and math.fabs(positions[token]['size'] > 10)):
                        
                            
                        r = self.ftx.createOrder(  fut + '-PERP', "Limit", 'buy', qty, self.get_bbo('ftx', fut)['bid'], {"newClientOrderId": "x-GYswxDoF-" + self.randomword(20)})
                        if afut != "":
                            if ex == 'ftx':
                                fut = "ETHUSD"
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                print('reduced at a profit too much! We must now lose!')
                                self.ftx.createOrder(  fut + '-PERP', "Limit", 'sell', qty, self.get_bbo('ftx', fut)['ask'], {"newClientOrderId": "x-GYswxDoF-" + self.randomword(20)})
                    
                        print(r)
                
     
            if ex == 'bybit':
                afut = ""
                for fut in self.futures:
                    if token in fut and qty + skew_size * -1 <  self.MAX_SKEW and self.place_asks[token] == True:
                        afut = fut
                        
                            
                        self.ftx.createOrder(  fut + '-PERP', "Limit", 'sell', qty, self.get_bbo('ftx', fut)['ask'], {"newClientOrderId": "x-GYswxDoF-" + self.randomword(20)})
                        print(r)
                for fut in self.futures:
                    if token in fut and qty + skew_size < self.MAX_SKEW and self.place_bids[token] == True or (self.place_bids[token] == False and self.place_asks[token] == False and math.fabs(positions[token]['size'] > 10)):
                        self.binance.createOrder(  fut + '/USDT', "Limit", 'buy', qty, self.get_bbo('binance', fut)['bid'], {"newClientOrderId": "x-GYswxDoF-" + self.randomword(20)})
                        if afut != "":
                            if math.fabs(self.positions[fut]['size']) >= 100 and math.fabs(self.positions[fut]['size']) > 1.33 * math.fabs(self.positions[afut]['size']):
                                print('reduced at a profit too much! We must now lose!')
                                self.binance.createOrder(  fut + '/USDT', "Limit", 'sell', qty, self.get_bbo('binance', fut)['ask'], {"newClientOrderId": "x-GYswxDoF-" + self.randomword(20)})
                  


                   
            self.execute_cancels(ex, fut, skew_size,  nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords)
        
    def cancelall(self, pair, ex ):
        if ex == 'binance':
            ords        = self.binance.fetchOpenOrders( pair + '/USDT' )
            
            for order in ords:
                #print(order)
                oid = order ['info'] ['orderId']
               # print(order)
                try:
                    self.binance.cancelOrder( oid , pair )
                except Exception as e:
                    print(e)
        if ex == 'ftx':
            ords        = self.ftx.fetchOpenOrders( pair + '-PERP')
            for order in ords:
                #print(order)
                oid = order ['info'] ['orderId']
               # print(order)
                try:
                    self.ftx.cancelOrder( oid , pair )
                except Exception as e:
                    print(e)
    def execute_cancels(self, ex, fut, skew_size,  nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords):
        if ex == 'binance':
            if nbids < len( bid_ords ):
                cancel_oids += [ o[ 'orderId' ] for o in bid_ords[ nbids : ]]
            if nasks < len( ask_ords ):
                cancel_oids += [ o[ 'orderId' ] for o in ask_ords[ nasks : ]]
            for oid in cancel_oids:
                try:
                    self.binance.cancel( oid )
                except:
                    self.logger.warn( 'Order cancellations failed: %s' % oid )
        if ex == 'ftx':
            
            if nbids < len( bid_ords ):
                cancel_oids += [ o[ 'orderID' ] for o in bid_ords[ nbids : ]]
            if nasks < len( ask_ords ):
                cancel_oids += [ o[ 'orderID' ] for o in ask_ords[ nasks : ]]
            for oid in cancel_oids:
                try:
                    self.ftx.cancel( oid )
            
                except:
                    PrintException()
                    self.logger.warn( 'Order cancellations failed: %s' % oid )

    def restart( self ):        
        try:
            strMsg = 'RESTARTING'
            print( strMsg )
            
            for fut in self.futures:
                self.cancelall(fut, 'ftx')
            for fut in self.futures:
                self.cancelall(fut, 'binance')
            
            strMsg += ' '
            for i in range( 0, 5 ):
                strMsg += '.'
                #print( strMsg )
                sleep( 1 )
        except:
            pass
        finally:
            os.execv( sys.executable, [ sys.executable ] + sys.argv )        
            
    


    def run( self ):
        
        self.run_first()
        self.output_status()
        print('run')    
        t_ts = t_out = t_loop = t_mtime = datetime.utcnow()

        while True:

            
            
            
            self.update_rates()
            self.update_balances()    
            self.update_positions()
        
            t_now   = datetime.utcnow()
            
            # Update time series and vols
            self.place_orders('binance')
            
            self.place_orders('ftx')
            #print('out of sleep!')
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
        
        self.start_time         = datetime.utcnow()
        self.update_status()
        
        self.equity_usd_init    = self.equity_usd
        self.equity_btc_init    = self.equity_btc
        
    def update_status( self ):
        
                      
        
        spot    = self.get_spot('BTC')
        t = 0
        print('set bals')
        print(self.bals['total'])   
        self.equity_usd = self.bals['total']
        self.equity_btc = self.bals['total'] / spot

                
        
    def update_positions( self ):
        print('update_positions')
        for pair in self.futures:

                self.positions[pair] = {
                'size':         0,
                'sizeBtc':      0,
                'averagePrice': None,
                'floatingPl': 0}

        for ex in self.totrade:
            
            if ex == 'binance':
                positions       = self.binance.fapiPrivateGetPositionRisk()
                #print('lala')
                #print(positions)
                #print(self.futures)
                for pos in positions:
                    #print('binance pos')
                    #print(pos)
                    pos['symbol'] = pos['symbol'].replace('USDT', '')
                    if pos['symbol'] in self.futures:
                        pos['size'] = float(pos['positionAmt']) * float(pos['markPrice'])
                        pos['floatingPl'] = float(pos['unRealizedProfit']) 
                        
                        if pos['symbol'] in self.futures:
                            self.positions[ pos[ 'symbol' ]] = pos
            if ex == 'ftx':
                try:
                    positions       = self.ftx.privateGetPositions()['result']
                    #print(self.futures)
                    spot = self.get_spot('BTC')
                    for pos in positions:
                        #print('ftx pos')
                        #print(pos)
                        pos['future'] = pos['future'].replace('-PERP', '')
                        if pos[ 'future' ] in self.futures:
                            pos['floatingPl'] = pos['unrealizedPnl']
                            pos['size'] = float(pos['netSize']) * self.get_spot(pos['future'])
                            if pos['side'] == 'sell':
                                pos['size'] = pos['size'] * spot * -1
                            else:
                                pos['size'] = pos['size'] * spot
                            self.positions[ pos[ 'future' ]] = pos
                except:
                    PrintException()
                
if __name__ == '__main__':
    
    print('hello world')
    try:
        mmbot = MarketMaker( monitor = args.monitor, output = args.output )
        mmbot.run()
    except( KeyboardInterrupt, SystemExit ):
        #print( "Cancelling open orders" )
        for fut in mmbot.futures:
            mmbot.cancelall(fut, 'ftx')
            mmbot.cancelall(fut, 'binance')
        
        sys.exit()
    except:
        print( traceback.format_exc())
        if args.restart:
            mmbot.restart()
        