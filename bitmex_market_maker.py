# This code is for sample purposes only, comes as is and with no warranty or guarantee of performance

from collections    import OrderedDict
from datetime       import datetime
from os.path        import getmtime
from time           import sleep
from datetime import date, timedelta
from utils          import ( get_logger, lag, print_dict, print_dict_of_dicts, sort_by_key,
                             ticksize_ceil, ticksize_floor, ticksize_round )
import requests
import json
import copy as cp

import random, string
import argparse, logging, math, os, pathlib, sys, time, traceback
testing = False
import bitmex
import ccxt
import inspect  
import linecache
def PrintException():
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    lineno = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno, f.f_globals)
    string = 'EXCEPTION IN ({}, LINE {} "{}"): {}'.format(filename, lineno, line.strip(), exc_obj)
    print(string)


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
#if 'KEY' in os.environ:
KEY     = "sGHr0ll5Nma3kfpLc9Y6ulFZ" ##os.environ['KEY']
SECRET  = "s7AZmA4mHBaH4leAsQjRUCdy_Z-VnHRWIF1B75rm6oRMeQOs" #os.environ['SECRET']
LEVERAGE_MAX = 40
#else:
#    KEY     = ""#"Ef30Pt3-"#"VC4d7Pj1"#
#    SECRET  = ""#"TdREcHubAr4cPh-WwifNI0Y1iGdq3YjedsO-8ct-Fhw"#"IB4VEP26OzTNUt4JhNILOW9aDuzctbGs_K6izxQG2dI"#
URL     = 'https://www.deribit.com'

BP                  = 1e-4      # one basis point
BTC_SYMBOL          = 'btc'
CONTRACT_SIZE       = 10        # USD
COV_RETURN_CAP      = 1000       # cap on variance for vol estimate
DECAY_POS_LIM       = 0.1       # position lim decay factor toward expiry
EWMA_WGT_COV        = 70         # parameter in % points for EWMA volatility estimate
EWMA_WGT_LOOPTIME   = 1.1       # parameter for EWMA looptime estimate
FORECAST_RETURN_CAP = 200       # cap on returns for vol estimate
LOG_LEVEL           = logging.INFO
MIN_ORDER_SIZE      = 25 # for mults of orders by x1.25 and x1.5, 3 is the absolute min. contracts to buy (rounds to 4, 5 with mults)
MAX_LAYERS          =  2        # max orders to layer the ob with on each side
MKT_IMPACT          =  0     # base 1-sided spread between bid/offer
NLAGS               =  2        # number of lags in time series
PCT                 = 100 * BP  # one percentage point

PCT_QTY_BASE        = 100       # pct order qty in bps as pct of acct on each order
MIN_LOOP_TIME       =   0.2       # Minimum time between loops
RISK_CHARGE_VOL     =  2.25      # vol risk charge in bps per 100 vol
SECONDS_IN_DAY      = 3600 * 24
SECONDS_IN_YEAR     = 365 * SECONDS_IN_DAY
WAVELEN_MTIME_CHK   = 15        # time in seconds between check for file change
WAVELEN_OUT         = 15        # time in seconds between output to terminal
WAVELEN_TS          = 15        # time in seconds between time series update
VOL_PRIOR           = 40       # vol estimation starting level in percentage pts

EWMA_WGT_COV        *= PCT
MKT_IMPACT          *= BP

PCT_QTY_BASE        *= BP
VOL_PRIOR           *= PCT

class Testing ( object ):
    def __init__( self ):
        passed = 0
        failed = 0
        mmbot = MarketMaker( monitor = args.monitor, output = args.output, testing = True)
        mmbot.futures = OrderedDict([('BTC-25SEP20', {'kind': 'future', 'baseCurrency': 'BTC', 'currency': 'USD', 'minTradeSize': 1.0, 'minTradeAmount': 10.0, 'instrumentName': 'BTC-25SEP20', 'isActive': True, 'settlement': 'month', 'created': '2020-03-02 08:06:44 GMT', 'tickSize': 0.5, 'pricePrecision': 1, 'expiration': '2020-09-25 08:00:00 GMT', 'contractSize': 10.0, 'expi_dt': datetime(2020, 9, 25, 8, 0)}), ('BTC-26JUN20', {'kind': 'future', 'baseCurrency': 'BTC', 'currency': 'USD', 'minTradeSize': 1.0, 'minTradeAmount': 10.0, 'instrumentName': 'BTC-26JUN20', 'isActive': True, 'settlement': 'month', 'created': '2019-12-20 09:00:20 GMT', 'tickSize': 0.5, 'pricePrecision': 1, 'expiration': '2020-06-26 08:00:00 GMT', 'contractSize': 10.0, 'expi_dt': datetime(2020, 6, 26, 8, 0)}), ('BTC-PERPETUAL', {'kind': 'future', 'baseCurrency': 'BTC', 'currency': 'USD', 'minTradeSize': 1.0, 'minTradeAmount': 10.0, 'instrumentName': 'BTC-PERPETUAL', 'isActive': True, 'settlement': 'perpetual', 'created': '2018-08-14 10:24:47 GMT', 'tickSize': 0.5, 'pricePrecision': 1, 'expiration': '3000-01-01 08:00:00 GMT', 'contractSize': 10.0, 'expi_dt': datetime(3000, 1, 1, 8, 0)})])
        mmbot.MAX_SKEW = 60.64390812091921
        mmbot.arbmult = {'BTC-25SEP20': {'arb': 1.5, 'long': 'others', 'short': 'BTC-25SEP20'}, 'BTC-26JUN20': {'arb': 0.5, 'long': 'others', 'short': 'BTC-25SEP20'}, 'BTC-PERPETUAL': {'arb': 0.5, 'long': 'others', 'short': 'BTC-25SEP20'}}

        mmbot.positions  = OrderedDict( { f: {
            'size':         0,
            'sizeBtc':      0,
            'indexPrice':   None,
            'markPrice':    None
        } for f in mmbot.futures.keys() } )

        

        # All 0 Positions market into arb 

        orders = mmbot.run()
        #print(orders)
        if orders == [{'BTC-25SEP20', 'false', 6986.175, 20.333333333333332, 'sell'}, {'false', 40.333333333333336, 7212.675, 'BTC-26JUN20', 'buy'}, {6945.505, 'false', 'BTC-PERPETUAL', 20.333333333333332, 'sell'}]:
            passed = passed + 1
            #print('All 0 Positions market into arb test pass, ' + str(passed) + ' / ' + str(failed) +' tests pass/fail...')


