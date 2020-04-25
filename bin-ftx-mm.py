# This code is for sample purposes only, comes as is and with no warranty or guarantee of performance

import sys
import threading
import time
from queue import Queue
import random, string
import datetime

from threading import Timer

from unicorn_binance_websocket_api.unicorn_binance_websocket_api_manager import BinanceWebSocketApiManager
from unicorn_fy.unicorn_fy import UnicornFy
binance_websocket_api_manager = BinanceWebSocketApiManager(exchange="binance.com-futures")
import inspect

start_time         = datetime.datetime.utcnow()
def pprint(string):
    

    
    log = 'log.txt'
    with open(log, "a") as myfile:
        myfile.write(datetime.datetime.utcnow().strftime( '%Y-%m-%d %H:%M:%S' ) + ', line: ' + str(inspect.currentframe().f_back.f_lineno)  + ': ' + str(string) + '\n')

from collections    import OrderedDict
from os.path        import getmtime
from time           import sleep
from utils          import ( get_logger, lag, print_dict, print_dict_of_dicts, sort_by_key,
                             ticksize_ceil, ticksize_floor, ticksize_round )
import requests
import bitmex
import bybit
import json

import copy as cp
import argparse, logging, math, os, pathlib, sys, time, traceback
import ccxt
import random



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

ftxkey     = os.environ["ftxkey"]#"NqOlVRaqGM-XCX0cpf67UYxvT2tcB56SHlS-tlB-"#"VC4d7Pj1"
ftxsecret  = os.environ["ftxsecret"]#gnBQZHa8-cT1E-p0YyNqHkx9Y_8bdk"#"IB4VEP26OzTNUt4JhNILOW9aDuzctbGs_K6izxQG2dI"

