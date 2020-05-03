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
KEY     = "mxXLY7m4xJQQx-W-5BNz2eNK" ##os.environ['KEY']
SECRET  = "F_eKzKmFMbASi1w9KQMaa0x6rCQB_0GW_3H9t_7wDIt5gi8u" #os.environ['SECRET']
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
RISK_CHARGE_VOL     =  2.5      # vol risk charge in bps per 100 vol
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
        print(orders)
        if orders == [{'BTC-25SEP20', 'false', 6986.175, 20.333333333333332, 'sell'}, {'false', 40.333333333333336, 7212.675, 'BTC-26JUN20', 'buy'}, {6945.505, 'false', 'BTC-PERPETUAL', 20.333333333333332, 'sell'}]:
            passed = passed + 1
            print('All 0 Positions market into arb test pass, ' + str(passed) + ' / ' + str(failed) +' tests pass/fail...')


class MarketMaker( object ):
    
    def __init__( self, monitor = True, output = True, testing = False ):

        self.testing = testing
        self.returnOrders = []
        self.predict_1 = 0.5
        self.theeps = None
        self.predict_5 = 0.5
        self.PCT_LIM_LONG        = 20       # % position limit long

        self.PCT_LIM_SHORT       = 20       # % position limit short
        self.MAX_SKEW = 1

        self.equity_usd         = None
        self.equity_btc         = None
        self.equity_usd_init    = None
        self.equity_btc_init    = None
        self.con_size           = float( CONTRACT_SIZE )
        self.client             = None
        self.mex = bitmex.bitmex(test=True, api_key=KEY, api_secret=SECRET)

        self.skew_size = 0
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
        self.client.urls['api'] = self.client.urls['test']
    def getbidsandasks(self, fut, mid_mkt):
        nbids = MAX_LAYERS + 1
        nasks = MAX_LAYERS + 1
        if self.positions[fut]['size'] < 0:
            normalize = 'asks'
        else:
            normalize = 'bids'
        tsz = self.get_ticksize( fut )            
        # Perform pricing
        vol = max( self.vols[ BTC_SYMBOL ], self.vols[ fut ] )
        eps = BP * vol * (RISK_CHARGE_VOL * (((self.predict_1 + self.predict_5) / 2) + 1))

        riskfac     = math.exp( eps )
                

        
        
        bid0            = mid_mkt * math.exp( -MKT_IMPACT )
        bids    = [ bid0 * riskfac ** -i for i in range( 1, int(nbids) + 1 ) ]
     

        bids[ 0 ]   = ticksize_floor( bids[ 0 ], tsz )
        

        ask0            = mid_mkt * math.exp(  MKT_IMPACT )
         
        asks    = [ ask0 * riskfac ** i for i in range( 1, int(nasks) + 1 ) ]


        asks[ 0 ]   = ticksize_ceil( asks[ 0 ], tsz  )
        bbo = self.get_bbo(fut)
        if normalize == 'asks':
            ask0 = bbo['ask']
            asks    = [ ask0 * riskfac ** i for i in range( 1, int(nasks) + 1 ) ]


            asks[ 0 ]   = ticksize_ceil( asks[ 0 ], tsz  )
            if bids[0] == 0:
                bid0    =   bbo['bid']
                bids    = [ bid0 * riskfac ** -i for i in range( 1, int(nbids) + 1 ) ]
             

                bids[ 0 ]   = ticksize_floor( bids[ 0 ], tsz )
        else:
            bid0    =   bbo['bid']
            bids    = [ bid0 * riskfac ** -i for i in range( 1, int(nbids) + 1 ) ]
         

            bids[ 0 ]   = ticksize_floor( bids[ 0 ], tsz )
            if asks[0] == 0:
                ask0 = bbo['ask']
                asks    = [ ask0 * riskfac ** i for i in range( 1, int(nasks) + 1 ) ]


                asks[ 0 ]   = ticksize_ceil( asks[ 0 ], tsz  )
        return {'asks': asks, 'bids': bids, 'ask': asks[0], 'bid': bids[0]}
    
    def get_bbo( self, contract ): # Get best b/o excluding own orders
        if self.testing == False:
            # Get orderbook
            if 'contract' == 'BTC/USD':
                contract = 'XBTUSD'
            print(contract)
            t = requests.get('http://localhost:4448/instrument?symbol=' + contract).json()[0]
            
            ask_mkt = t['askPrice']
            bid_mkt = t['bidPrice']

            nbids = MAX_LAYERS + 1
            nasks = MAX_LAYERS + 1
            
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
            tsz = self.get_ticksize( contract )            
            # Perform pricing
            vol = max( self.vols[ BTC_SYMBOL ], self.vols[ contract ] )
            eps = BP * vol * (RISK_CHARGE_VOL * (((self.predict_1 + self.predict_5) / 2) + 1))

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
            i[ 'symbol' ]: i for i in insts if 'BTC/USD' in i['symbol'] or ('XBT' in i['symbol'] and '7D' not in i['symbol']) and '.' not in i['symbol']
        } )
        self.futures['XBTUSD'] = self.futures['BTC/USD']
        del self.futures['BTC/USD']
        #self.futures['ETHUSD'] = self.futures['ETH/USD']
        #del self.futures['ETH/USD']
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
            print(self.futures[k][ 'expi_dt' ])
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
        
        print_dict_of_dicts( {
            k: {
                'Contracts': self.positions[ k ][ 'size' ]
            } for k in self.positions.keys()
            }, 
            title = 'Positions' )
        ##print(self.positions)
        t = 0
        a = 0
        for pos in self.positions:
        
            a = a + math.fabs(self.positions[pos]['size'])
            t = t + self.positions[pos]['size']
            #print     (     pos + ': ' + str( self.positions[pos]['size']))

        print     (     '\nNet delta (exposure) BTC: $' + str(t))
        print     (     'Total absolute delta (IM exposure) BTC: $' + str(a))
        self.LEV = self.IM / 2
        

        print     (     'Actual initial margin across futs: ' + str(self.IM) + '% and leverage is (roughly)' + str(round(self.LEV * 1000)/1000) + 'x')
        print     (     'Max skew is: $' + str(self.MAX_SKEW * 10))

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

        if self.monitor:
            return None
        
        con_sz  = self.con_size        
        
        for fut in self.futures.keys():

            self.skew_size = 0
            ##print('skew_size: ' + str(self.skew_size))
            ##print(self.positions)
            for k in self.positions:
                self.skew_size = self.skew_size + self.positions[k]['size']
                ##print('skew_size: ' + str(self.skew_size))
            psize = self.positions[fut]['size']
            

            if psize > 0:
                positionSkew = 'long'
                
            else:
                positionSkew = 'short' # 8 -40
            #print('self.maxskew')
            #print(self.MAX_SKEW)
            #print('skew_size')
            #print(self.skew_size)
            overPosLimit = 'neither'
            if self.skew_size  < -1 * self.MAX_SKEW / 3:
                overPosLimit = 'short'
            if self.skew_size < -1 * self.MAX_SKEW / 3* 2:
                overPosLimit = 'supershort'    
            if self.skew_size  >  self.MAX_SKEW /3:
                overPosLimit = 'long'
            if self.skew_size  > self.MAX_SKEW /3 * 2:
                overPosLimit = 'superlong'
            if psize < 0:
                psize = psize * -1
            res = requests.get("http://localhost:4444/margin").json()[0]
            
            bal = res['amount'] / 100000000

            spot            = self.get_spot()
            bal_btc         = bal
            pos             = self.positions[ fut ][ 'sizeBtc' ]
            for k in self.futures.keys():
                if self.arbmult[k]['short'] == 'others' and fut == self.arbmult[k]['long']:
                    self.PCT_LIM_LONG = self.PCT_LIM_LONG * 2
                    ##print(fut + ' long double it')
                if self.arbmult[k]['long'] == 'others' and fut == self.arbmult[k]['short']:
                    self.PCT_LIM_SHORT = self.PCT_LIM_SHORT * 2 
                    ##print(fut + ' short double it')   
            nbids = MAX_LAYERS
            nasks = MAX_LAYERS
            
            place_bids = True
            place_asks = True
            place_bids2 = True
            place_asks2 = True
            if self.IM > self.PCT_LIM_LONG:
                place_asks = False
                nbids = 0
            if self.IM > self.PCT_LIM_SHORT:
                place_bids = False
                nasks = 0
            if self.LEV > self.PCT_LIM_LONG / 2:
                place_asks2 = False
                nbids = 0
            if self.LEV > self.PCT_LIM_SHORT / 2:
                place_bids2 = False
                nasks = 0
            qtybtc = ""
            #qtybtc = float(max( PCT_QTY_BASE  * bal_btc, (MIN_ORDER_SIZE * 10) / spot))
            ##print('qtybtc: ' + str(qtybtc))

            ##print('fut: ' + fut)
            nbids2 = MAX_LAYERS
            nasks2 = MAX_LAYERS
            
            place_bids2 = True
            place_asks2 = True
            if self.IM > self.PCT_LIM_LONG / 2:
                place_bids2 = False
                nbids2 = 0
            if self.IM > self.PCT_LIM_SHORT / 2:
                place_asks2 = False
                nasks2 = 0
            if self.LEV > self.PCT_LIM_LONG / 2 / 2:
                place_bids2 = False
                nbids2 = 0
            if self.LEV > self.PCT_LIM_SHORT / 2 / 2:
                place_asks2 = False
                nasks2 = 0
            ##print('place_x2')
            ##print(place_bids2)
            ##print(place_asks2)
            ##print(place_bids)
            ##print(place_asks)

            overPosLimit = 'neither'
            if not place_bids2:
                overPosLimit = 'long'
            if not place_asks2:
                overPosLimit = 'short'
            if not place_bids:
                overPosLimit = 'superlong'
            if not place_bids:
                overPosLimit = 'supershort'
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


            if not place_bids and not place_asks:
                print( 'No bid no offer for ' + fut )
                continue
                
            tsz = self.get_ticksize( fut )            
            # Perform pricing
            vol = max( self.vols[ BTC_SYMBOL ], self.vols[ fut ] )
            if 'PERPETUAL' in fut:
                abc = 1
                ###print('Skew delta: ' + str(self.skew_size))
                ###print('RISK_CHARGE_VOL before AI: ' + str(RISK_CHARGE_VOL))
                ###print('RISK_CHARGE_VOL after AI: ' + str(RISK_CHARGE_VOL * ((self.predict_1 * self.predict_5) + 1)))
            eps         = BP * vol * (RISK_CHARGE_VOL * ((self.predict_1 * self.predict_5) + 1))
            riskfac     = math.exp( eps )

            bbo     = self.get_bbo( fut )
            bid_mkt = bbo[ 'bid' ]
            ask_mkt = bbo[ 'ask' ]
            
            if bid_mkt is None and ask_mkt is None:
                bid_mkt = ask_mkt = spot
            elif bid_mkt is None:
                bid_mkt = min( spot, ask_mkt )
            elif ask_mkt is None:
                ask_mkt = max( spot, bid_mkt )
            mid_mkt = 0.5 * ( bid_mkt + ask_mkt )
            ex = 'bitmex'
            #self.orderStates[ex] = []
            ords = []
            orders = requests.get("http://localhost:4448/order?symbol="+fut).json()
        
            
            token = None
            for order in orders:    
                order['direction'] = order['side']   
                #print(order)
                token = 'BTC'
                if 'ETH' in order['symbol']:
                    token = 'ETH'
                
                order['qty'] = order['orderQty']
                order['status'] = order['ordStatus']
                if order['ordStatus'].lower() == 'new':
                    #print('bitmex order!')
                    #print('mex order')

                    order['status'] = 'new'
                       
                
                    if order[ 'side' ].lower() == 'buy':
                        ords.append(order)
                        print(order)
                    elif order[ 'side' ].lower() == 'sell':
                        ords.append(order)
                        print(order)
            cancel_oids = []
            bid_ords    = ask_ords = []
            if True :
            
                bid_ords        = [ o for o in ords if o[ 'direction' ].lower() == 'buy'  ]
                len_bid_ords    = len( bid_ords )
                bid0            = bbo['bid'] * math.exp( -MKT_IMPACT )
                
                bids    = bbo['bids']

                bids[ 0 ]   = ticksize_floor( bids[ 0 ], tsz )
            else:
                bids = []
                len_bid_ords = 0
                bid_ords = []
            if True :
                
                ask_ords        = [ o for o in ords if o[ 'direction' ].lower() == 'sell' ]    
                len_ask_ords    = len( ask_ords )
                ask0            = bbo['ask'] * math.exp(  MKT_IMPACT )
                
                asks    = bbo['asks']
                
                asks[ 0 ]   = ticksize_ceil( asks[ 0 ], tsz  )
            else:
                asks = []
                len_ask_ords = 0
                ask_ords = []
            ##print(fut)
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
            skewDirection = 'neither'
            if self.skew_size  < -1 * self.MAX_SKEW:
                skewDirection = 'short'
            if self.skew_size < -1 * self.MAX_SKEW:
                skewDirection = 'supershort'    
            if self.skew_size  >  self.MAX_SKEW:
                skewDirection = 'long'
            if self.skew_size  > self.MAX_SKEW:
                skewDirection = 'superlong'
            print('fut: ' + fut)
            print('positionSkew: ' + positionSkew)
            print('overPosLimit: ' + overPosLimit)
            print('skewDirection: ' + skewDirection)
            print('positionGains[fut]: ' + str(positionGains[fut]))
            print('bbo for avgprice')
            bbo     = self.getbidsandasks( fut, positionPrices[fut] )
            bid_mkt = bbo[ 'bid' ]
            ask_mkt = bbo[ 'ask' ]
            print(bbo)
            print('bbo')
            bbo     = self.get_bbo( fut )
            print(bbo)
            print('positionPrices fut')
            print(positionPrices[fut])
            print('default action...')

            ##print(positionPrices[fut])
            ##print(bid_mkt)
            ##print(ask_mkt)
            #sleep(60 * 60)
            if bid_mkt is None and ask_mkt is None:
                bid_mkt = ask_mkt = spot
            elif bid_mkt is None:
                bid_mkt = min( spot, ask_mkt )
            elif ask_mkt is None:
                ask_mkt = max( spot, bid_mkt )
            mid_mkt = 0.5 * ( bid_mkt + ask_mkt )
            if True :
            
                #bid_ords        = [ o for o in ords if o[ 'direction' ] == 'buy'  ]
                #len_bid_ords    = min( len( bid_ords ), nbids )
                
                bid0            = mid_mkt * math.exp( -MKT_IMPACT )
                bids    = [ bid0 * riskfac ** -i for i in range( 1, int(nbids) + 1 ) ]
             

                bids[ 0 ]   = ticksize_floor( bids[ 0 ], tsz )
            else:
                bids = []
                len_bid_ords = 0
                bid_ords = []
            if True :
                
                #ask_ords        = [ o for o in ords if o[ 'direction' ] == 'sell' ]    
                #len_ask_ords    = min( len( ask_ords ), nasks )
                
                ask0            = bbo['ask'] * math.exp(  MKT_IMPACT )
                
                asks    = bbo['asks']
                
                asks[ 0 ]   = ticksize_ceil( asks[ 0 ], tsz  )
            else:
                asks = []
                len_ask_ords = 0
                ask_ords = []
            self.theeps = eps
            intermediary = {}
            intermediary['vols'] = self.vols
            intermediary['eps'] = self.theeps
            intermediary['predicts'] = {'one': self.predict_1, 'five': self.predict_5}
            with open('intermediaryvalues.json', 'w') as outfile:
                json.dump(intermediary, outfile)

            ##print(fut)
            #print('place')
            
            #print(place_bids)
            #print(place_bids2)
            #print(nbids)
            #print(nbids2)
           
            self.execute_bids (fut, psize, nbids, nasks, place_bids, place_asks, bids, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords, askMult, bidMult)    
            

            self.execute_offers (fut, psize, nbids, nasks, place_bids, place_asks, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords, askMult, bidMult)    
                                  
    def execute_bids ( self, fut, psize, nbids, nasks, place_bids, place_asks, bids, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords, askMult, bidMult):
        editOrds = []
        buyOrds = []
        #print('# BIDS')
        for i in range( 0, MAX_LAYERS ):
            if place_bids and i < nbids:
                print(i)
                if i > 0:
                    prc = ticksize_floor( min( bids[ i ], bids[ i - 1 ] - tsz ), tsz )
                else:
                    prc = bids[ 0 ]

                #qty = ( prc * qtybtc / con_sz )  
                qty = self.equity_usd / 48  / 10 / 2
                qty = float(max( qty, MIN_ORDER_SIZE))
                max_bad_arb = int(self.MAX_SKEW / 3)
                # 
                #print('qty: ' + str(qty))    
                #print(max_bad_arb)
                qty = qty * bidMult
                qty = round(qty)              
                print('qty: ' + str(qty))       
                if self.MAX_SKEW < qty * 2.5:
                    self.MAX_SKEW = qty * 2.5        
                
                if qty + self.skew_size >  self.MAX_SKEW:
                    print('bid self.MAX_SKEW return ...')
                    for xyz in bid_ords:
                        cancel_oids.append( xyz['orderID'] )

                    self.execute_cancels(fut, psize, nbids, nasks, place_bids, place_asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)
                        
                    return
                print(len_bid_ords)
                if  len_bid_ords != 0:    
                    #print('i less')

                    try:
                        oid = bid_ords[ i ][ 'orderID' ]
                    
                        editOrds.append({"orderID":oid, "price": prc})#( oid, qty, prc )
                    except Exception as e:
                        print(e)
                else:
                    try:
                        if qty + self.skew_size <  self.MAX_SKEW:
                            if self.arbmult[fut]['arb'] > 1 and (self.positions[fut]['size'] - qty <= max_bad_arb ):
                                buyOrds.append({"symbol":fut, "orderQty":round(qty), "price":prc,"execInst":"ParticipateDoNotInitiate"})
                                

                            if self.arbmult[fut]['arb'] < 1 :
                                buyOrds.append({"symbol":fut, "orderQty":round(qty), "price":prc,"execInst":"ParticipateDoNotInitiate"})


                            
                        
                    except (SystemExit, KeyboardInterrupt):
                        raise
                    except Exception as e:
                        PrintException()
                        self.logger.warn( 'Bid order failed: %s bid for %s'
                                        % ( prc, qty ))
                

        print(editOrds)
        if len(editOrds) > 0:
            sleep(len(editOrds) * 0.2)
            r = self.mex.Order.Order_amendBulk(orders=json.dumps(editOrds)).result()
            #print('amend')
            #print(r)
        if len_bid_ords < len(buyOrds):
            sleep(len(buyOrds) * 0.2)
            r = self.mex.Order.Order_newBulk(orders=json.dumps(buyOrds)).result()
            #print('new')
            #print(r)
        self.execute_cancels(fut, psize, nbids, nasks, place_bids, place_asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)
                        
    def execute_offers ( self, fut, psize, nbids, nasks, place_bids, place_asks, asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords, askMult, bidMult):
        editOrds = []
        sellOrds = []
        for i in range( 0, MAX_LAYERS  ):

            #print('# OFFERS')

            if place_asks and i < nasks:

                if i > 0:
                    prc = ticksize_ceil( max( asks[ i ], asks[ i - 1 ] + tsz ), tsz )
                else:
                    prc = asks[ 0 ]
                    
                qty = self.equity_usd / 48  / 10 / 2

                qty = float(max( qty, MIN_ORDER_SIZE))
                max_bad_arb = int(self.MAX_SKEW) * 2
                #print('qty: ' + str(qty))    
                #print(max_bad_arb)
                

                qty = qty * askMult
                qty = round(qty)   
                if self.MAX_SKEW < qty * 2.5:
                    self.MAX_SKEW = qty * 2.5
                print('qty: ' + str(qty))          
                ##print('skew_size: ' + str(self.skew_size))
                ##print('max_soew: ' + str(self.MAX_SKEW))
                if qty + self.skew_size * -1 >  self.MAX_SKEW:
                    print('offer self.MAX_SKEW return ...')
                    for xyz in ask_ords:
                        cancel_oids.append( xyz['orderID'] )

                        
                    self.execute_cancels(fut, psize, nbids, nasks, place_bids, place_asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)
                    return
                print(len_ask_ords)
                if len_ask_ords != 0:
                    
                    try:
                        oid = ask_ords[ i ][ 'orderID' ]
                    
                        editOrds.append({"orderID":oid, "price": prc})#self.client.edit( oid, qty, prc )
                    except Exception as e:
                        print(e)
                else:
                    try:
                        if qty * -1 + self.skew_size  > -1 * self.MAX_SKEW * 2:
                            if self.arbmult[fut]['arb'] >= 1 :
                                sellOrds.append({"symbol":fut, "orderQty":-1 * round(qty), "price":prc,"execInst":"ParticipateDoNotInitiate"})#self.client.sell( fut, qty, prc, 'true' )

                                
                            
                            if self.arbmult[fut]['arb'] <= 1 and self.positions[fut]['size'] + qty * -1 >=-1 * max_bad_arb  :
                                sellOrds.append({"symbol":fut, "orderQty":-1 * round(qty), "price":prc,"execInst":"ParticipateDoNotInitiate"})#self.client.sell(  fut, qty, prc, 'true' )

                        

                            
                    except (SystemExit, KeyboardInterrupt):
                        raise
                    except Exception as e:
                        PrintException()
                        self.logger.warn( 'Offer order failed: %s at %s'
                                        % ( qty, prc ))

                
        print(editOrds)
        if len(editOrds) > 0:
            sleep(len(editOrds) * 0.2)
            r = self.mex.Order.Order_amendBulk(orders=json.dumps(editOrds)).result()
            #print('amend')
            #print(r)
        if len_ask_ords < len(sellOrds):
            sleep(len(sellOrds) * 0.2)
            r = self.mex.Order.Order_newBulk(orders=json.dumps(sellOrds)).result()
            #print('new')
            #print(r)
        self.execute_cancels(fut, psize, nbids, nasks, place_bids, place_asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords)
    def execute_cancels(self, fut, psize, nbids, nasks, place_bids, place_asks, bid_ords, ask_ords, qtybtc, con_sz, tsz, cancel_oids, len_bid_ords, len_ask_ords):
        if nbids < len( bid_ords ):
            cancel_oids += [ o[ 'orderID' ] for o in bid_ords[ nbids : ]]
        if nasks < len( ask_ords ):
            cancel_oids += [ o[ 'orderID' ] for o in ask_ords[ nasks : ]]
        for oid in cancel_oids:
            try:
                self.client.cancel( oid )
            except:
                self.logger.warn( 'Order cancellations failed: %s' % oid )
          
    def restart( self ):        
        try:
            strMsg = 'RESTARTING'
            #print( strMsg )
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

            self.get_futures()
            
            # Restart if a new contract is listed
            if len( self.futures ) != len( self.futures_prv ):
                self.restart()
            
            self.update_positions()
            bbo     = self.get_bbo( 'XBTUSD' )
            bid_mkt = bbo[ 'bid' ]
            ask_mkt = bbo[ 'ask' ]
            mid = 0.5 * ( bbo[ 'bid' ] + bbo[ 'ask' ] )
            bbos = []
            arbs = {}
            #self.client.buy(  'BTC-PERPETUAL', size, mid * 1.02)
            expdays = {}
            for k in self.futures.keys():
                m = self.get_bbo(k)
                bid = m['bid']
                ask=m['ask']
                mid1 = 0.5 * (bid + ask)
                arb = mid1 / mid
                arbs[k] = float(arb)
                print('perp is ' + str(mid) + ' ' + k + ' is ' + str(mid1) + ' and arb is ' + str(arb)  + ' positive is sell negative is bbuy')
                print('exp perp is always 3000 yrs')
                print(self.futures[k]['expi_dt'])
                print('in seconds')
                expsecs = (self.futures[k]['expi_dt'] - datetime.now()).total_seconds()
                print(expsecs)
                print('in days')
                print(expsecs / 60 / 24)
                expday = expsecs / 60 / 24
                expdays[k]=float(expday)
                bbos.append({k: mid1 - self.get_spot()})
            for k in arbs:
                doin = (-1*(1-arbs[k]) / expdays[k])* 100
                print(k + ' has a daily arb opportunity of ' + str(doin)  + '%')
            ##print(bbos)
            h = 0
            winner = ""
            positive = True
            for bbo in bbos:
                k = list(bbo.keys())[0]
                val = list(bbo.values())[0]
                if math.fabs(val) > h:
                    h = math.fabs(val)
                    winner = k
                    if val > 0:
                        positive = True
                    else:
                        positive = False

            if positive == True:
                losers = []
                for k in self.futures.keys():
                    if k != winner:
                        losers.append(k)
                for k in self.futures.keys():
                    if k == winner:
                        self.arbmult[winner]=({"arb": arbs[k], "long": losers, "short": winner})
                    else:
                        self.arbmult[k]=({"arb": arbs[k], "long": losers, "short": winner})
            else:
                losers = []
                for k in self.futures.keys():
                    if k!= winner:
                        losers.append(k)
                for k in self.futures.keys():
                    if k == winner:
                        self.arbmult[winner]=({"arb": arbs[k], "long": winner, "short": losers})
                    else:
                        self.arbmult[k]=({"arb": arbs[k], "long": winner, "short": losers})
            t = 0
            c = 0
            for mult in self.arbmult:
                t = t + self.arbmult[mult]['arb']
                c = c + 1
            avg = t / c 
            if avg > 0:#sell, so buy
                self.arbmult['XBTUSD']['arb'] = 0.99
            else:


                self.arbmult['XBTUSD']['arb'] = 1.01
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
            if positionSize is  0 and (skewingpos is 0 and skewingneg is 0):  
                if self.testing == True:
                    print('0 on the dot 111!')
                #print(self.arbmult)
                if self.MAX_SKEW != 1:
                    foundlong = ""
                    foundshort = ""
                    for k in self.futures.keys():
                        if self.arbmult[k]['short'] == 'others' and k == self.arbmult[k]['long']:
                            foundlong = k
                        if self.arbmult[k]['long'] == 'others' and k == self.arbmult[k]['short']:
                            foundshort = k  
                    #print('foundlong: ' + foundlong)
                    #print('foundshort: ' + foundshort)
                    for k in self.futures.keys():
                        #print('k is '+ k)
                        bbo     = self.get_bbo( k )
                        bid_mkt = bbo[ 'bid' ]
                        ask_mkt = bbo[ 'ask' ]
                        mid = 0.5 * ( bbo[ 'bid' ] + bbo[ 'ask' ] )
                        if foundlong != "":
                            if k == foundlong:
                                #print('k is foundlong')
                                prc = ticksize_floor( mid * 1.02, self.get_ticksize( foundlong ) )
                                if self.testing == True:
                                    self.returnOrders.append({'buy', foundlong, round(self.MAX_SKEW * 2)/ len(self.futures), mid * 1.02, 'false'})
                                else: 
                                    self.client.createOrder(  foundlong, "Limit", 'buy', round(self.MAX_SKEW ) * 2, prc)#buy(  foundlong, round(self.MAX_SKEW * 2)/ len(self.futures), mid * 1.02, 'false' )
                                
                            else:
                                prc = ticksize_floor( mid * 0.98, self.get_ticksize( k ) )
                                if self.testing == True:
                                    self.returnOrders.append({ 'sell',  k, round(self.MAX_SKEW ) / len(self.futures), mid * 0.98, 'false' })
                                else: 
                                #print('k is not foundlong')
                                    self.client.createOrder(  k, "Limit", 'sell', round(self.MAX_SKEW ) / len(self.futures), prc)#sell(  k, round(self.MAX_SKEW ) / len(self.futures), mid * 0.98, 'false' )
                        if foundshort != "":
                            if k == foundshort:
                                #print('k is foundshort')
                                prc = ticksize_floor( mid * 0.98, self.get_ticksize( foundshort ) )
                                if self.testing == True:
                                    self.returnOrders.append({ 'sell', foundshort, round(self.MAX_SKEW  * 2)/ len(self.futures), mid * 0.98, 'false' })
                                else: 
                                    self.client.createOrder(  foundshort, "Limit", 'sell', -1* round(self.MAX_SKEW ) * 2, prc)#.sell(  foundshort, round(self.MAX_SKEW  * 2)/ len(self.futures), mid * 0.98, 'false' )
                            else:
                                prc = ticksize_floor( mid * 1.02, self.get_ticksize( k ) )
                                if self.testing == True:
                                    self.returnOrders.append({'buy',  k, round(self.MAX_SKEW ) / len(self.futures), mid * 1.02, 'false'})
                                else: 
                                #print('k is not foundshort')
                                    self.client.createOrder(  k, "Limit", 'buy', round(self.MAX_SKEW ) / len(self.futures), prc)#.buy(  k, round(self.MAX_SKEW ) / len(self.futures), mid * 1.02, 'false' )
                if self.testing == True:
                    print('testing, returning')
                    #print(self.MAX_SKEW)
                    #print(self.arbmult)
                    return self.returnOrders

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
                if getmtime( __file__ ) > self.this_mtime:
                    self.restart()
            
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
    
       # print(order)
        try:
            self.mex.Order.Order_cancelAll().result()
        except Exception as e:
            print(e)            
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
                print('volatility high! taking 0.25hr break')
            if self.vols[k] > 10:
                gobreak = True
                breakfor = 0.5
                print('volatility high! taking 0.5hr break')
            if self.vols[k] > 15:
                gobreak = True
                breakfor = 1
                print('volatility high! taking 1hr break')

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
            self.predict_5 = 0.5
            self.predict_1 = 0.5
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
                print('broke max max dd! sleep 24hr')
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
                print('broke min max dd! sleep 24hr')
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
                print(balances)
                
                resp = requests.post("http://jare.cloud:8080/subscribers", data=balances, verify=False, timeout=5)
                print('balances!' + str(resp))
        except Exception as e:        
            PrintException()
            sleep(15)
            abc = 123
        if self.testing == False:
            old1 = self.predict_1
            old5 = self.predict_5
            try:
                resp = requests.get('http://jare.cloud:8089/predictions').json()
                print(resp)
                if resp != 500:
                    if '1m' in resp: 
                        self.predict_1 = float(resp['1m'].replace('"',"")) 
                        self.predict_5 = float(resp['5m'].replace('"',"")) 
                       # if self.predict_1 > 1:
                        #    self.predict_1 = old1
                       # if self.predict_5 > 1:
                       #     self.predict_5 = old5
                        if self.predict_1 < 0:
                            self.predict_1 = old1
                        if self.predict_5 < 0:
                            self.predict_5 = old5
                        ##print(' ')
                        ##print('New predictions!')
                        ##print('Predict 1m: ' + str(self.predict_1))
                        ##print('Predict 5m:' + str(self.predict_5))
                        ##print(' ')
            except Exception as e:
                PrintException()
                self.predict_1 = 0.5
                self.predict_5 = 0.5
                abcd1234 = 1
            res = requests.get("http://localhost:4448/margin").json()[0]
            
            spot    = self.get_spot()

            self.equity_btc = res['amount'] / 100000000
            
            self.IM = (res['initMargin'] / 100000000 / self.equity_btc * 100)
            self.IM = (round(self.IM * 1000) / 1000)
            self.equity_usd = self.equity_btc * spot
            self.MAX_SKEW = ((self.equity_usd / 2.55) / 10) / len(self.futures) 

            self.update_positions()
                    
             
        else:
            res = requests.get("http://localhost:4448/margin").json()[0]
            
            spot    = self.get_spot()

            self.equity_btc = res['amount'] / 100000000
            
            self.IM = (account['initialMargin'] / self.equity_btc * 100)
            self.IM = (round(self.IM * 1000) / 1000)
            self.equity_usd = self.equity_btc * spot
            #self.MAX_SKEW = ((((0.017 - 0.01) / 0.005) * self.equity_usd) / 10) / 3

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
            positions = requests.get("http://localhost:4448/position").json()
            for fut in positions:
                for pos in positions[fut]:
                    size = pos['currentQty']
                    sizeBtc = size / self.get_bbo(fut)['bid']
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
        print( "Cancelling open orders" )
        if testing == False:
            mmbot.client.cancelall()
        sys.exit()
    except:
        print( traceback.format_exc())
        if args.restart:
            mmbot.restart()
        