class MarketMaker( object ):
    
    def __init__( self, monitor = True, output = True, testing = False ):

        self.testing = testing
        self.returnOrders = []
        self.theeps = None
        self.PCT_LIM_LONG        = 20       # % position limit long

        self.PCT_LIM_SHORT       = 20       # % position limit short
        self.MAX_SKEW = MIN_ORDER_SIZE * 1.1 

        self.equity_usd         = None
        self.equity_btc         = None
        self.equity_usd_init    = None
        self.equity_btc_init    = None
        self.con_size           = float( CONTRACT_SIZE )
        self.client             = None
        self.mex = bitmex.bitmex(test=False, api_key=KEY, api_secret=SECRET)
        self.place_asks = {}
        self.place_bids = {}
        self.LEV_LIM = {}
        self.mexfundingfirst = True
        self.exchangeRates = {}
        self.skew_size = {}
        self.maxMaxDD = 20
        self.minMaxDD = -8
        self.seriesData = {}
        self.seriesData[(datetime.strptime((date.today() - timedelta(days=1)).strftime('%Y-%m-%d'), '%Y-%m-%d'))] = 0
            
        self.startUsd = 0
        self.IM = 0
        self.LEV = 0
        self.tradeids = []
        self.amounts = 0
        self.fees = 0
        self.startTime = int(time.time()*1000)
        self.arbmult = {}

        self.deltas             = OrderedDict()
        self.futures            = OrderedDict()
        self.futures_prv        = OrderedDict()
        self.logger             = None
        self.mean_looptime      = 1
        self.monitor            = monitor
        self.output             = output or monitor
        self.positions          = OrderedDict()
        self.spread_data        = None
        self.this_mtime         = None
        self.ts                 = None
        self.vols               = OrderedDict()
    
    
    def create_client( self ):
        self.client = ccxt.bitmex({  'enableRateLimit': True, 'rateLimit': 3000, "apiKey": KEY,
    "secret": SECRET})    
        #### TESTNET TO WWW
        #print(dir(self.client))  
        #self.client.urls['api'] = self.client.urls['test']
    
    def get_bbo( self, contract ): # Get best b/o excluding own orders
        if self.testing == False:
            # Get orderbook
            if 'contract' == 'BTC/USD':
                contract = 'XBTUSD'
            if 'contract' == 'ETH/USD':
                contract = 'XBTUSD'
            if 'contract' == 'XRP/USD':
                contract = 'XRPUSD'
            #print(contract)
            t = requests.get('http://localhost:4444/instrument?symbol=' + contract).json()[0]
            
            ask_mkt = t['askPrice']
            bid_mkt = t['bidPrice']
            if '.B' in contract:
                ask_mkt = t['markPrice']
                bid_mkt = t['markPrice']
            nbids = MAX_LAYERS 
            nasks = MAX_LAYERS 
            
            if bid_mkt is None and ask_mkt is None:
                bid_mkt = ask_mkt = spot
            elif bid_mkt is None:
                bid_mkt = min( spot, ask_mkt )
            elif ask_mkt is None:
                ask_mkt = max( spot, bid_mkt )
            mid_mkt = 0.5 * ( bid_mkt + ask_mkt )
            """
            ords        = self.client.getopenorders( contract )
            bid_ords    = [ o for o in ords if o[ 'direction' ] == 'buy'  ]
            ask_ords    = [ o for o in ords if o[ 'direction' ] == 'sell' ]
            best_bid    = None
            best_ask    = None

            err = 10 ** -( self.get_precision( contract ) + 1 )
            
            for b in bids:
                match_qty   = sum( [ 
                    o[ 'quantity' ] for o in bid_ords 
                    if math.fabs( b[ 'price' ] - o[ 'price' ] ) < err
                ] )
                if match_qty < b[ 'quantity' ]:
                    best_bid = b[ 'price' ]
                    break
            
            for a in asks:
                match_qty   = sum( [ 
                    o[ 'quantity' ] for o in ask_ords 
                    if math.fabs( a[ 'price' ] - o[ 'price' ] ) < err
                ] )
                if match_qty < a[ 'quantity' ]:
                    best_ask = a[ 'price' ]
                    break
                    """
            tsz = t['tickSize']           
            # Perform pricing
            if '.B' not in contract:
                vol = max( self.vols[ BTC_SYMBOL ], self.vols[ contract ] )
                eps = BP * vol * (RISK_CHARGE_VOL)
            else:
                vol = self.vols[ BTC_SYMBOL ]
                eps = BP * vol * (RISK_CHARGE_VOL)
            riskfac     = math.exp( eps )
                    

            
            
            bid0            = mid_mkt * math.exp( -MKT_IMPACT )
            bids    = [ bid0 * riskfac ** -i for i in range( 1, int(nbids) + 1 ) ]
         

            bids[ 0 ]   = ticksize_floor( bids[ 0 ], tsz )
            
            ask0            = mid_mkt * math.exp(  MKT_IMPACT )
             
            asks    = [ ask0 * riskfac ** i for i in range( 1, int(nasks) + 1 ) ]


            asks[ 0 ]   = ticksize_ceil( asks[ 0 ], tsz  )
            
            best_bid    = bids[0]
            best_ask    = asks[0]

            return { 'bid': best_bid, 'ask': best_ask, 'bids': bids, 'asks': asks }
        else:
            if contract == 'BTC-PERPETUAL':
                return{'bid': 7086.0, 'ask': 7088.5, 'bids': [7086.0, 7085.124143894359], 'asks': [7088.5, 7089.376493958146]}
            if contract == 'BTC-25SEP20':
                return{'bid': 7127.5, 'ask': 7130.0, 'bids': [7127.5, 7126.611695761672], 'asks': [7130.0, 7130.888945825834]}
            if contract == 'BTC-26JUN20':
                return{'bid': 7070.0, 'ask': 7072.5, 'bids': [7070.0, 7069.128943174431], 'asks': [7072.5, 7073.371693238075]}

        
    def get_futures( self ): # Get all current futures instruments
        
        self.futures_prv    = cp.deepcopy( self.futures )
        insts               = self.client.fetchMarkets()
        #print(insts[0])
        self.futures        = sort_by_key( { 
            i[ 'symbol' ]: i for i in insts if 'BTC/USD' in i['symbol'] or ('XBT' in i['symbol'] and '7D' not in i['symbol']) and '.' not in i['symbol']    or ('XRP' in i['symbol'] and 'BTC' not in i['symbol'] and '7D' not in i['symbol']) and '.' not in i['symbol'] and len(i['symbol']) <= 8 #or ('ETH' in i['symbol'] and 'BTC' not in i['symbol'] and '7D' not in i['symbol']) and '.' not in i['symbol'] and len(i['symbol']) <= 8  
        } )
        self.futures['XBTUSD'] = self.futures['BTC/USD']
        del self.futures['BTC/USD']
        if 'ETH/USD' in self.futures:
            self.futures['ETHUSD'] = self.futures['ETH/USD']
            del self.futures['ETH/USD']
        if 'XRP/USD' in self.futures:
            self.futures['XRPUSD'] = self.futures['XRP/USD']
            del self.futures['XRP/USD']
            
        #print(self.futures.keys())
        #print(self.futures['XBTH20'])
        for k in self.futures.keys():
            if self.futures[k]['info']['expiry'] == None:
                self.futures[k][ 'expi_dt' ] = datetime.strptime( 
                                    '3000-01-01 15:00:00', 
                                    '%Y-%m-%d %H:%M:%S')
            else:
                self.futures[k][ 'expi_dt' ] = datetime.strptime( 
                                    self.futures[k]['info']['expiry'][ : -5 ], 
                                    '%Y-%m-%dT%H:%M:%S')
            #print(self.futures[k][ 'expi_dt' ])
        #for k, v in self.futures.items():
            #self.futures[ k ][ 'expi_dt' ] = datetime.strptime( 
            #                                   v[ 'expiration' ][ : -4 ], 
            #                                   '%Y-%m-%d %H:%M:%S' )
                        
        
                        
        #print(self.futures)
    def get_pct_delta( self ):         
        self.update_status()
        return sum( self.deltas.values()) / self.equity_btc

    
    def get_spot( self ):
        return self.get_bbo('XBTUSD')['bid']

    
    def get_precision( self, contract ):
        return self.futures[ contract ] ['precision' ] ['price']

    
    def get_ticksize( self, contract ):
        return self.futures[ contract ]['info'][ 'tickSize' ]
    
    def get_multiplier( self, contract ):
        contract2 = contract.replace('/','')
        if 'XBT' in contract:
            return ( 1 )
        return (self.get_bbo(contract2)['bid'] * self.futures[ contract ]['info']['multiplier']  / 100000000) /  self.get_bbo(".B" + contract[0:3] + "XBT")['bid']  
    
    
    def output_status( self ):
        
        if not self.output:
            return None
        
        self.update_status()
        
        now     = datetime.utcnow()
        days    = ( now - self.start_time ).total_seconds() / SECONDS_IN_DAY
        print     (     '********************************************************************' )
        print     (     'Start Time:        %s' % self.start_time.strftime( '%Y-%m-%d %H:%M:%S' ))
        print     (     'Current Time:      %s' % now.strftime( '%Y-%m-%d %H:%M:%S' ))
        print     (     'Days:              %s' % round( days, 1 ))
        print     (     'Hours:             %s' % round( days * 24, 1 ))
        print     (     'Spot Price:        %s' % self.get_spot())
        
        
        pnl_usd = self.equity_usd - self.equity_usd_init
        pnl_btc = self.equity_btc - self.equity_btc_init
        
        print     (     'Equity ($):        %7.2f'   % self.equity_usd)
        print     (     'P&L ($)            %7.2f'   % pnl_usd)
        print     (     'Equity (BTC):      %7.4f'   % self.equity_btc)
        print     (     'P&L (BTC)          %7.4f'   % pnl_btc)
        
        #print_dict_of_dicts( {
        #    k: {
        #        '$USD': self.positions[ k ][ 'size' ]
        #    } for k in self.positions.keys()
        #    }, 
        #    title = 'Positions' )
        ##print(self.positions)
        t = 0
        a = 0
        for k in self.positions:
            self.skew_size[k[0:3]] = 0

        for k in self.positions:
            self.skew_size[k[0:3]] = self.skew_size[k[0:3]] + self.positions[k]['size']
        print(' ')
        print('Skew')

        for pos in self.skew_size:
        

            print     (     pos + ': $' + str( self.skew_size[pos]))

        print(' ')
        print('Positions')
        for pos in self.positions:
        
            a = a + math.fabs(self.positions[pos]['size'])
            t = t + self.positions[pos]['size']

            print     (     pos + ': $' + str( self.positions[pos]['size']))

        print     (     '\nNet delta (exposure) BTC: $' + str(t))
        print     (     'Total absolute delta (IM exposure) BTC: $' + str(a))
        

        print     (     '(Roughly) initial margin across futs: ' + str(self.IM) + '% and (actual) leverage is ' + str(round(self.LEV * 1000)/1000) + 'x')
        print     (     'Max skew is: $' + str(self.MAX_SKEW))

        if not self.monitor:
            print_dict_of_dicts( {
                k: {
                    '%': self.vols[ k ]
                } for k in self.vols.keys()
                }, 
                multiple = 100, title = 'Vols' )

            print     (     '\nMean Loop Time: %s' % round( self.mean_looptime, 2 ))
            
        ##print( '' )

        
    def place_orders( self ):
        try:
            if self.monitor:
                return None
            
            con_sz  = self.con_size        
            
            for fut in self.futures.keys():
                for k in self.positions:
                    self.skew_size[k[0:3]] = 0
                ##print('skew_size: ' + str(self.skew_size))
                ##print(self.positions)
                for k in self.positions:
                    self.skew_size[k[0:3]] = self.skew_size[k[0:3]] + self.positions[k]['size']
                    ##print('skew_size: ' + str(self.skew_size))
                #print(self.skew_size)
                res = requests.get("http://localhost:4444/margin").json()[0]
                
                bal = res['amount'] / 100000000

                spot            = self.get_spot()
                bal_btc         = bal
                pos             = self.positions[ fut ][ 'sizeBtc' ]
                
                nbids = MAX_LAYERS 
                nasks = MAX_LAYERS 
                
                
                self.place_bids[fut[0:3]] = True
                self.place_asks[fut[0:3]] = True
                #print(self.PCT_LIM_LONG)
                a = {}
                for pos in self.positions:
                    a[pos[0:3]] = 0
                
                for pos in self.positions:
                    a[pos[0:3]] = a[pos[0:3]] + math.fabs(self.positions[pos]['size'])
                
                for pos in self.positions:
                    if self.LEV_LIM[pos[0:3]] == 0:
                        print('lev lim 0!')
                        self.place_asks[pos[0:3]] = False
                        self.place_bids[pos[0:3]] = False
                    elif (((a[pos[0:3]] / self.equity_usd) / self.LEV_LIM[pos[0:3]] * 1000 ) / 10 ) > 100:
                        self.place_asks[pos[0:3]]= False
                        self.place_bids[pos[0:3]] = False
                
                qtybtc = ""
                #qtybtc = float(max( PCT_QTY_BASE  * bal_btc, (MIN_ORDER_SIZE * 10) / spot))
                ##print('qtybtc: ' + str(qtybtc))

                
                
                ##print('place_x2')
                ##print(place_bids2)
                ##print(place_asks2)
                ##print(place_bids)
                ##print(place_asks)

                positionGains = {}
                positionPrices = {}
                for ifut in self.futures.keys():
                    if ifut not in positionPrices:
                        positionPrices[ifut] = 0
                askMult = 1
                bidMult = 1
                for f in self.futures.keys():
                    positionGains[f] = True
                for p in self.positions:
                
                    if self.positions[p]['floatingPl'] > 0:
                        positionGains[self.positions[p]['instrument']] = True
                    else:
                        positionGains[self.positions[p]['instrument']] = False
                    positionPrices[self.positions[p]['instrument']] = self.positions[p]['averagePrice']    


                
                for pos in self.positions:
                    if self.place_asks[fut[0:3]] == False:
                        abc=123#print(fut + ' place_asks false!')

                    if self.place_bids[fut[0:3]] == False:
                        abc=123#print(fut + ' place_bids false!')
                tsz = self.get_ticksize( fut )            
                # Perform pricing
                vol = max( self.vols[ BTC_SYMBOL ], self.vols[ fut ] )
                
                eps         = BP * vol * (RISK_CHARGE_VOL)
                riskfac     = math.exp( eps )

                bbo     = self.get_bbo( fut )
                bids = bbo['bids']
                asks = bbo['asks']
                ex = 'bitmex'
                #self.orderStates[ex] = []
                ords = []
                bid_ords = []
                ask_ords = []
                future321 = fut.replace('/','').replace('BTC','XBT')
                
                orders = requests.get("http://localhost:4444/order?symbol=" + future321).json()
            
                    
                for order in orders:   

                    order['direction'] = order['side']   
                    #print(order)
                    order['qty'] = order['orderQty']
                    order['status'] = order['ordStatus']
                    if order['ordStatus'].lower() == 'new':
                        #print('bitmex order!')
                        #print('mex order')

                        order['status'] = 'new'
                           
                    
                        if order[ 'side' ].lower() == 'buy':
                            bid_ords.append(order)
                            #print(order)
                        elif order[ 'side' ].lower() == 'sell':
                            ask_ords.append(order)
                            #print(order)
             
                cancel_oids = []
                
                ##print(fut)
                ##print(fut)
                ##print(fut)
                ##print(fut)
                ##print(fut)
                ##print(fut)

                ##print(positionSkew)
                ##print(overPosLimit)
                ##print(overPosLimit)
                ##print(place_asks)
                ##print(positionGains[fut])
                

                ##print(positionPrices[fut])
                ##print(bid_mkt)
                ##print(ask_mkt)
                #sleep(60 * 60)
            
                len_bid_ords    = len( bid_ords )
                #print('len_bid_ords ' + str(len_bid_ords))
                
                
                   
                len_ask_ords    = len( ask_ords )
                #print('len_ask_ords ' + str(len_ask_ords))
                bbo = self.get_bbo( fut )
                bids = bbo[ 'bids' ]
                asks = bbo[ 'asks' ]
                editOrds = []
                for i in range( 0, MAX_LAYERS ):
                    try:
                        if  len(bid_ords) > i:
                            oid = bid_ords[ i ][ 'orderID' ]
                        
                            editOrds.append({"orderID":oid, "price": ticksize_floor( bids[i], self.get_ticksize( fut ) )})#( oid, qty, prc )
                    except Exception as e:
                        PrintException()
                    try:
                        if len(ask_ords) > i:
                            oid = ask_ords[ i ][ 'orderID' ]
                            
                            editOrds.append({"orderID":oid, "price": ticksize_ceil( asks[i], self.get_ticksize( fut ) )})#self.client.edit( oid, qty, prc )
                    except Exception as e:
                        PrintException()
                if len(editOrds) > 0:
                    sleep(len(editOrds) * MAX_LAYERS * 0.2)


                    #print('edit!')
                    try:
                        r = self.mex.Order.Order_amendBulk(orders=json.dumps(editOrds)).result()
                    except:
                        PrintException()
                    #print('amend')
                    #print(r)
                if self.place_asks[fut[0:3]] == False and self.place_bids[fut[0:3]] == False:
                    try:
                        
                        prc = self.get_bbo(fut)['bid']
                        
                        qty = self.equity_usd / 48  / 10 / 2
                        qty = float(max( qty, MIN_ORDER_SIZE))
                        # 
                        #print('qty: ' + str(qty))    
                        #print(max_bad_arb)
                        
                        qty = round(qty)  
                        for k in self.positions:
                            self.skew_size[k[0:3]] = 0

                        for k in self.positions:
                            self.skew_size[k[0:3]] = self.skew_size[k[0:3]] + self.positions[k]['size'] 
                        token = fut[0:3] 
                        if 'ETH' in fut or 'XRP' in fut:
                            qty = qty / self.get_bbo(fut[0:3] + 'USD')['bid']
                            if 'USD' in fut:
                                qty = qty / self.get_multiplier(fut)
                            if qty <= 1:
                                qty = 1

                        if self.positions[fut]['size'] >= 0:
                            if qty + self.skew_size[token] * -1 <= self.MAX_SKEW:
                                mexAsks = []
                                for i in range(len_ask_ords, round(MAX_LAYERS)):
                                    mexAsks.append({"symbol":fut, "orderQty":-1*round(qty), "price":ticksize_ceil( asks[i], self.get_ticksize( fut ) ),"execInst":"ParticipateDoNotInitiate"})
                                
                                if  len(mexAsks) > 0:
                                    #if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                                        
                                        sleep(len(mexAsks) * MAX_LAYERS * 0.2)
                                        r = self.mex.Order.Order_newBulk(orders=json.dumps(mexAsks)).result()
                                           #print(r)s
                            

                        if self.positions[fut]['size'] <= 0:
                            if qty + self.skew_size[token] <= self.MAX_SKEW:

                                mexBids = []
                                for i in range(len_bid_ords, round(MAX_LAYERS)):
                                    mexBids.append({"symbol":fut, "orderQty":round(qty), "price":ticksize_floor( bids[i], self.get_ticksize( fut )  ),"execInst":"ParticipateDoNotInitiate"})
                               
                                if  len(mexBids) > 0:
                                    #if self.qty + skew_size[token] <= self.MAX_SKEW:

                                        sleep(len(mexBids) * MAX_LAYERS * 0.2)
                                        r = self.mex.Order.Order_newBulk(orders=json.dumps(mexBids)).result()
                                            #print(r)
                                           #print(r)
                                
                    except:
                        PrintException()
                    
                    
                    
                self.theeps = eps
                intermediary = {}
                intermediary['vols'] = self.vols
                intermediary['eps'] = self.theeps
                with open('intermediaryvalues.json', 'w') as outfile:
                    json.dump(intermediary, outfile)

                ##print(fut)
                #print('place')
                
                #print(place_bids)
                #print(place_bids2)
                #print(nbids)
                #print(nbids2)
                #print(' ')
                #print(self.place_bids[fut[0:3]])
                #print(' ')
                if self.place_bids[fut[0:3]] == True:
                    self.execute_bids (fut, nbids, nasks, bids, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords, askMult, bidMult)    
                
                if self.place_asks[fut[0:3]] == True:
                    self.execute_offers (fut, nbids, nasks, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords, askMult, bidMult)    
        except:
            PrintException()                            
    def execute_bids ( self, fut, nbids, nasks, bids, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords, askMult, bidMult):
        try:
            buyOrds = []
            #print(' ')
            #print(MAX_LAYERS)
            #print(nbids)
            #print( ' ')
            #print('# BIDS')
            for i in range( 0, MAX_LAYERS ):
                if i < nbids:
                    #print(i)
                    if i > 0:
                        prc = ticksize_floor( min( bids[ i ], bids[ i - 1 ] - tsz ), tsz )
                    else:
                        prc = bids[ 0 ]

                    #qty = ( prc * qtybtc / con_sz )  
                    qty = self.equity_usd / 48  / 10 / 2
                    qty = float(max( qty, MIN_ORDER_SIZE))
                    max_bad_arb = int(self.MAX_SKEW )
                    # 
                    #print('qty: ' + str(qty))    
                    #print(max_bad_arb)
                    qty = qty * bidMult
                    qty = round(qty)              
                    #print('qty: ' + str(qty))       
                    if self.MAX_SKEW < qty * 1.1 :
                        self.MAX_SKEW = qty * 1.1  
                    
                    if qty + self.skew_size[fut[0:3]] >  self.MAX_SKEW:
                        #print(fut+ ' bid self.MAX_SKEW return ...')
                        for xyz in bid_ords:
                            cancel_oids.append( xyz['orderID'] )

                        #self.execute_cancels(fut, nbids, nasks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)
                            
                        return
                    #print(len_bid_ords)
                        #print('i less')
                    
                    try:
                        if 'USD' not in fut:
                            if self.arbmult[fut[0:3]]['arb'] > 0 and (self.positions[fut]['size'] - qty <= max_bad_arb ):
                                if 'ETH' in fut or 'XRP' in fut:
                                    qty = qty / self.get_bbo(fut[0:3] + 'USD')['bid']
                                    if 'USD' in fut:
                                        qty = qty / self.get_multiplier(fut)
                                    if qty <= 1:
                                        qty = 1
                                buyOrds.append({"symbol":fut, "orderQty":round(qty), "price":prc,"execInst":"ParticipateDoNotInitiate"})
                                

                            if self.arbmult[fut[0:3]]['arb'] < 0 :
                                if 'ETH' in fut or 'XRP' in fut:
                                    qty = qty / self.get_bbo(fut[0:3] + 'USD')['bid']
                                    if 'USD' in fut:
                                        qty = qty / self.get_multiplier(fut)
                                qty = int(qty * 1.1)
                                #print('buy qty * 1.1, 1' + fut)
                                if qty <= 1:
                                    qty = 1
                                buyOrds.append({"symbol":fut, "orderQty":round(qty), "price":prc,"execInst":"ParticipateDoNotInitiate"})
                        else:
                            if self.arbmult[fut[0:3]]['arb'] < 0 and (self.positions[fut]['size'] - qty <= max_bad_arb ):
                                if 'ETH' in fut or 'XRP' in fut:
                                    qty = qty / self.get_bbo(fut[0:3] + 'USD')['bid']
                                    if 'USD' in fut:
                                        qty = qty / self.get_multiplier(fut)
                                    if qty <= 1:
                                        qty = 1
                                buyOrds.append({"symbol":fut, "orderQty":round(qty), "price":prc,"execInst":"ParticipateDoNotInitiate"})
                                

                            if self.arbmult[fut[0:3]]['arb'] > 0:
                                if 'ETH' in fut or 'XRP' in fut:
                                    qty = qty / self.get_bbo(fut[0:3] + 'USD')['bid']
                                    if 'USD' in fut:
                                        qty = qty / self.get_multiplier(fut)
                                qty = int(qty * 1.1)
                                #print('buy qty * 1.1, 2' + fut)
                                if qty <= 1:
                                    qty = 1
                                buyOrds.append({"symbol":fut, "orderQty":round(qty), "price":prc,"execInst":"ParticipateDoNotInitiate"})
                                   

                            
                        
                    except (SystemExit, KeyboardInterrupt):
                        raise
                    except Exception as e:
                        PrintException()
                        self.logger.warn( 'Bid order failed: %s bid for %s'
                                        % ( prc, qty ))
                
            #print(buyOrds)
            
            if len_bid_ords < len(buyOrds):
                sleep(len(buyOrds) * MAX_LAYERS * 0.2)
                ##print('buy!')
                #print(buyOrds)
                if self.equity_usd < 2000 and fut == 'ETHM20':
                    buyOrds = [buyOrds[0]]
                r = self.mex.Order.Order_newBulk(orders=json.dumps(buyOrds)).result()
                #print('new')
                #print(r)

            if len_bid_ords > len(buyOrds):
                for index in range(MAX_LAYERS, len_bid_ords):
                    try:

                        sleep(MAX_LAYERS * 0.2)
                        self.mex.Order.Order_cancel(orderID=bid_ords[index]['orderID']).result()
                    except Exception as e:
                        PrintException()                    
            #self.execute_cancels(fut, nbids, nasks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)
        except:
            PrintException()                
    def execute_offers ( self, fut, nbids, nasks, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords, askMult, bidMult):
        try:
            sellOrds = []
            for i in range( 0, MAX_LAYERS  ):

                #print('# OFFERS')

                if i < nasks:

                    if i > 0:
                        prc = ticksize_ceil( max( asks[ i ], asks[ i - 1 ] + tsz ), tsz )
                    else:
                        prc = asks[ 0 ]
                        
                    qty = self.equity_usd / 48  / 10 / 2

                    qty = float(max( qty, MIN_ORDER_SIZE))
                    
                    #10
                    
                    max_bad_arb = int(self.MAX_SKEW )
                    #print('qty: ' + str(qty))    
                    #print(max_bad_arb)
                    

                    qty = qty * askMult
                    qty = round(qty)   
                    if self.MAX_SKEW < qty * 1.1 :
                        self.MAX_SKEW = qty * 1.1 
                    #print('qty: ' + str(qty))          
                    ##print('skew_size: ' + str(self.skew_size))
                    ##print('max_soew: ' + str(self.MAX_SKEW))
                    if qty + self.skew_size[fut[0:3]] * -1 >  self.MAX_SKEW:
                        #print(fut + ' offer self.MAX_SKEW return ...')
                        for xyz in ask_ords:
                            cancel_oids.append( xyz['orderID'] )

                            
                        #self.execute_cancels(fut, nbids, nasks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)
                        return
                    #print(len_ask_ords)

                    try:
                        if 'USD' not in fut:
                            if self.arbmult[fut[0:3]]['arb'] >= 0:
                                if 'ETH' in fut or 'XRP' in fut:
                                    qty = qty / self.get_bbo(fut[0:3] + 'USD')['bid']
                                    
                                    if 'USD' in fut:
                                        qty = qty / self.get_multiplier(fut)
                                qty = int(qty * 1.1)
                                #print('sell qty * 1.1, 1' + fut)
                                if qty <= 1:
                                    qty = 1
                                sellOrds.append({"symbol":fut, "orderQty":-1 * round(qty), "price":prc,"execInst":"ParticipateDoNotInitiate"})#self.client.sell( fut, qty, prc, 'true' )

                                
                            
                            if self.arbmult[fut[0:3]]['arb'] <= 0 and self.positions[fut]['size'] + qty * -1 >=-1 * max_bad_arb  :
                                if 'ETH' in fut or 'XRP' in fut:
                                    qty = qty / self.get_bbo(fut[0:3] + 'USD')['bid']
                                    if 'USD' in fut:
                                        qty = qty / self.get_multiplier(fut)
                                    if qty <= 1:
                                        qty = 1
                                sellOrds.append({"symbol":fut, "orderQty":-1 * round(qty), "price":prc,"execInst":"ParticipateDoNotInitiate"})#self.client.sell(  fut, qty, prc, 'true' )
                        else:
                            if self.arbmult[fut[0:3]]['arb'] <= 0:
                                if 'ETH' in fut or 'XRP' in fut:
                                    qty = qty / self.get_bbo(fut[0:3] + 'USD')['bid']
                                    
                                    if 'USD' in fut:
                                        qty = qty / self.get_multiplier(fut)
                                qty = int(qty * 1.1)
                                #print('sell qty * 1.1, 2' + fut)
                                if qty <= 1:
                                    qty = 1
                                sellOrds.append({"symbol":fut, "orderQty":-1 * round(qty), "price":prc,"execInst":"ParticipateDoNotInitiate"})#self.client.sell( fut, qty, prc, 'true' )

                                
                            
                            if self.arbmult[fut[0:3]]['arb'] >= 0 and self.positions[fut]['size'] + qty * -1 >=-1 * max_bad_arb  :
                                if 'ETH' in fut or 'XRP' in fut:
                                    qty = qty / self.get_bbo(fut[0:3] + 'USD')['bid']
                                    if 'USD' in fut:
                                        qty = qty / self.get_multiplier(fut)
                                    if qty <= 1:
                                        qty = 1
                                sellOrds.append({"symbol":fut, "orderQty":-1 * round(qty), "price":prc,"execInst":"ParticipateDoNotInitiate"})#self.client.sell(  fut, qty, prc, 'true' )

                        

                            
                    except (SystemExit, KeyboardInterrupt):
                        raise
                    except Exception as e:
                        PrintException()
                        self.logger.warn( 'Offer order failed: %s at %s'
                                        % ( qty, prc ))

                    
            
            if len_ask_ords < len(sellOrds):
                sleep(len(sellOrds) * MAX_LAYERS * 0.2)
                #print(sellOrds)
                ##print('sell!')

                if self.equity_usd < 2000 and fut == 'ETHM20':
                    sellOrds = [sellOrds[0]]
                r = self.mex.Order.Order_newBulk(orders=json.dumps(sellOrds)).result()
                #print('new')
                #print(r)
                
            if len_ask_ords > len(sellOrds):
                for index in range(MAX_LAYERS, len_ask_ords):
                    try:

                        sleep(MAX_LAYERS * 0.2)
                        self.mex.Order.Order_cancel(orderID=ask_ords[index]['orderID']).result()
                    except Exception as e:
                        PrintException()
            #self.execute_cancels(fut, nbids, nasks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)
        
        except:
            PrintException()     
    def restart( self ):        
        try:
            strMsg = 'RESTARTING'
            print( strMsg )
            if testing == False:
                self.cancelall()
            strMsg += ' '
            for i in range( 0, 5 ):
                strMsg += '.'
                ##print( strMsg )
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

            #self.get_futures()
            
            # Restart if a new contract is listed
            #if len( self.futures ) != len( self.futures_prv ):
            #    self.restart()
            
            self.update_positions()
            bbos = []
            arbs = {}
            #self.client.buy(  'BTC-PERPETUAL', size, mid * 1.02)
            expdays = {}
            for k in self.futures.keys():
                bbo     = self.get_bbo( k[0:3] + 'USD' )
                bid_mkt = bbo[ 'bid' ]
                ask_mkt = bbo[ 'ask' ]
                mid = 0.5 * ( bbo[ 'bid' ] + bbo[ 'ask' ] )

                m = self.get_bbo(k)
                
                bid = m['bid']
                ask=m['ask']
                mid1 = 0.5 * (bid + ask)
                if k == 'ETHM20' or k == 'XRPM20':
                    mid1 = mid1 * self.get_spot()
                arb = mid1 / mid
                arbs[k] = float(arb)
                #if 'USD' not in k:
                    #print('perp is ' + str(mid) + ' ' + k + ' is ' + str(mid1) + ' and arb is ' + str(arb)  + ' positive is sell negative is bbuy')
                
                expsecs = (self.futures[k]['expi_dt'] - datetime.now()).total_seconds()
                
                expday = expsecs / 60 / 24
                expdays[k]=float(expday)
                bbos.append({k: mid1 - self.get_spot()})
            try:
                r = random.randint(0, 250)
                if self.mexfundingfirst == True or r <= 5:
                    self.mexfundingfirst = False
                    res = self.mex.Instrument.Instrument_getActive().result()
                    
                    for inst in res[0]:
                        if inst['symbol'] == 'XBTUSD':
                            self.exchangeRates['XBT'] = float(inst['fundingRate']) * 3
                        if inst['symbol'] == 'ETHUSD':
                            self.exchangeRates['ETH'] = float(inst['fundingRate']) * 3
                        if inst['symbol'] == 'XRPUSD':
                            self.exchangeRates['XRP'] = float(inst['fundingRate']) * 3

            except:
                PrintException()

            fundvsprem = {}
            newarbs = {}
            for k in arbs:
                if 'USD' not in k:
                    doin = (-1*(1-arbs[k]) / expdays[k])* 100
                    #print(k[0:3])
                    #print(k + ' has a daily arb opportunity of ' + str(doin)  + '%, funding daily rate is ' + str(self.exchangeRates[k[0:3]]) + '%')
                    if math.fabs(doin) > math.fabs(self.exchangeRates[k[0:3]]):
                        #print('Premium arb wins! Premium arb is ' + str(math.fabs(doin) - math.fabs(self.exchangeRates[k[0:3]])) + ' % better right now!')
                        fundvsprem[k[0:3]] = 'premium'
                        newarbs[k[0:3]] = doin
                    else:
                        #print('Funding arb wins! Funding arb is ' + str(math.fabs(self.exchangeRates[k[0:3]]) - math.fabs(doin)) + ' % better right now!')
                        fundvsprem[k[0:3]] = 'funding' #funding
                        newarbs[k[0:3]] = self.exchangeRates[k[0:3]]
                        #longs pay shorts, shorts pay longs
                        newarbs[k[0:3]] = newarbs[k[0:3]] * -1
            arbs = newarbs
            self.arbmult = {}

            for token in arbs:
                self.arbmult[token] = {}
            for token in arbs:
                
                if arbs[token] < 0:
                    self.arbmult[token] = ({'coin': token, 'long': 'futs', 'short': 'perp', 'arb': (arbs[token])})
                else:
                    self.arbmult[token] = ({'coin': token, 'long': 'perp', 'short': 'futs', 'arb': (arbs[token])})
            #funding: {'ETH': {'coin': 'ETH', 'long': 'futs', 'short': 'perp', 'arb': -0.00030000000000000003}, 'XBT': {'coin': 'XBT', 'long': 'perp', 'short': 'futs', 'arb': 0.000153}, 'XRP': {'coin': 'XRP', 'long': 'futs', 'short': 'perp', 'arb': -0.0007440000000000001}}
            #premium: {'ETH': {'coin': 'ETH', 'long': 'futs', 'short': 'perp', 'arb': -0.00013291636050582245}, 'XBT': {'coin': 'XBT', 'long': 'perp', 'short': 'futs', 'arb': 3.722894995661838e-05}, 'XRP': {'coin': 'XRP', 'long': 'futs', 'short': 'perp', 'arb': -6.462857850516617e-05}}
            
            print(self.arbmult)
            t = 0
            c = 0
            for arb in self.arbmult:
                t = t + math.fabs(self.arbmult[arb]['arb'])

                c = c + 1
            #print('t: ' + str(t))
            
            for arb in self.arbmult:
                self.arbmult[arb]['perc'] = math.fabs(round((self.arbmult[arb]['arb']) / t * 1000) / 1000) #* 1.41425
                
            #print(self.arbmult)
            
            print(self.arbmult)
            for coin in arbs:
                self.LEV_LIM[coin] = LEVERAGE_MAX
            for coin in arbs:
                self.LEV_LIM[coin] = self.LEV_LIM[coin] * self.arbmult[coin]['perc'] 
            print(self.LEV_LIM)
            skewingpos = 0
            skewingneg = 0
            positionSize = 0
            for p in self.positions:
                positionSize = positionSize + self.positions[p]['size']
                if self.positions[p]['size'] > 0:
                    skewingpos = skewingpos + 1
                elif self.positions[p]['size'] < 0:
                    skewingneg = skewingneg + 1
            #print('pos size' + str(positionSize))
            #print('skewing')
            #print(skewingpos)
            #print(skewingneg)
            #print(self.MAX_SKEW)
            
            t_now   = datetime.utcnow()
            
            # Update time series and vols
            if ( t_now - t_ts ).total_seconds() >= WAVELEN_TS:
                t_ts = t_now
                self.update_timeseries()
                self.update_vols()
            sleep(0.01)
            size = int (100)

            self.place_orders()
            
            # Display status to terminal
            if self.output:    
                t_now   = datetime.utcnow()
                if ( t_now - t_out ).total_seconds() >= WAVELEN_OUT:
                    self.output_status(); t_out = t_now
            
            # Restart if file change detected
            t_now   = datetime.utcnow()
            if ( t_now - t_mtime ).total_seconds() > WAVELEN_MTIME_CHK:
                t_mtime = t_now
                #if getmtime( __file__ ) > self.this_mtime:
                    #self.restart()
            
            t_now       = datetime.utcnow()
            looptime    = ( t_now - t_loop ).total_seconds()
            
            # Estimate mean looptime
            w1  = EWMA_WGT_LOOPTIME
            w2  = 1.0 - w1
            t1  = looptime
            t2  = self.mean_looptime
            
            self.mean_looptime = w1 * t1 + w2 * t2
            
            t_loop      = t_now
            sleep_time  = MIN_LOOP_TIME - looptime
            if sleep_time > 0:
                time.sleep( sleep_time )
            if self.monitor:
                time.sleep( WAVELEN_OUT )

    def cancelall(self):
    
       # #print(order)
        try:
            self.mex.Order.Order_cancelAll().result()
        except Exception as e:
            PrintException()            
    def run_first( self ):
        
        self.create_client()
        if testing == False:
            self.cancelall()
        self.logger = get_logger( 'root', LOG_LEVEL )
        # Get all futures contracts
        self.get_futures()
        self.this_mtime = getmtime( __file__ )
        self.symbols    = [ BTC_SYMBOL ] + list( self.futures.keys()); self.symbols.sort()
        self.deltas     = OrderedDict( { s: None for s in self.symbols } )
        
        # Create historical time series data for estimating vol
        ts_keys = self.symbols + [ 'timestamp' ]; ts_keys.sort()
        
        self.ts = [
            OrderedDict( { f: None for f in ts_keys } ) for i in range( NLAGS + 1 )
        ]
        
        self.vols   = OrderedDict( { s: VOL_PRIOR for s in self.symbols } )
        
        self.start_time         = datetime.utcnow()
        self.update_status()
        self.equity_usd_init    = self.equity_usd
        self.equity_btc_init    = self.equity_btc
    
    
    def update_status( self ):

        gobreak = False
        breakfor = 0
        for k in self.vols.keys():
            if self.vols[k] > 10:
                gobreak = True
                breakfor = 0.25
                #print('volatility high! taking 0.25hr break')
            if self.vols[k] > 10:
                gobreak = True
                breakfor = 0.5
                #print('volatility high! taking 0.5hr break')
            if self.vols[k] > 15:
                gobreak = True
                breakfor = 1
                #print('volatility high! taking 1hr break')

        if gobreak == True:
            self.update_positions()
            self.cancelall()
            positionSize = 0
            positionPos = 0
            for p in self.positions:
                positionSize = positionSize + self.positions[p]['size']
                if self.positions[p]['size'] < 0:
                    positionPos = positionPos - self.positions[p]['size']
                else:   
                    positionPos = positionPos + self.positions[p]['size']
            if positionSize > 0:
                selling = True
                size = positionSize
            else:
                selling = False
                size = positionSize * -1
            #print('positionSize: ' + str(positionSize))
            size = size / len(self.positions)
            #print('size: ' + str(size))
            try:
                for p in self.positions:
                    sleep(0.01)

                    bbo     = self.get_bbo( self.positions[p]['instrument'] )
                    bid_mkt = bbo[ 'bid' ]
                    ask_mkt = bbo[ 'ask' ]
                    mid = 0.5 * ( bbo[ 'bid' ] + bbo[ 'ask' ] )
                    if selling:
                        prc = ticksize_floor( mid * 0.98, self.get_ticksize( self.positions[p]['instrument'] ) )

                        self.client.createOrder(  self.positions[p]['instrument'], "Limit", 'sell', -1 * size,  prc)#.sell(  self.positions[p]['instrument'], size, mid  * 0.98, 'false' )

                    else:

                        prc = ticksize_floor( mid * 1.02, self.get_ticksize( self.positions[p]['instrument'] ) )
                        self.client.createOrder(  self.positions[p]['instrument'], "Limit", 'buy', size,  mid  * prc)#.buy(  self.positions[p]['instrument'], size, mid * 1.02, 'false' )
            except Exception as e:
                PrintException()
            self.vols               = OrderedDict()
            sleep(60 * 60 * breakfor)

        if self.startUsd != 0:
            startUsd = self.startUsd + self.startUsd2 
            nowUsd = self.equity_usd + self.equity_usd2
           
            


            diff = 100 * ((nowUsd / startUsd) -1)
            ##print('diff')
            ##print(diff)
            
            if diff < self.diff2:
                self.diff2 = diff
            if diff > self.diff3:
                self.diff3 = diff
            #print('self diff2 : ' +str(self.diff2))
            #print('self diff3 : ' +str(self.diff3))
            positionSize = 0
            for p in self.positions:
                positionSize = positionSize + self.positions[p]['size']
                if self.positions[p]['size'] > 0:
                    skewingpos = skewingpos + 1
                elif self.positions[p]['size'] < 0:
                    skewingneg = skewingneg + 1
            if self.diff3 > self.maxMaxDD and self.diff3 != 0:
                #print('broke max max dd! sleep 24hr')
                self.cancelall()
                
                if positionSize > 0:
                    selling = True
                    size = positionSize
                else:
                    selling = False
                    size = positionSize * -1
                #print('size: ' + str(size))
                try:
                    for p in self.positions:
                        sleep(0.01)

                        bbo     = self.get_bbo( self.positions[p]['instrument'] )
                        bid_mkt = bbo[ 'bid' ]
                        ask_mkt = bbo[ 'ask' ]
                        mid = 0.5 * ( bbo[ 'bid' ] + bbo[ 'ask' ] )
                        if selling:
                            prc = ticksize_floor( mid * 0.98, self.get_ticksize( self.positions[p]['instrument'] ) )

                            self.client.createOrder(  self.positions[p]['instrument'], "Limit", 'sell', -1 * size,  prc)#.sell(  self.positions[p]['instrument'], size, mid  * 0.98, 'false' )

                        else:

                            prc = ticksize_floor( mid * 1.02, self.get_ticksize( self.positions[p]['instrument'] ) )
                            self.client.createOrder(  self.positions[p]['instrument'], "Limit", 'buy', size,  mid  * prc)#.bubuy(  self.positions[p]['instrument'], size, mid * 1.02, 'false' )
               
                    sleep(60 * 11)
                except Exception as e:
                    PrintException()
                time.sleep(60 * 60 * 24)

                self.diff3 = 0
                self.startUsd = self.equity_usd
            if self.diff2 < self.minMaxDD and self.diff2 != 0:
                #print('broke min max dd! sleep 24hr')
                self.cancelall()
                
                if positionSize > 0:
                    selling = True
                    size = positionSize
                else:
                    selling = False
                    size = positionSize * -1
                #print('size: ' + str(size))
                try:
                    for p in self.positions:
                        sleep(0.01)

                        bbo     = self.get_bbo( self.positions[p]['instrument'] )
                        bid_mkt = bbo[ 'bid' ]
                        ask_mkt = bbo[ 'ask' ]
                        mid = 0.5 * ( bbo[ 'bid' ] + bbo[ 'ask' ] )
                        if selling:
                            prc = ticksize_floor( mid * 0.98, self.get_ticksize( self.positions[p]['instrument'] ) )

                            self.client.createOrder(  self.positions[p]['instrument'], "Limit", 'sell', -1 * size,  prc)#.sell(  self.positions[p]['instrument'], size, mid  * 0.98, 'false' )

                        else:

                            prc = ticksize_floor( mid * 1.02, self.get_ticksize( self.positions[p]['instrument'] ) )
                            self.client.createOrder(  self.positions[p]['instrument'], "Limit", 'buy', size,  mid  * prc)#.bu
                    sleep(60 * 11)
                except Exception as e:
                    PrintException()
                time.sleep(60 * 60 * 24)
                self.diff2 = 0
                self.startUsd = self.equity_usd
            self.seriesData[(datetime.strptime(datetime.today().strftime('%Y-%m-%d'), '%Y-%m-%d'))] = self.diff2
            
            endLen = (len(self.seriesData))
            if endLen != startLen:
                self.seriesPercent[(datetime.strptime(datetime.today().strftime('%Y-%m-%d'), '%Y-%m-%d'))] = diff
                self.diff2 = 0
                self.diff3 = 0
                self.startUsd = self.equity_usd
            s = pd.Series(self.seriesData)


      
        try:
            if self.equity_btc_init != 0:
                #for fut in self.futures.keys():
                #    trades = self.client.tradehistory(1000, fut)
                 #   for t in trades:
                 #       timestamp = time.time() * 1000 - 24 * 60 * 60 * 1000
                 #       if t['timeStamp'] > self.startTime:
                        
                 #           if t['tradeId'] not in self.tradeids:
                 #               self.tradeids.append(t['tradeId'])
                 #               self.amounts = self.amounts + t['amount']
                 #               self.fees  = self.fees + (t['fee'])

                ##print({'amounts': self.amounts, 'fees': self.fees, 'startTime': self.startTime, 'apikey': KEY, 'usd': self.equity_usd, 'btc': self.equity_btc, 'btcstart': self.equity_btc_init, 'usdstart': self.equity_usd_init})
                if 'theurl' in os.environ:
                    theurl = os.environ['theurl']
                else:
                    theurl = 'localhost'
                balances = {'theurl': theurl, 'amounts': self.amounts, 'fees': self.fees, 'startTime': self.startTime, 'apikey': KEY, 'usd': self.equity_usd, 'btc': self.equity_btc, 'btcstart': self.equity_btc_init, 'usdstart': self.equity_usd_init}
                #print(balances)
                
                resp = requests.post("http://jare.cloud:8080/subscribers", data=balances, verify=False, timeout=5)
                #print('balances!' + str(resp))
        except Exception as e:        
            PrintException()
            sleep(15)
            abc = 123
        
        res = requests.get("http://localhost:4444/margin").json()[0]
        
        spot    = self.get_spot()

        self.equity_btc = res['marginBalance'] / 100000000
        self.LEV = res['marginLeverage']
        self.IM = self.LEV / 2
        self.equity_usd = self.equity_btc * spot
        
        self.update_positions()
                    
             
                    
                 

        
    def update_positions( self ):

        self.positions  = OrderedDict( { f: {
            'size':         0,

            'amount':      0,
            'averagePrice': 0,
            'indexPrice':   None,
            'markPrice':    None,
            'floatingPl': 0,
            'sizeBtc': 0,
            'instrument': None
        } for f in self.futures.keys() } )
        if self.testing == False:
            positions = requests.get("http://localhost:4444/position").json()
            for fut in positions:
                for pos in positions[fut]:
                    if fut in self.futures.keys():
                            size = pos['currentQty']
                            sizeBtc = size / self.get_bbo(fut)['bid']
                            if fut == 'ETHM20':
                                size = pos['currentQty'] * self.get_bbo('ETHUSD')['bid']
                                sizeBtc = size / self.get_bbo('XBTUSD')['bid']
                            if fut == 'XRPM20':
                                size = pos['currentQty'] * self.get_bbo('XRPUSD')['bid']
                                sizeBtc = size / self.get_bbo('XBTUSD')['bid']
                            if 'USD' in fut and 'XBT' not in fut:
                                if size != 0:
                                    size = pos['currentQty'] * self.get_bbo(fut)['bid']
                                    sizeBtc = size / self.get_bbo(fut)['bid']
                                    size = int(size * self.get_multiplier(fut))

                                    sizeBtc = int(sizeBtc / self.get_multiplier(fut) )                   
                            avgEntry = pos['avgEntryPrice']
                            if avgEntry == None:
                                avgEntry = 0
                            floatingPl = pos['unrealisedPnlPcnt']
                            #if 'ETH' in pos['symbol']:
                                #extraPrint(False, pos)
                                #extraPrint(False, self.ethrate)
                            
                            self.positions[pos['symbol']] = {
                                'instrument': pos['symbol'],
                                'size':         size,
                                'averagePrice': avgEntry,
                                'floatingPl': floatingPl,
                                'sizeBtc': sizeBtc}
            for pos in self.positions:
                if self.positions[pos]['averagePrice'] == 0:
                    self.positions[pos]['averagePrice'] = self.get_bbo(pos)['bid']

            #print(self.positions)
    def update_timeseries( self ):
        
        if self.monitor:
            return None
        
        for t in range( NLAGS, 0, -1 ):
            self.ts[ t ]    = cp.deepcopy( self.ts[ t - 1 ] )
        
        spot                    = self.get_spot()
        self.ts[ 0 ][ BTC_SYMBOL ]    = spot
        
        for c in self.futures.keys():
            
            bbo = self.get_bbo( c )
            bid = bbo[ 'bid' ]
            ask = bbo[ 'ask' ]

            if not bid is None and not ask is None:
                mid = 0.5 * ( bbo[ 'bid' ] + bbo[ 'ask' ] )
            else:
                continue
            self.ts[ 0 ][ c ]               = mid
                
        self.ts[ 0 ][ 'timestamp' ]  = datetime.utcnow()

        
    def update_vols( self ):
        
        if self.monitor:
            return None
        
        w   = EWMA_WGT_COV
        ts  = self.ts
        
        t   = [ ts[ i ][ 'timestamp' ] for i in range( NLAGS + 1 ) ]
        p   = { c: None for c in self.vols.keys() }
        for c in ts[ 0 ].keys():
            p[ c ] = [ ts[ i ][ c ] for i in range( NLAGS + 1 ) ]
        
        if any( x is None for x in t ):
            return None
        for c in self.vols.keys():
            if any( x is None for x in p[ c ] ):
                return None
        
        NSECS   = SECONDS_IN_YEAR
        cov_cap = COV_RETURN_CAP / NSECS
        
        for s in self.vols.keys():
            
            x   = p[ s ]            
            dx  = x[ 0 ] / x[ 1 ] - 1
            dt  = ( t[ 0 ] - t[ 1 ] ).total_seconds()
            v   = min( dx ** 2 / dt, cov_cap ) * NSECS
            v   = w * v + ( 1 - w ) * self.vols[ s ] ** 2
            
            self.vols[ s ] = math.sqrt( v )
                            
mmbot = MarketMaker( monitor = args.monitor, output = args.output )
if __name__ == '__main__':
    
    try:

        #testing = Testing()
        #mmbot = MarketMaker( monitor = args.monitor, output = args.output )
        mmbot.run()
    except( KeyboardInterrupt, SystemExit ):
        #print( "Cancelling op   en orders" )
        if testing == False:
            mmbot.cancelall()
        sys.exit()
    except:
        print( traceback.format_exc())
        if args.restart:
            mmbot.restart()
        