binkey     = os.environ["binkey"]#"VC4d7Pj1"
binsecret  = os.environ['binsecret']#"#"IB4VEP26OzTNUt4JhNILOW9aDuzctbGs_K6izxQG2dI"
URL     = 'https://www.deribit.com'
binance_websocket_api_manager = BinanceWebSocketApiManager(exchange="binance.com-futures")
3.set_private_api_config(binkey, binsecret)
userdata_stream_id = binance_websocket_api_manager.create_stream(["!userData"], ["arr"])
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
        self.MAX_SKEW_OLD = MIN_ORDER_SIZE *1.5

        
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
        self.bin_futures = {}
        self.notperps = []
        self.rateCounter = 9
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
    def printException(self):
        exc_type, exc_obj, tb = sys.exc_info()
        f = tb.tb_frame
        lineno = tb.tb_lineno
        filename = f.f_code.co_filename
        linecache.checkcache(filename)
        line = linecache.getline(filename, lineno, f.f_globals)
        string = 'EXCEPTION IN ({}, LINE {} "{}"): {}'.format(filename, lineno, line.strip(), exc_obj)
        print (string)
        pprint(string)
        sleep(10)
    def update_bin_pos ( self ):
        while True:
            try:
                
                ex = ''
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
                sleep(0.1)
            except Exception as e:
                #print(e)
                #pprint(e)
                sleep(0.1)
    def resetBlocker(self,token):
        pprint('unblock ' + token)
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
        
        self.arbmult = {}

        for token in self.positions:
            self.arbmult[token.split('-')[0]] = {}
        for token in self.positions:
            self.arbmult[token.split('-')[0]]['perc'] = 0
            self.arbmult[token.split('-')[0]]['arb'] = 0
        minArb = ((0.0002 * 1 + 0.0002 * 1) / 2 * 2) #* 2
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
        if w not in self.totrade:
            self.totrade.append(w)
        print(allfuts)
        for ftxfut in allfuts:
            if w in ftxfut:
                futlist[ftxfut.split('-')[0]] =  ftxfut
        print(futlist)    
        self.futures = []
        self.notperps = []
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
                        self.notperps.append(futlist[arb])

                        self.futures.append(arb)
                        self.active.append(arb)
                    if ftx < -1 * minArb:
                        self.arbmult[arb] = ({'coin': arb, 'long': 'ftx', 'short': futlist[arb], 'arb': -1 * ftx})
                        self.futures.append(arb)
                        self.notperps.append(futlist[arb])
                        self.active.append(arb)

                elif (binance < 0 or binance > 0 and math.fabs(binance) > math.fabs(ftx)) and math.fabs(binance) > minArb:
                    if binance > minArb:
                        self.arbmult[arb] = ({'coin': arb, 'long': futlist[arb], 'short': 'binance', 'arb': binance})
                        self.futures.append(arb)
                        self.active.append(arb)
                        self.notperps.append(futlist[arb])

                    if binance < -1 * minArb:
                        self.arbmult[arb] = ({'coin': arb, 'long': 'binance', 'short': futlist[arb], 'arb': -1 * binance})
                        self.futures.append(arb)
                        self.notperps.append(futlist[arb])
                        self.active.append(arb)
                else:
                    pprint('loser ' + arb)
                    pprint(ftx - minArb)
                    pprint(binance - minArb)
        print(minArb)
        
        t = 0
        c = 0
        bal = self.bals['total']
        lev = 5
        exposure = bal * lev
        fees = (0.02/100 + (0.02*0.7)/100) * 2
        for arb in self.arbmult:
            if self.arbmult[arb]['arb'] > minArb:
                t = t + self.arbmult[arb]['arb']

                c = c + 1
        pprint('t: ' + str(t))
        tdaily = 0
        test = 0
        ohlcvt = 0
        ohlcvc = 0
        ohlcvVolumes = {}
        ohlcvh = 0
        ohlcvl = 9999999999999999999999999
        for arb in self.arbmult:
            if self.arbmult[arb]['arb'] > minArb:
                ohlcv = self.ftx.fetchOHLCV(arb + '-PERP', '1h')

                if ohlcv[-1][4] * ohlcv[-1][5] > ohlcvh:
                    ohlcvh = ohlcv[-1][4] * ohlcv[-1][5]
                if ohlcv[-1][4] * ohlcv[-1][5] < ohlcvl:
                    ohlcvl = ohlcv[-1][4] * ohlcv[-1][5]
                ohlcvVolumes[arb] = ohlcv[-1][4] * ohlcv[-1][5]
                ohlcvt = ohlcvt + (ohlcv[-1][4] * ohlcv[-1][5])

                ohlcvc = ohlcvc + 1
            else:
                ohlcvVolumes[arb] = 0

        ohlcvt = ohlcvt - ohlcvh
        ohlcvt = ohlcvt - ohlcvl
        ohlcvc = ohlcvc - 2
        ohlcvavg = ohlcvt / ohlcvc
        for arb in self.arbmult:
            if ohlcvVolumes[arb] < ohlcvavg / 50:
                t = t - self.arbmult[arb]['arb']
                c = c - 1
        print('ohlcv count (less outliers)')
        print(ohlcvc)
        print('ohlcv total (less outliers)')
        print(ohlcvt)

        print('ohlcv avg (less outliers)')
        print(ohlcvavg)
        for arb in self.arbmult:
            if ohlcvVolumes[arb] > ohlcvavg / 50:
                self.arbmult[arb]['perc'] = round(self.arbmult[arb]['arb'] / t * 1000) / 1000 #* 1.41425
                self.arbmult[arb]['amt'] = round(exposure * self.arbmult[arb]['perc'] * 1000) / 1000
                self.arbmult[arb]['daily'] = round(self.arbmult[arb]['amt'] * self.arbmult[arb]['arb'] * 1000) / 1000
                
                self.arbmult[arb]['daily fees'] = self.arbmult[arb]['daily'] * fees
                self.arbmult[arb]['daily - fees'] = self.arbmult[arb]['daily'] - self.arbmult[arb]['daily fees']
                tdaily = tdaily + self.arbmult[arb]['daily - fees']
            else:
                self.arbmult[arb]['perc'] = 0
                print(arb + ' less than half the avg ohlcv volume (less outliers)! Arbmult percentage of total 0!')
        
        pprint(self.arbmult)
        returns = round((tdaily / bal) * 1000000) / 10000
        ##print('assuming $' + str(bal) + ' balance and ' + str(lev) + 'x leverage, and ' + str(fees * 100) + '% fees for a roundtrip as maker to buy/sell the exposure: ')
        ##print(self.arbmult)
        ##print('that would be ' + str(returns) + '% daily returns')
        annualret = (self.compounding(365, bal, returns / 100) * 1000) / 1000
        roe = ((((annualret / bal) * 1000) / 10) * 1000) / 1000
        apr = (returns * 365 * 1000) / 1000
        ##print('that is $' + str(annualret) + ' annualized, ' + str(roe) + '% ROE and ' + str(apr) + '% APR')
        coins = []
        for coin in self.positions:
            coin = coin.split('-')[0]
            if coin not in coins:
                coins.append(coin)
        for coin in self.futures:
            coin = coin.split('-')[0]
            if coin not in coins:
                coins.append(coin)
        
        for coin in coins:
            self.PCT_LIM_LONG[coin]        = 15      # % position limit long
            self.LEV_LIM_LONG[coin] = 30
            self.LEV_LIM_SHORT[coin] = 30
            self.PCT_LIM_SHORT[coin]       = 15    # % position limit short
        for coin in coins:
            self.LEV_LIM_LONG[coin] = self.LEV_LIM_LONG[coin] * self.arbmult[coin]['perc'] 
            self.LEV_LIM_SHORT[coin] = self.LEV_LIM_SHORT[coin] * self.arbmult[coin]['perc'] 
            self.PCT_LIM_SHORT[coin]  = self.PCT_LIM_SHORT[coin] * self.arbmult[coin]['perc'] 
            self.PCT_LIM_LONG[coin]  = self.PCT_LIM_LONG[coin] * self.arbmult[coin]['perc']
            
        #0.0011
        #119068
        print(self.arbmult)
        
        totlev = 0
        print(self.LEV_LIM_SHORT)
        for lev in self.LEV_LIM_SHORT:
            totlev = totlev + self.LEV_LIM_SHORT[lev]
        print('totlev: ' + str(totlev))
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
            'apiKey': ftxkey,   
            'secret': ftxsecret,
        })
        self.binance     = ccxt.binance({
            'enableRateLimit': True,
            'apiKey': binkey,
            'secret': binsecret,
            "options":{"defaultMarket":"futures"},
            'urls': {'api': {
                                     'public': 'https://fapi.binance.com/fapi/v1',
                                     'private': 'https://fapi.binance.com/fapi/v1',},}
 })
    def get_bin_futures( self ): # Get all current futures instruments
        
        insts               = self.binance.fetchMarkets()
        #print(insts[0])
        self.bin_futures        = sort_by_key( { 
            i[ 'symbol' ]: i for i in insts 
        } )
        #print(self.futures)
        #for k, v in self.futures.items():
            #self.futures[ k ][ 'expi_dt' ] = datetime.strptime( 
            #                                   v[ 'expiration' ][ : -4 ], 
            #                                   '%Y-%m-%d %H:%M:%S' )
                        
        


    def get_eth( self ):
        r = requests.get('https://api.binance.com/api/v1/ticker/price?symbol=ETHUSDT').json()
        return float(r['price'])
    def get_bbo( self, exchange, contract ): # Get best b/o excluding own orders
        if exchange == 'binance':
            # Get orderbook
            ob      = self.binance.fetchOrderBook( contract + '/USDT' )
            bids    = ob[ 'bids' ]
            asks    = ob[ 'asks' ]
       
            #best_bid = self.get_spot(contract)
            #best_ask = best_bid
            try:
                best_bid    = bids[0][0]
                best_ask    = asks[0][0]
            except:

                self.printException()
            
        if exchange == 'ftx':
            if '-' in contract:
                ob      = self.ftx.fetchOrderBook( contract )
            else:
                if '-' in contract:
                    ob      = self.ftx.fetchOrderBook( contract )
                else:
                    ob      = self.ftx.fetchOrderBook( contract + '-PERP')
            bids    = ob[ 'bids' ]
            asks    = ob[ 'asks' ]
       
            #best_bid = self.get_spot(contract)
            #best_ask = best_bid
            try:
                best_bid    = bids[0][0]
                best_ask    = asks[0][0]
            except:
                self.printException()
            
                   
        return { 'bid': best_bid, 'ask': best_ask }
    
        
        
    def get_pct_delta( self ):         
        self.update_status()
        return sum( self.deltas.values()) / self.equity_btc

    
    def get_spot( self, contract ):
        r = requests.get('https://api.binance.com/api/v1/ticker/price?symbol=' + contract.split('-')[0] + 'USDT').json()
        return float(r['price'])
    
    def get_precision( self, contract ):
        
        return float(self.bin_futures[ contract + '/USDT' ]['precision'][ 'amount' ])
        
    
    def get_ticksize( self, ex, contract ):
        return self.futures[ contract ] ['info'] ['filters'] [ 0 ] [ 'tickSize' ]
        
    
    def output_status( self ):
        
        if not self.output:
            return None
        
        self.update_status()
        print    (    '\nPositions: ')
        t = 0
        a = 0
        te = 0
        ae = 0
        for pos in self.positions:
            if math.fabs(self.positions[pos]['size'])  != 2:
                a = a + math.fabs(self.positions[pos]['size'])
            
                t = t + self.positions[pos]['size'] 
                print    (   pos + ': ' + str( self.positions[pos]['size'] ))
                
        print    (   '\nNet delta (exposure) USD: $' + str(t))
        print    (   'Total absolute delta (IM exposure) USD: $' + str(a))
        print    (   'Actual initial margin across all accounts: ' + str(self.IM) + '% and leverage is ' + str(round(self.LEV * 1000)/1000) + 'x')
        print    (   ' ')    
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
        
        print    (    'Equity ($):        %7.2f'   % self.equity_usd)
        print    (    'P&L ($)            %7.2f'   % pnl_usd)
        print    (    'Equity (BTC):      %7.4f'   % self.equity_btc)
        print    (    'P&L (BTC)          %7.4f'   % pnl_btc)

        
        print    (    '' )

        
    def place_orders( self, ex ):
        ##print('place_orders')
        ##print(self.arbmult)
        up = 0
        tokens = []
        for token in self.futures:
            tokens.append(token)
        for tokenex in self.positions:
            if tokenex.split('-')[0] not in tokens:
                tokens.append(tokenex.split('-')[0])

        token = tokens[random.randint(0, len(tokens)-1)]
        
        
        self.skew_size[token] = 0
        if True:
            up = up + 1
            
            if token in self.blockers:
                if self.blockers[token] == True:
                    pprint('blocked..return')
                    return

            ##print(token)
            if self.monitor:
                return None
            con_sz  = self.con_size        
             ## FIX THIS IN PROD
            bal_btc         = self.bals['total']
            ###print('yo place orders ' + ex + ': ' + token)
            
            spot            = self.get_spot('BTC')
            nbids = 1
            nasks = 1
            
            self.place_bids[token.split('-')[0]] = True
            self.place_asks[token.split('-')[0]] = True
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

            pprint(self.LEV_LIM_LONG)
            t = 0
            for lev in self.LEV_LIM_LONG:
                t = t + self.LEV_LIM_LONG[lev]
            pprint('t: ' + str(t))
            pprint(self.place_bids)
            fut = token
            if (fut + '-' + ex) in self.positions:
                if self.positions[fut + '-' + ex]['size'] < self.MAX_SKEW * 2 and self.place_bids[token.split('-')[0]] == False and self.place_asks[token.split('-')[0]] == False and self.positions[fut + '-' + ex]['size'] > -1 * self.MAX_SKEW * 2:
                    pprint('no bid or ask, returning ' + fut)
                    #return
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
            ##print(self.place_bids[token.split('-')[0]])
            ##print(self.place_asks[token.split('-')[0]])

        

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
                    self.printException()#self.printException()
            if ex == 'ftx':
                try:
                    if '-' in token:
                        ords        = self.ftx.fetchOpenOrders( token )
                    else:
                        ords        = self.ftx.fetchOpenOrders( token + '-PERP' )
                    bid_ords    = [ o for o in ords if o ['info'] [ 'side' ] == 'buy'  ]
                    ask_ords    = [ o for o in ords if o ['info'] [ 'side' ] == 'sell' ]
                except Exception as e:
                    self.printException()#self.printException()
           
            asks = []
            bids = []
            len_bid_ords    = min( len( bid_ords ), nbids )
            len_ask_ords    = min( len( ask_ords ), nasks )
            if self.place_bids[token.split('-')[0]]:      
                bids.append(bid_mkt)
            if self.place_asks[token.split('-')[0]]:
                asks.append(ask_mkt)
           
            ###print(self.place_asks[token.split('-')[0]])
            self.execute_arb (token, ex, token, nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords )    


    def execute_arb ( self, token, ex, fut, nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords):
        fut = token
        pprint(fut)
        try:
            prc = self.get_bbo(ex, fut)['ask']
        except Exception as e:
            self.printException()
            
        if prc > 5000:
            pprint('prc too high, returning')
            return
        #print('token token ' + fut)
        splittok = token
        pprint(token)
        self.skew_size[token] = 0
        for ex2 in self.totrade:
                
            if (fut + '-' + ex2) in self.positions:
                self.skew_size[token] = self.skew_size[token] + self.positions[fut + '-' + ex2]['size'] 
            #print('skew_size[token]: ' + str(self.skew_size[token]))
        pprint('skew size')
        pprint(self.skew_size)
        i = 0
                    ##BTC     ##USD 
        self.blocktrues = 1
        for block in self.blockers:
            if self.blockers[block] == True:
                self.blocktrues = self.blocktrues * 1.25                  
        self.qty = ((( qtybtc * self.get_spot('BTC')) / prc)) * self.blocktrues
        precision = self.get_precision(token)
        self.qty = max( 3 / 10 ** precision, round(self.qty * (10 ** precision)) / 10 ** precision)
        self.MAX_SKEW = self.qty * prc * 1.5
            

        
        self.MAX_SKEW = self.MAX_SKEW * self.blocktrues
        pprint('qty: ' + fut + ': ' + str(self.qty))
        #qty = int(qty)

        #print('skew_size[token]: ' + str(self.skew_size[token]))
        #print('MAX SKEW ' + str(self.MAX_SKEW))
        #print('qty ' + str(self.qty))
        #print('calc ' +str( self.qty * prc + self.skew_size[token] ))
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
        pprint('blockers')
        pprint(self.blockers)
        if token in self.blockers:
            if self.blockers[token] == False:
                gogo = True

        else:
            gogo = True
        if gogo == True:
                
            try:
                if self.positions[fut + '-binance']['size'] > self.MAX_SKEW * 2 and self.place_bids[token.split('-')[0]] == False and self.place_asks[token.split('-')[0]] == False:
                    
                    self.binance.createOrder(  fut + '/USDT', "Limit", 'sell', self.qty, self.get_bbo('binance', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                    pprint('sell bin, return')
                    
                if self.positions[fut + '-binance']['size'] < -1 * self.MAX_SKEW * 2 and self.place_bids[token.split('-')[0]] == False and self.place_asks[token.split('-')[0]] == False:
                    
                    self.binance.createOrder(  fut + '/USDT', "Limit", 'buy', self.qty, self.get_bbo('binance', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                    pprint('buy bin, return')
                    
                if self.positions[fut + '-ftx']['size'] > self.MAX_SKEW * 2 and self.place_bids[token.split('-')[0]] == False and self.place_asks[token.split('-')[0]] == False:
                    
                    self.ftx.createOrder(  fut + '-PERP', "limit", 'sell', self.qty, self.get_bbo('ftx', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                    pprint('sell ftx, return')
                    
                if self.positions[fut + '-ftx']['size'] < -1 * self.MAX_SKEW * 2 and self.place_bids[token.split('-')[0]] == False and self.place_asks[token.split('-')[0]] == False:
                    
                    self.ftx.createOrder(  fut + '-PERP', "limit", 'buy', self.qty, self.get_bbo('ftx', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                    pprint('buy ftx, return')
                    
                if self.place_asks[token.split('-')[0]] == False and self.place_bids[token.split('-')[0]] == False and (math.fabs(self.positions[fut+'-binance']['size']) > 15 or math.fabs(self.positions[fut+'-ftx']['size']) > 15):
                    

                    self.maybes[token] = True
            except Exception as e:
                print(e)

        # bid edit
        try:
            for i in bid_ords:
                oid = i[ 'id' ]
                side = i[ 'side' ]
                try:
                    if ex == 'binance':
                        
                        self.binance.editOrder( oid, fut + '/USDT', 'limit', side, self.qty, self.get_bbo('binance', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15) })
                    if ex == 'ftx':
                        
                        if '-' in fut:
                            self.ftx.editOrder( oid, fut, 'limit', side, self.qty, self.get_bbo('ftx', fut)['bid'], {'leverage': 10})
                        else:
                            self.ftx.editOrder( oid, fut + '-PERP', 'limit', side, self.qty, self.get_bbo('ftx', fut)['bid'], {'leverage': 10})
                except:
                    self.printException()

                    abc=123#self.printException()
        except:
            self.printException()
            abc=123#self.printException()
        # ask edit
        

        try:
            for i in ask_ords:
                oid = i[ 'id' ]
                side = i[ 'side' ]
                try:
                    if ex == 'binance':
                        
                        self.binance.editOrder( oid, fut + '/USDT', 'limit', side, self.qty, self.get_bbo('binance', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15) })
                    if ex == 'ftx':
                        
                        if '-' in fut:
                            self.ftx.editOrder( oid, fut, 'limit', side, self.qty, self.get_bbo('ftx', fut)['ask'], {'leverage': 10})
                        else:
                            self.ftx.editOrder( oid, fut + '-PERP', 'limit', side, self.qty, self.get_bbo('ftx', fut)['ask'], {'leverage': 10})
                except:
                    self.printException()
                    abc=123#self.printException()
        except:
            self.printException()
            abc=123#self.printException()
        
        if len(bid_ords) > 1:
            self.place_bids[fut.split('-')[0]] = False
            print('enough bids!')
        if len(ask_ords) > 1:
            self.place_asks[fut.split('-')[0]] = False
            print('enough bids!')

            
        if 'long' in self.arbmult[token]:
        
            self.execute_longs ( prc, splittok, token, ex, fut, nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords)
            self.execute_shorts ( prc, splittok, token, ex, fut, nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords)
        
    def execute_longs ( self, prc, splittok, token, ex, fut, nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords):
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
                        pprint('bin 1')
                        
                        self.binance.createOrder(  fut + '/USDT', "Limit", 'sell', self.qty, self.get_bbo('binance', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                        
                        self.ftx.createOrder(  fut + '-PERP', "limit", 'buy', self.qty / 3, self.get_bbo('ftx', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})    
                        
                    if ex == 'ftx':
                    # bybit
                        pprint('ftx 1')
                        
                        self.ftx.createOrder(  fut + '-PERP', "limit", 'sell', self.qty, self.get_bbo('ftx', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})    
                        
                        self.binance.createOrder(  fut + '/USDT', "Limit", 'buy', self.qty / 3, self.get_bbo('binance', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                        
                    
        # long reduce
        
                else:
                    if ex == 'binance':
                    # deribit
                        pprint('bin 2')
                        
                        self.binance.createOrder(  fut + '/USDT', "Limit", 'buy', self.qty, self.get_bbo('binance', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                        
                        self.ftx.createOrder(  fut + '-PERP', "limit", 'sell', self.qty / 3, self.get_bbo('ftx', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})    
                        
                    if ex == 'ftx':
                    # bybit
                        pprint('ftx 2')
                        
                        self.ftx.createOrder(  fut + '-PERP', "limit", 'buy', self.qty, self.get_bbo('ftx', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})    
                        
                        self.binance.createOrder(  fut + '/USDT', "Limit", 'sell', self.qty / 3, self.get_bbo('binance', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                        
            pprint(ex)
            # long fut short ex?

            if self.arbmult[token]['long'] not in self.totrade:
                pprint('long fut ' + self.arbmult[token]['long'] + ' short ex: ' + self.arbmult[token]['short'])
                if ex == 'binance' and self.arbmult[token]['short'] == 'binance':
                    afut = ""
                    pprint(self.MAX_SKEW)
                    pprint(self.qty * prc + self.skew_size[token])

                    if (reducing == False and token in fut and  self.qty * prc + (self.skew_size[token]) > -1 *  self.MAX_SKEW  and self.place_asks[token.split('-')[0]] == True):
                        afut = fut
                        if fut in self.maybes :
                            if self.maybes[fut] == True and self.place_bids[token.split('-')[0]] == True:
                                self.blockers[fut] = True
                                self.maybes[fut] = False
                                r = Timer(wait_seconds, self.resetBlocker, (token))
                                pprint('block ' + token + ' for ' + str(wait_seconds))
                                r.start()    
                                
                        pprint('binbin sell a fut')
                        gogo = False
                        if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                        else: 
                            gogo = True    
                        if gogo == True: 
                            
                            self.binance.createOrder(  fut + '/USDT', "Limit", 'sell', self.qty, self.get_bbo('binance', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                        
                    pprint(self.qty * prc + -1 * self.skew_size[splittok])
                    if  token in fut and  self.qty * prc + (self.skew_size[splittok]) <  self.MAX_SKEW and self.place_bids[token.split('-')[0]] == True:
                         gogo = False
                         if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                         else: 
                            gogo = True    
                         if gogo == True:
                            pprint('ftxftx fut buy')
                            print((self.arbmult)  )
                            try: 
                                self.ftx.createOrder( self.arbmult[token]['short'], "limit", 'buy', self.qty, self.get_bbo('ftx', self.arbmult[token]['short'])['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)}   )
                            except:
                                abc123 = 1
                #print(str(self.PCT_LIM_LONG[token]) + ' Ok! ' + ex + ' wins! They can long! ' + str(self.place_bids[token.split('-')[0]]) + ' ' + str(self.IM))
                if ex == 'ftx' and self.arbmult[token]['short'] == 'ftx':
                    afut = ""
                    pprint(self.MAX_SKEW)
                    pprint(self.qty * prc + self.skew_size[token])
                    if (reducing == False and token in fut and  self.qty * prc + (self.skew_size[token]) > -1 * self.MAX_SKEW  and self.place_asks[token.split('-')[0]] == True):
                        afut = fut
                        if fut in self.maybes :
                            if self.maybes[fut] == True and self.place_bids[token.split('-')[0]] == True:
                                self.blockers[fut] = True
                                self.maybes[fut] = False
                                r = Timer(wait_seconds, self.resetBlocker, (token))
                                pprint('block ' + token + ' for ' + str(wait_seconds))
                                r.start()    
                                
                        pprint('ftx buy')
                        gogo = False
                        if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                        else: 
                            gogo = True    
                        if gogo == True: 
                            
                            self.ftx.createOrder(  fut + '-PERP', "limit", 'sell', self.qty, self.get_bbo('ftx', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)}   )
                            
                    
                    pprint(self.qty * prc + -1 * self.skew_size[splittok])
                    if  token in fut and  self.qty * prc + (self.skew_size[splittok]) <  self.MAX_SKEW and self.place_bids[token.split('-')[0]] == True:
                         gogo = False
                         if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                         else: 
                            gogo = True    
                         if gogo == True:
                            pprint('ftxftx fut buy')
                            try:
                                self.ftx.createOrder( self.arbmult[token]['short'], "limit", 'buy', self.qty, self.get_bbo('ftx', self.arbmult[token]['short'])['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)}   )
                            except:
                                abc=123            # short fut long ex?
            elif self.arbmult[token]['short'] not in self.totrade:
                pprint('short fut ' + self.arbmult[token]['short'] + ' long ex: ' + self.arbmult[token]['long'])
                if ex == 'binance' and self.arbmult[token]['long'] == 'binance':
                    afut = ""
                    pprint(self.MAX_SKEW)
                    pprint(self.qty * prc + self.skew_size[token])

                    if (reducing == False and token in fut and  self.qty * prc + (self.skew_size[token]) <  self.MAX_SKEW  and self.place_bids[token.split('-')[0]] == True):
                        afut = fut
                        if fut in self.maybes :
                            if self.maybes[fut] == True and self.place_bids[token.split('-')[0]] == True:
                                self.blockers[fut] = True
                                self.maybes[fut] = False
                                r = Timer(wait_seconds, self.resetBlocker, (token))
                                pprint('block ' + token + ' for ' + str(wait_seconds))
                                r.start()    
                                
                        pprint('binbin buy a fut')
                        gogo = False
                        if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                        else: 
                            gogo = True    
                        if gogo == True: 
                            
                            self.binance.createOrder(  fut + '/USDT', "Limit", 'buy', self.qty, self.get_bbo('binance', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                        
                    pprint(self.qty * prc + -1 * self.skew_size[token])
                    if  token in fut and self.place_asks[token.split('-')[0]] == True and  self.qty * prc + (self.skew_size[splittok]) > -1 *  self.MAX_SKEW:
                         gogo = False
                         if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                         else: 
                            gogo = True    
                         if gogo == True:
                            pprint('ftxftx fut sell')
                            try:
                                self.ftx.createOrder( self.arbmult[token]['short'], "limit", 'sell', self.qty, self.get_bbo('ftx', self.arbmult[token]['short'])['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)}   )
                            except:
                                abc=123
                #print(str(self.PCT_LIM_LONG[token]) + ' Ok! ' + ex + ' wins! They can long! ' + str(self.place_bids[token.split('-')[0]]) + ' ' + str(self.IM))
                if ex == 'ftx' and self.arbmult[token]['long'] == 'ftx':
                    afut = ""
                    pprint(self.MAX_SKEW)
                    pprint(self.qty * prc + self.skew_size[token])
                    if (reducing == False and token in fut and  self.qty * prc + (self.skew_size[token]) <  self.MAX_SKEW  and self.place_bids[token.split('-')[0]] == True):
                        afut = fut
                        if fut in self.maybes :
                            if self.maybes[fut] == True and self.place_bids[token.split('-')[0]] == True:
                                self.blockers[fut] = True
                                self.maybes[fut] = False
                                r = Timer(wait_seconds, self.resetBlocker, (token))
                                pprint('block ' + token + ' for ' + str(wait_seconds))
                                r.start()    
                                
                        pprint('ftx buy')
                        gogo = False
                        if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                        else: 
                            gogo = True    
                        if gogo == True: 
                            
                            self.ftx.createOrder(  fut + '-PERP', "limit", 'buy', self.qty, self.get_bbo('ftx', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)}   )
                            
                    
                    pprint(self.qty * prc + -1 * self.skew_size[token])
                    if  token in fut and self.place_asks[token.split('-')[0]] == True and  self.qty * prc + (self.skew_size[splittok]) > -1 *  self.MAX_SKEW:
                         gogo = False
                         if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                         else: 
                            gogo = True    
                         if gogo == True:
                            pprint('ftxftx fut sell')
                            try:
                                self.ftx.createOrder( self.arbmult[token]['short'], "limit", 'sell', self.qty, self.get_bbo('ftx', self.arbmult[token]['short'])['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)}   )
                            except:
                                abc=123   
        # Long add on winning ex, short other ex - or rather 
            elif ex == self.arbmult[token]['long']:     
                #print(str(self.PCT_LIM_LONG[token]) + ' Ok! ' + ex + ' wins! They can long! ' + str(self.place_bids[token.split('-')[0]]) + ' ' + str(self.IM))
                if ex == 'binance':
                    afut = ""
                    pprint(self.MAX_SKEW)
                    pprint(self.qty * prc + self.skew_size[token])

                    if (reducing == False and token in fut and  self.qty * prc + (self.skew_size[token]) <  self.MAX_SKEW  and self.place_bids[token.split('-')[0]] == True) and (math.fabs(self.positions[token + '-ftx']['size']) / math.fabs(self.positions[token + '-binance']['size']) < 1.33):
                        afut = fut
                        if fut in self.maybes :
                            if self.maybes[fut] == True and self.place_bids[token.split('-')[0]] == True:
                                self.blockers[fut] = True
                                self.maybes[fut] = False
                                r = Timer(wait_seconds, self.resetBlocker, (token))
                                pprint('block ' + token + ' for ' + str(wait_seconds))
                                r.start()    
                                
                        pprint('binbin buy')
                        gogo = False
                        if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                        else: 
                            gogo = True    
                        if gogo == True: 
                            
                            self.binance.createOrder(  fut + '/USDT', "Limit", 'buy', self.qty, self.get_bbo('binance', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)})
                        
                    pprint(self.qty * prc + -1 * self.skew_size[token])
                    if  token in fut and self.place_asks[token.split('-')[0]] == True and  self.qty * prc + (self.skew_size[token]) > -1 *  self.MAX_SKEW and math.fabs(self.positions[token + '-ftx']['size']) / math.fabs(self.positions[token + '-binance']['size']) > 0.75:
                         gogo = False
                         if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                         else: 
                            gogo = True    
                         if gogo == True:
                            pprint('ftxftx sell')
                            
                            self.ftx.createOrder(  fut + '-PERP', "limit", 'sell', self.qty, self.get_bbo('ftx', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)}   )
                             
                #print(str(self.PCT_LIM_LONG[token]) + ' Ok! ' + ex + ' wins! They can long! ' + str(self.place_bids[token.split('-')[0]]) + ' ' + str(self.IM))
                if ex == 'ftx':
                    afut = ""
                    pprint(self.MAX_SKEW)
                    pprint(self.qty * prc + self.skew_size[token])
                    if (reducing == False and token in fut and  self.qty * prc + (self.skew_size[token]) <  self.MAX_SKEW  and self.place_bids[token.split('-')[0]] == True) and (math.fabs(self.positions[token + '-ftx']['size']) / math.fabs(self.positions[token + '-binance']['size']) < 1.33):
                        afut = fut
                        if fut in self.maybes :
                            if self.maybes[fut] == True and self.place_bids[token.split('-')[0]] == True:
                                self.blockers[fut] = True
                                self.maybes[fut] = False
                                r = Timer(wait_seconds, self.resetBlocker, (token))
                                pprint('block ' + token + ' for ' + str(wait_seconds))
                                r.start()    
                                
                        pprint('ftx buy')
                        gogo = False
                        if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                        else: 
                            gogo = True    
                        if gogo == True: 
                            
                            self.ftx.createOrder(  fut + '-PERP', "limit", 'buy', self.qty, self.get_bbo('ftx', fut)['ask'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)}   )
                            
                    
                    pprint(self.qty * prc + -1 * self.skew_size[token])
                    if  token in fut and self.place_asks[token.split('-')[0]] == True and  self.qty * prc + (self.skew_size[token]) > -1 *  self.MAX_SKEW and math.fabs(self.positions[token + '-ftx']['size']) / math.fabs(self.positions[token + '-binance']['size']) > 0.75:
                         gogo = False
                         if fut in self.blockers:
                            if self.blockers[fut] == False:
                                gogo = True
                         else: 
                            gogo = True    
                         if gogo == True:
                            pprint('bin sell')
                            
                            self.binance.createOrder(  fut + '/USDT', "Limit", 'sell', self.qty, self.get_bbo('binance', fut)['bid'], {"newClientOrderId": "x-v0tiKJjj-" + self.randomword(15)}) 
                                    
        except:
            self.printException()
            self.execute_cancels(ex, fut, nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords)


    def execute_shorts ( self, prc, splittok, token, ex, fut, nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords):
        delta = datetime.timedelta(hours=1)
        now = datetime.datetime.now()
        next_hour = (now + delta).replace(microsecond=0, second=0, minute=7)

        self.execute_cancels(ex, fut, nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords)
        
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
                    pprint(e)
        if ex == 'ftx':
            if '-' in pair:
                ords        = self.ftx.fetchOpenOrders( pair )
            else:    
                ords        = self.ftx.fetchOpenOrders( pair + '-PERP')
            for order in ords:
                ###print(order)
                oid = order ['info'] ['id']
               # ##print(order)
                try:
                    
                    self.ftx.cancelOrder( oid , pair )
                except Exception as e:
                    pprint(e)
    def execute_cancels(self, ex, fut, nbids, nasks,  bids, asks, bid_ords, ask_ords, qtybtc, con_sz, cancel_oids, len_bid_ords, len_ask_ords):
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
                    self.printException()
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
            self.printException()
            pass
        finally:
            os.execv( sys.executable, [ sys.executable ] + sys.argv )        
            
    

    
    def run( self ):
        
        self.run_first()
        self.update_positions() 
        self.output_status()
        ##print('run')    
        t_ts = t_out = t_loop = t_mtime = datetime.datetime.utcnow()

        while True:
            self.rateCounter = self.rateCounter + 1

            #for fut in self.futures:
            #    self.cancelall(fut, 'ftx')
            #for fut in self.futures:
            #    self.cancelall(fut, 'binance')
            if self.rateCounter == 10:
                self.rateCounter = 0
                self.update_rates()
            self.update_balances()    
            self.update_positions()
        
            t_now   = datetime.datetime.utcnow()
            self.skew_size = {}
            
            
            
            # Update time series and vols

            self.place_orders('binance')
            self.update_positions()
            self.output_status()
            #self.output_status();
            self.place_orders('ftx')
            self.output_status()
            ###print('out of sleep!')

            
             
            
    def run_first( self ):
        
        self.create_client()
        self.get_bin_futures()
        self.update_balances()
        
        
                
        self.logger = get_logger( 'root', LOG_LEVEL )
        # Get all futures contracts
        
        self.update_rates() 
        #self.update_positions() 
        t = threading.Thread(name='positions',target=self.update_bin_pos, args=())
        t.start()
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
        for fut in self.futures:
            self.cancelall(fut, 'ftx')
        for fut in self.futures:
            self.cancelall(fut, 'binance')
         
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
            if '-' in pair:
                self.positions[pair] = {
                'size':         2,
                'sizeBtc':      0,
                'averagePrice': None,
                'floatingPl': 0}    
            else:
                self.positions[pair + '-ftx'] = {
                'size':         2,
                'sizeBtc':      0,
                'averagePrice': None,
                'floatingPl': 0}
        for pair in self.active:
            if '-' in pair:
                self.positions[pair] = {
                'size':         2,
                'sizeBtc':      0,
                'averagePrice': None,
                'floatingPl': 0}    
            else:
                self.positions[pair + '-binance'] = {
                'size':         2,
                'sizeBtc':      0,
                'averagePrice': None,
                'floatingPl': 0}


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
        ex='ftx'
        try:
            positions       = self.ftx.privateGetPositions()['result']
            ###print(self.futures)
            for pos in positions:
                ###print('ftx pos')
                
                pos['future'] = pos['future'].replace('-PERP', '')
                pos['floatingPl'] = pos['unrealizedPnl']
                if pos['entryPrice'] is not None:
                    pos['size'] = float(pos['netSize']) * (pos['entryPrice'])
                else:
                    pos['size'] = 0
                #if pos['size'] == 0:
                #    pos['size'] = 2
                if pos['size'] != 0:
                    if '-' in pos[ 'future' ]:
                        self.positions[ pos[ 'future' ]] = pos
                    else:
                        self.positions[ pos[ 'future' ] + '-ftx'] = pos


        except:
            self.printException()
                
if __name__ == '__main__':
    
    ##print('hello world')
    try:
        try:
            os.rename('log.txt', 'log-' + str(start_time) + '.txt')
        except Exception as e:
            abc123 = 1
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
        sys.exit()
        if args.restart:
            mmbot.restart()
        