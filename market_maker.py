# This code is for sample purposes only, comes as is and with no warranty or guarantee of performance
#from bitmex_websocket import BitMEXWebsocket

#now useing api-connectors/official-ws/delta-server/index.js due to peformance issues. Run with nohup node index.js &

import linecache
import sys
import threading
from datetime import timedelta
import time
from queue import Queue
from threading import Timer
#from BybitWebsocket import BybitWebsocket
from prettytable import PrettyTable

import asyncio
import logging
import os
from uuid import uuid4
import pymongo
from pymongo import MongoClient
client = MongoClient()
db = client.market_maker
dbask_ords = db.ask_ords
dbbid_ords = db.bid_ords
dbpositions = db.positions
import threading

# PYTHONPATH=.:$PYTHONPATH DERIBIT_CLIENT_ID=YOU_ACCESS_KEY DERIBIT_CLIENT_SECRET=YOU_ACCESS_SECRET python3 market_maker.py


from ssc2ce.deribit import Deribit, AuthType


# changes various behavior for testing. Set to False in production!
testing = False

import inspect  
def PrintException():
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    lineno = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno, f.f_globals)
    string = 'EXCEPTION IN ({}, LINE {} "{}"): {}'.format(filename, lineno, line.strip(), exc_obj)
    print(string)
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
from deribit_api import RestClient
#import websocket
import json




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
with open('keys.txt') as json_file:
    keydata = json.load(json_file)
KEY     = keydata["deribit"]["key"]#"VC4d7Pj1"
SECRET  = keydata["deribit"]["secret"]#"IB4VEP26OzTNUt4JhNILOW9aDuzctbGs_K6izxQG2dI"





URL     = 'https://www.deribit.com'

EWMA_WGT_LOOPTIME   = 2.5    
BP                  = 1e-4      # one basis point
BTC_SYMBOL          = 'btc'
CONTRACT_SIZE       = 10        # USD
COV_RETURN_CAP      = 100       # cap on variance for vol estimate
DECAY_PCT_LIM       = 0.1       # position lim decay factor toward expiry
LOG_LEVEL           = logging.INFO
MIN_ORDER_SIZE      = 29
MKT_IMPACT          =  0.5      # base 1-sided spread between bid/offer
PCT                 = 100 * BP  # one percentage point
PCT_QTY_BASE        = (10*7)/1.5      # pct order self.qty in bps as pct of acct on each order
MIN_LOOP_TIME       =   0.2       # Minimum time between loops
SECONDS_IN_DAY      = 3600 * 24
SECONDS_IN_YEAR     = 365 * SECONDS_IN_DAY
WAVELEN_MTIME_CHK   = 15        # time in seconds between check for file change
WAVELEN_OUT         = 15        # time in seconds between output to terminal
WAVELEN_TS          = 15        # time in seconds between time series update

MKT_IMPACT          *= BP

PCT_QTY_BASE        *= BP

#conn = Deribit()
#bitws = BybitWebsocket(wsURL="wss://stream.bybit.com/realtime",
#                                 api_key=keydata["bybit"]["key"], api_secret=keydata["bybit"]["secret"])
#bitws.subscribe_order()

#bitws.subscribe_execution()
#bitws.subscribe_position()



class MarketMaker( object ):
    
    def __init__( self, monitor = True, output = True ):

        self.iask = {}
        self.ibid = {}
         
        
        self.deri_bal = {}
        self.deri_orders = {}
        self.deri_orders['bids'] = []
        self.deri_orders['asks'] = []
        self.deri_quote = {}
        self.deri_quote['ETH'] = []
        self.deri_quote['BTC'] = []
        self.deri_index = {}

        self.MAX_SKEW = MIN_ORDER_SIZE * 5.5
        self.MAX_SKEW_OLD = MIN_ORDER_SIZE * 5.5

        self.bit  = bybit.bybit(test=False, api_key=keydata["bybit"]["key"], api_secret=keydata["bybit"]["secret"])
        
        self.mex = bitmex.bitmex(test=False, api_key=keydata["bitmex"]["key"], api_secret=keydata["bitmex"]["secret"])

        
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
        self.LEVERAGE_LIMIT_SHORT = 10
        self.LEVERAGE_LIMIT_LONG = 10
        self.INITIAL_MARGIN_LIMIT_LONG        = 20   # % position limit long

        self.INITIAL_MARGIN_LIMIT_SHORT       = 20
        for token in self.exchangeRates:
            self.PCT_LIM_LONG[token]        = self.INITIAL_MARGIN_LIMIT_LONG 
            self.PCT_LIM_SHORT[token]       = self.INITIAL_MARGIN_LIMIT_SHORT    
            self.LEV_LIM_LONG[token] = self.LEVERAGE_LIMIT_LONG
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
        self.bid_ords = {}
        self.ask_ords = {}

        self.len_bid_ords = {}
        self.len_ask_ords = {}

        self.oldt = 0
        self.oldte = 0
        self.ccxt = None
        self.cancelledMex = []
        self.domex = True
        self.qty = None
        self.banned = []

        self.bidsleft = {}
        self.asksleft = {}
        self.bidsleftbefore = {}
        self.asksleftbefore = {}
        self.doneFuts = []
        self.MAX_LAYERS          =  1        # max orders to layer the ob with on each side

        self.exfuts = {}
        #self.orderStates = {}
          
        self.mexfundingfirst = True
        self.t = 0
        self.oldte = 0
        self.bitOrders = []
        self.create_client()
        #self.ws = {}
        self.tradeids = []
        self.amounts = 0
        self.fees = 0
        self.startTime = int(time.time()*1000)
        self.arbmult = {}
        self.arbmult['BTC'] = {}
        self.arbmult['ETH'] = {}
        self.totrade = ['bitmex','bybit', 'deribit']
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
       #print('loop in thread!')
        loop.run_until_complete(self.update_counts())


    

    def mextimer(self):
        self.domex = True

    def bit_ords(self):
        while True:
            try:
                ex = 'bybit'


                count = 0
                for token in self.exchangeRates:

                    brem = False
                    arem = False
                    addBidOrders = []
                    addAskOrders = []
                    ords2 = []
                    #print(self.futtoks[token][ex].replace('-bybit', ''))
                    ords = self.bit.Order.Order_getOrders(order="true",symbol=self.futtoks[token][ex].replace('-bybit', '')).result()[0]['result']
                    if 'data' in ords:
                        ords = ords['data']
                        count = 0

                        brem = False
                        arem = False
                        for order in ords:
                            if 'ETH' in order['symbol']:
                                order['sybmol'] = 'ETHUSD-bybit'
                            order['orderID'] = order['order_id']
                            order['status'] = order['order_status']
                            if order['order_status'] == 'New':

                                order['status'] = 'new'
                                #print('bybit order')
                                #print('bybit order!')
                                #print(' ')

                                #print('bybit orders!')
                                #print(order)
                                #print(' ')
                                token = 'BTC'
                                if 'ETH' in order['symbol']:
                                    token = 'ETH'

                                count = count + 1
                                gogo = True
                                
                                order['name'] = self.futtoks[token][ex]
                                if order[ 'side' ].lower() == 'buy':
                                    addBidOrders.append(order)
                                elif order[ 'side' ].lower() == 'sell':
                                    addAskOrders.append(order)
                             
                        self.bid_ords[self.futtoks[token][ex]] = addBidOrders 
                        self.ask_ords[self.futtoks[token][ex]] = addAskOrders
                    #print('bybit #self.orderStates[ex]')
                    #print(#self.orderStates[ex])

            except Exception as e:
                PrintException() 
    def bit_pos(self):
        while True:
            try:
                for fut in self.futures['bybit']:
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
                            toinsert = {
                                'name': name,
                                'size':         size,
                                'sizeBtc':      home,
                                'averagePrice': pos['entry_price'],
                                'floatingPl': pos['unrealised_pnl']}
                            self.positions[name]=toinsert
                            
                        
            except Exception as e:     
                
                abc=123#PrintException()
    def der_pos(self):
        while True:
            try:
                ex = 'deribit'

                positions       = self.client.positions()
                for pos in positions:
                    fut = pos['instrument']

                    if pos[ 'instrument' ] in self.futures['deribit']:
                        if 'BTC' in pos[ 'instrument' ]:
                           
                            pos['size'] = pos['size'] * 10
                        pos['name'] = pos[ 'instrument' ]
                        self.positions[fut] = pos
            except Exception as e:
                PrintException()
    def der_ords(self):
        while True:
            try:  
                brem = False
                arem = False
                ex = 'deribit'
                count = 0
                for token in self.exchangeRates:
                    ords = self.client.getopenorders(self.futtoks[token][ex])          
                    
                    count = 0
                    newbidords = []
                    newaskords = []
                    for o in ords:
                        
                        #print('deribit order!')
                        o['orderID'] = o['orderId']
                        o['symbol'] = o['instrument']
                        token = 'BTC'
                        if 'ETH' in o['symbol']:
                            token = 'ETH'   
                        
                            
                        o['qty'] = o['quantity']
                        
                        o['side'] = o['direction'].lower()
                        o['order_state'] = o['state']
                        o['status'] = o['state']
                        order = o

                        if o['order_state'] == 'open':
                            o['status'] = 'new'
                            
                            order = o

                            count = count + 1
                        order['name'] = self.futtoks[token][ex]
                        if order[ 'side' ].lower() == 'buy':
                            newbidords.append(o)
                        elif order[ 'side' ].lower() == 'sell':

                            newaskords.append(o)
                            #self.orderStates[ex].append(order['orderID'])
                        

                    
                    #prnt('deribit #self.orderStates[ex]')                  
                    #print(#self.orderStates[ex])
                    
                    self.bid_ords[self.futtoks[token][ex]]=newbidords 
                    self.ask_ords[self.futtoks[token][ex]]=newaskords

                    #for order in self.bid_ords[self.futtoks[token][ex]]:

            except Exception as e:
                PrintException()    
    def mex_ords(self):
        while True:
            try:
                #extraPrint(False, ords)
                ex = 'bitmex'
                #self.orderStates[ex] = []
                ords = []
                orders = requests.get("http://localhost:4444/order").json()
                for fut in orders:
                    brem = False
                    arem = False
                    count = 0
                    
                    count = -1
                    addBidOrders = []
                    addAskOrders = []
                    token = None
                    for order in orders[fut]:    
                        count = count + 1
                        #print(order)
                        token = 'BTC'
                        if 'ETH' in order['symbol']:
                            token = 'ETH'
                        
                        order['qty'] = order['orderQty']
                        order['status'] = order['ordStatus']
                        if order['ordStatus'].lower() == 'canceled':

                            self.cancelledMex.append(order['orderID'])
                        if order['ordStatus'].lower() == 'new':
                            #print('bitmex order!')
                            #print('mex order')

                            order['status'] = 'new'

                            
                            order['name'] = self.futtoks[token][ex]
                            if order[ 'side' ].lower() == 'buy':
                                addBidOrders.append(order)
                            elif order[ 'side' ].lower() == 'sell':
                                addAskOrders.append(order)
                   
                    self.bid_ords[self.futtoks[token][ex]]=addBidOrders 
                    self.ask_ords[self.futtoks[token][ex]]=addAskOrders
            
            except Exception as e:
                PrintException()
    def mex_pos(self):
        while True:
            try:

                ex = 'bitmex'
                for fut in self.futures['bitmex']:
                    positions = requests.get("http://localhost:4444/position?symbol=" + fut).json()

                    for pos in positions:
                        size = pos['currentQty']
                        avgEntry = pos['avgEntryPrice']
                        floatingPl = pos['unrealisedPnlPcnt']
                        #if 'ETH' in pos['symbol']:
                            #extraPrint(False, pos)
                            #extraPrint(False, self.ethrate)
                        self.positions[pos['symbol']] = {
                            'name': pos['symbol'],
                            'size':         size,
                            'averagePrice': avgEntry,
                            'floatingPl': floatingPl}
            except:
                PrintException()

    def update_counts(self):
        while True:
            
            
            
            
                
            
            try:
                sleep(1)
                for ex in self.totrade:
                    for token in self.exchangeRates:
                        self.len_bid_ords[self.futtoks[token][ex]]    = len(self.bid_ords[self.futtoks[token][ex]]) - 1
                        self.ibid[self.futtoks[token][ex]] = self.len_bid_ords[self.futtoks[token][ex]] - 1

                        self.len_ask_ords[self.futtoks[token][ex]]    = len(self.ask_ords[self.futtoks[token][ex]]) - 1
                        self.iask[self.futtoks[token][ex]] = self.len_ask_ords[self.futtoks[token][ex]] - 1 
                        self.asksleft[self.futtoks[token][ex]] = self.asksleftbefore[self.futtoks[token][ex]] + self.len_ask_ords[self.futtoks[token][ex]]
                        self.bidsleft[self.futtoks[token][ex]] = self.bidsleftbefore[self.futtoks[token][ex]] + self.len_bid_ords[self.futtoks[token][ex]]
                    
                        try:

                            bid_ords = self.bid_ords
                            ask_ords = self.ask_ords
                            if 'bids' in  bid_ords:
                                self.bid_ords[self.futtoks[token][ex]] = bid_ords['bids']
                            if 'asks' in ask_ords:
                                self.ask_ords[self.futtoks[token][ex]] = ask_ords["asks"]
                            pos = dbpositions.find_one({"name": self.futtoks[token][ex]})
                            if pos is not None:
                                self.positions[self.futtoks[token][ex]] = pos
                        except:
                           PrintException()#abc=123#PrintException()
                        self.asksleft[self.futtoks[token][ex]] = max(self.len_ask_ords[self.futtoks[token][ex]], self.asksleftbefore[self.futtoks[token][ex]])

                        self.bidsleft[self.futtoks[token][ex]] = max(self.len_bid_ords[self.futtoks[token][ex]], self.bidsleftbefore[self.futtoks[token][ex]])
                        if ex == 'deribit':
                            try:
                                for order in self.bid_ords[self.futtoks[token][ex]]:
                                    if self.len_bid_ords[order['symbol']] > self.MAX_LAYERS + 1 and order['side'].lower() == 'buy':
                                        #brem = True
                                        #print('cancel 1')
                                        self.client.cancel( order['orderID'] )
                                for order in self.ask_ords[self.futtoks[token][ex]]:
                                    if self.len_ask_ords[order['symbol']] > self.MAX_LAYERS + 1 and order['side'].lower() == 'sell':
                                        #arem = True
                                        #print('cancel 6')
                                        self.client.cancel( order['orderID'] )
                                        count = 0
                                for order in self.bid_ords[self.futtoks[token][ex]]:
                                    #print(count)
                                    if count > self.MAX_LAYERS  + 1 and order['side'].lower() == 'buy':
                                        #brem = True
                                        #print('cancel 1')
                                        (self.client.cancel( order['orderID'] ))
                                    count = count + 1
                                count = 0
                                for order in self.ask_ords[self.futtoks[token][ex]]:
                                    #print(count)
                                
                                    if count > self.MAX_LAYERS + 1 and order['side'].lower() == 'sell':
                                        #arem = True
                                        #print('cancel 6')
                                        (self.client.cancel( order['orderID'] ))
                                    count = count + 1
                            except:

                               PrintException()#abc=123#PrintException()
                        if ex == 'bitmex':
                            try:
                                for order in self.bid_ords[self.futtoks[token][ex]]:
                                    if order['orderID'] not in self.cancelledMex:
                                        if (self.len_bid_ords[order['symbol']]) > self.MAX_LAYERS + 1 and order['side'].lower() == 'buy' :
                                            #brem = True
                                            #print('cancel 3')

                                            self.mex.Order.Order_cancel(orderID=order['orderID']).result()
                                    else:
                                        self.bid_ords[self.futtoks[token][ex]].remove(order)
                                for order in self.ask_ords[self.futtoks[token][ex]]:
                                    if order['orderID'] not in self.cancelledMex:
                                        if (self.len_ask_ords[order['symbol']]) > self.MAX_LAYERS + 1  and order['side'].lower() == 'sell' :
                                            #arem = True
                                            #print('cancel 4')

                                            self.mex.Order.Order_cancel(orderID=order['orderID']).result()
                                    else:
                                        self.ask_ords[self.futtoks[token][ex]].remove(order)
                            except:
                               PrintException()#abc=123#PrintException()
                            try:
                                count = 0
                                for order in self.bid_ords[self.futtoks[token][ex]]:
                                    if count > self.MAX_LAYERS  + 1 and order['side'].lower() == 'buy':
                                        if order['orderID'] not in self.cancelledMex:
                                            self.mex.Order.Order_cancel(orderID=order['orderID']).result()
                                        else:
                                            self.ask_ords[self.futtoks[token][ex]].remove(order)
                                    count = count + 1
                                count = 0
                                for order in self.ask_ords[self.futtoks[token][ex]]:
                                
                                    if count > self.MAX_LAYERS + 1 and order['side'].lower() == 'sell':
                                        if order['orderID'] not in self.cancelledMex:
                                            self.mex.Order.Order_cancel(orderID=order['orderID']).result()
                                        else:
                                            self.ask_ords[self.futtoks[token][ex]].remove(order)
                                    count = count + 1
                            except:
                               PrintException()#abc=123#PrintException()
                        if ex == 'bybit':
                            try:
                                for order in self.bid_ords[self.futtoks[token][ex]]:
                                    if count > self.MAX_LAYERS  + 1 and order['side'].lower() == 'buy':
                                        #brem = True
                                        #print('cancel 1')
                                        self.bit.Order.Order_cancel(order_id=order['orderID'] ).result()
                                    count = count + 1
                                count = 0
                                for order in self.ask_ords[self.futtoks[token][ex]]:
                                
                                    if count > self.MAX_LAYERS + 1 and order['side'].lower() == 'sell':
                                        #arem = True
                                        self.bit.Order.Order_cancel(order_id=order['orderID'] ).result()
                                    count = count + 1
                            except:
                               PrintException()#abc=123#PrintException()
                            try:
                                for order in self.bid_ords[self.futtoks[token][ex]]:
                                    if (self.len_bid_ords[order['symbol']]) > self.MAX_LAYERS + 1   and order['side'].lower() == 'buy' :
                                        #brem = True
                                        #print('cancel 2')
                                        self.bit.Order.Order_cancel(order_id=ords[count]['orderID'] ).result()
                                for order in self.ask_ords[self.futtoks[token][ex]]:
                                    if (self.len_ask_ords[order['symbol']]) > self.MAX_LAYERS + 1 and order['side'].lower() == 'sell':
                                        #arem = True
                                        #print('cancel 5')
                                        self.bit.Order.Order_cancel(order_id=ords[count]['orderID'] ).result()
                            except:
                               PrintException()#abc=123#PrintException()

                
            except Exception as e:
               PrintException()#abc=123
               PrintException()#abc=123#PrintException()        

             
    
    async def printer(self, **kwargs):
        data = kwargs
        
        request = kwargs['request']
        doprint = True
        if request["method"] == 'book.BTC-PERPETUAL.raw':
            return
        #if "public/subscribe" in request["method"] or "quote" in request['method'] or "price_index" in request["method"]:
            #self.update_mex_bit_pos_and_order()
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
            #print('printer')
            #print(str(len(data['response']['result'])))
            """
            for order in data['response']['result']:
                if order['direction'].lower() == 'buy':
                    self.deri_orders['bids'].append(order)
                if order['direction'].lower() == 'sell':
                    self.deri_orders['bids'].append(order)
                #print(order['order_id'])
                #print(order['direction'].lower())

                #print(order['order_state'])
            """
            doprint = False
        if "position" in request["method"]:
            self.positions[data['response']['result']['instrument_name']] = data['response']['result']
            doprint = False

            self.positions[data['response']['result']['instrument_name']]['floatingPl'] = data['response']['result']['floating_profit_loss']
                       
            extraPrint(False, self.positions)
        if "account" in request["method"]:
            self.deri_bal[data["response"]['result']['currency']] = data['response']['result']['equity']
            doprint = False
            extraPrint(False, self.deri_bal)

        if doprint == True and 'subscribe' not in request['method']:
            #print(2)
            extraPrint(False, repr(data))

             
    async def handle_subscription(self, data: dict):
        doprint = True
        if data["params"]["channel"] == 'book.BTC-PERPETUAL.raw':
            return


        #if "quote" in data["params"]["channel"] or "price_index" in data["params"]["channel"]:
            #self.update_mex_bit_pos_and_order()
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
        #print(data)
        if "open_orders" in data["params"]["channel"]:
            """
            #print('subscrption')
            #print(str(len(data['response']['result'])))
            
            for order in data['response']['result']:
                if order['direction'].lower() == 'buy':
                    self.deri_orders['bids'].append(order)
                if order['direction'].lower() == 'sell':
                    self.deri_orders['bids'].append(order)
                #print(order['order_id'])
                #print(order['side'].lower())
                #print(order['order_status'])
            """
            doprint = False
        if "position" in data["params"]["channel"]:
            self.positions[data['response']['result']['instrument_name']] = data['response']['result']
            
            self.positions[data['response']['result']['instrument_name']]['floatingPl'] = data['response']['result']['floating_profit_loss']
            doprint = False
        if "account" in data["params"]["channel"]:
            self.deri_bal[data["response"]['result']['currency']] = data['response']['result']['euuity']
            doprint = False
            extraPrint(False, self.deri_bal)
        if doprint == True:
            #print(1)
            extraPrint(False, repr(data))

    

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
            res = requests.get("https://www.deribit.com/api/v2/public/get_funding_chart_data?instrument_name=BTC-PERPETUAL&length=1m").json()['result']

            self.exchangeRates['BTC']['deribit'] = res['interest_8h'] * 3
    
            res = requests.get("https://www.deribit.com/api/v2/public/get_funding_chart_data?instrument_name=ETH-PERPETUAL&length=1m").json()['result']

            self.exchangeRates['ETH']['deribit'] = res['interest_8h'] * 3

        except Exception as e:
            extraPrint(False, e)
            PrintException()#abc=123#PrintException()
        try:
            r = random.randint(0, 50)
            if self.mexfundingfirst == True or r == 0:
                self.mexfundingfirst = False
                res = self.mex.Instrument.Instrument_getActive().result()
                
                for inst in res[0]:
                    if inst['symbol'] == 'XBTUSD':
                        self.exchangeRates['BTC']['bitmex'] = float(inst['fundingRate']) * 3
                    if inst['symbol'] == 'ETHUSD':
                        self.exchangeRates['ETH']['bitmex'] = float(inst['fundingRate']) * 3
                

        except Exception as e:
            extraPrint(False, e)
            PrintException()#abc=123#PrintException()
        try:
            
            res = self.bit.Funding.Funding_predictedRate(symbol="BTCUSD").result()
            #print(res)
            if 'bybit' in self.exchangeRates['BTC']:
                resold = self.exchangeRates['BTC']['bybit']
            else:
                resold = 0
            if res is not None:
                res = float(res[0]['result']['funding_rate']) * 3
            else:
                res = resold
            self.exchangeRates['BTC']['bybit'] = res
            res = self.bit.Funding.Funding_predictedRate(symbol="ETHUSD").result()
            if 'bybit' in self.exchangeRates['ETH']:
                resold = self.exchangeRates['ETH']['bybit']
            else:
                resold = 0
            if res is None:
                res = resold
            else:

               res = float(res[0]['result']['funding_rate']) * 3

            self.exchangeRates['ETH']['bybit'] = res
            extraPrint(False, self.exchangeRates)
        except Exception as e:
            extraPrint(False, e) # extraPrint(False, e)
            PrintException()#abc=123#PrintException()
            PrintException()#abc=123#PrintException()
        extraPrint(False, self.exchangeRates)
        positive = {}
       #print(self.exchangeRates)
        for coins in self.exchangeRates:
            h = -99999999
            l = 999999999
            for funding in self.exchangeRates[coins]:
                k = funding
                val = self.exchangeRates[coins][funding] * 1000000
                
                if val > h:
                    h = val
                    winner = k

                    if val > 0:
                        positive[coins] = True
                    else:
                        positive[coins] = False
                if val < l:
                    l = val
                    loser = k

                    if val > 0:
                        positive[coins] = True
                    else:
                        positive[coins] = False
                
            self.arbmult[coins]=({"long": loser, "short": winner})
           #print(self.arbmult)
                
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
            self.PCT_LIM_LONG[thetoken]  = self.PCT_LIM_LONG[thetoken]  *  self.percs[thetoken]
    
            self.LEV_LIM_LONG[thetoken] = self.LEVERAGE_LIMIT_LONG
            self.LEV_LIM_SHORT[thetoken] = self.LEVERAGE_LIMIT_SHORT
            self.LEV_LIM_LONG[thetoken] = self.LEV_LIM_LONG[thetoken]  * self.percs[thetoken]
            self.LEV_LIM_SHORT[thetoken] = self.LEV_LIM_SHORT[thetoken] * self.percs[thetoken]
    
        if self.arbmult[token]['short'] == ex:
            self.LEV_LIM_SHORT[token] = self.LEV_LIM_SHORT[token] * 1
            self.PCT_LIM_SHORT[token]  = self.PCT_LIM_SHORT[token] * 1
    
            self.MAX_SKEW = self.MAX_SKEW * 1     
        
        if self.arbmult[token]['long'] == ex:
            self.MAX_SKEW = self.MAX_SKEW * 1     
        
            self.LEV_LIM_LONG[token] = self.LEV_LIM_LONG[token] * 1
            self.PCT_LIM_LONG[token]  = self.PCT_LIM_LONG[token] * 1
        extraPrint(False, self.LEV_LIM_LONG)
        extraPrint(False, self.LEV_LIM_SHORT)
        #0.0011
        #119068
    def update_balances( self ):
        try:
            bal = self.client.account()['equity']
            self.bals['deribit-btc'] = bal
            account         = self.ccxt.fetchBalance({'currency': 'ETH'})
            bal_eth         = account['info']['result'][ 'equity' ] 
            self.ethrate = self.get_spot("ETH") / self.get_spot("BTC")
            self.bals['deribit-eth'] = bal_eth * self.ethrate

        except:
            PrintException()#abc=123#PrintException()
        try:
            if testing == False:
                res = requests.get("http://localhost:4444/margin").json()[0]
            
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
            PrintException()#abc=123#PrintException()
        try:
            bal = self.bit.Wallet.Wallet_getBalance(coin="BTC").result()[0]['result']['BTC']['equity']
            self.bals['bybit-btc'] = bal
            bal = self.bit.Wallet.Wallet_getBalance(coin="ETH").result()[0]['result']['ETH']['equity']
            extraPrint(False, 'bybit bal eth: ' + str(bal))
            self.ethrate = self.get_spot("ETH") / self.get_spot("BTC")
            self.bals['bybit-eth'] = bal * self.ethrate
        except Exception as e:
            extraPrint(False, e)
            PrintException()#abc=123#PrintException()
        
        t = 0
        l = 99999999999
        c = 1
        self.bals['total'] = 0

        if 'total' in self.bals:
            told = self.bals['total']
        for bal in self.bals:
            if self.bals[bal] < l and self.bals[bal] != 0:
                extraPrint(False, bal)
                extraPrint(False, self.bals[bal])
                l = self.bals[bal]
            if self.bals[bal] != 0:
                c = c + 1

            t = t + self.bals[bal]
            
        self.bals['total'] = t
        
        if l * c == 0:
            try:
                self.bals['total'] = told
            except:
                abc123 = 1
        return (self.bals)
    def create_client( self ):
        self.client = RestClient( KEY, SECRET, URL )
        self.ccxt     = ccxt.deribit({
            'apiKey': KEY,
            'secret': SECRET,
        })
    
    def get_asks_bids(self, ex, token):
        asks = []
        bids = []
        try:
            bbo     = self.get_bbo( ex, self.futtoks[token][ex] )
            bid_mkt = bbo[ 'bid' ]
            ask_mkt = bbo[ 'ask' ]
            asks.append(ask_mkt)
            bids.append(bid_mkt)
            tsz = self.get_ticksize( self.futtoks[token][ex] ) 
            if bid_mkt is None and ask_mkt is None:
                if token == 'ETH':
                    spot = self.get_spot('ETH')
                else:
                    spot = self.get_spot('BTC')
                #print('issue 1 with bid ask in asks/bids calc')
                bid_mkt = ask_mkt = spot
            elif bid_mkt is None:
                if token == 'ETH':
                    spot = self.get_spot('ETH')
                else:
                    spot = self.get_spot('BTC')
                #print('issue 2 with bid ask in asks/bids calc')
                bid_mkt = min( spot, ask_mkt )
            elif ask_mkt is None:
                if token == 'ETH':
                    spot = self.get_spot('ETH')
                else:
                    spot = self.get_spot('BTC')
                #print('issue 3 with bid ask in asks/bids calc')
                ask_mkt = max( spot, bid_mkt )
            mid_mkt = 0.5 * ( bid_mkt + ask_mkt )


            
            eps = 0.0005

            riskfac     = math.exp( eps )
                    

            
            
            bid0            = bid_mkt
            newbids    = [ bid0 * riskfac ** -i for i in range( 1, int(self.MAX_LAYERS) + 1 ) ]
         

            newbids[ 0 ]   = ticksize_floor( bids[ 0 ], tsz )
            for bid in newbids:
                bids.append(bid)

            ask0            = ask_mkt
             
            newasks    = [ ask0 * riskfac ** i for i in range( 1, int(self.MAX_LAYERS)+ 1 ) ]
            prc = asks[0]
            newasks[ 0 ]   = ticksize_floor( asks[ 0 ], tsz )
            for ask in newasks:
                asks.append(ask)
            nasks = []
            nbids = []
            for ask in asks:
                ask = ticksize_ceil( ask , tsz  )
                nasks.append(ask)
            for bid in bids:
                bid = ticksize_ceil( bid , tsz  )
                nbids.append(bid)
            asks = nasks
            bids = nbids
        except Exception as e:
            #print('no asks bids in functino')
            PrintException()#abc=123#PrintException()
            try:
                bbo     = self.get_bbo( ex, self.futtoks[token][ex] )
                bid = bbo[ 'bid' ]
                ask = bbo[ 'ask' ]
                
                asks.append(ask)
                bids.append(bid)
            except Exception as e:
                extraPrint(False, 'no bid, returning')
                   
        #print('asks: ' + str(asks) + ', bids: ' + str(bids))
        return({'asks': asks, 'bids': bids})
    def get_eth( self ):
        r = requests.get('https://api.binance.com/api/v1/ticker/price?symbol=ETHUSDT').json()
        return float(r['price'])
    def get_bbo( self, exchange, contract ): # Get best b/o excluding own orders
        if exchange == 'deribit':
            
            # Get orderbook
            ob      = self.client.getorderbook( contract )
            bids    = ob[ 'bids' ]
            asks    = ob[ 'asks' ]

            best_bid    = bids[0]['price']
            best_ask    = asks[0]['price']

            
        if exchange == 'bitmex':

            if testing == False:
                t = requests.get('http://localhost:4444/instrument?symbol=' + contract).json()[0]
            
                best_ask = t['askPrice']
                best_bid = t['bidPrice']
               
                        
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
               PrintException()#abc=123#PrintException()



            
            extraPrint(False, result)
            try:
                best_bid    = result[0]['result'][0]['bid_price']
                best_ask    = result[0]['result'][0]['ask_price']
            except Exception as e:
                extraPrint(False, e)
                PrintException()#abc=123#PrintException()
        extraPrint(False, exchange)
        best_bid = round(float(best_bid) * 100) / 100

        best_ask = round(float(best_ask) * 100) / 100
        return { 'bid': float(best_bid), 'ask': float(best_ask) }
    
        
    def get_futures( self ): # Get all current futures instruments
        self.futures['bybit'] = ['ETHUSD-bybit','BTCUSD']
        self.futures['deribit'] = [ 'ETH-PERPETUAL','BTC-PERPETUAL']  
        self.futures['bitmex'] = [ 'ETHUSD', 'XBTUSD']
        self.exfuts = {}
        for ex in self.futures:
            for pair in self.futures[ex]:
                self.exfuts[pair] = ex
        for token in self.exchangeRates:
            self.futtoks[token] = {}
        for ex in self.totrade:
            for instrument in self.futures[ex]:

                if 'ETH' in instrument:
                    self.futtoks['ETH'][ex] = self.futures[ex][0]
                else: 
                    self.futtoks['BTC'][ex] = self.futures[ex][1]
       
                self.ibid[instrument] = 0
                self.iask[instrument] = 0
                
        extraPrint(False, self.futtoks)
        
    def get_pct_delta( self ):  
        return sum( self.deltas.values()) / self.equity_btc

    
    def get_spot( self, coin ):
    
        if 'ETH' in coin:
            return self.get_bbo('bitmex', 'ETHUSD')['bid']
        else:
            return self.get_bbo('bitmex', 'XBTUSD')['bid']
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
        extraPrint(False, self.exchangeRates)
        extraPrint(False, self.len_bid_ords)
        extraPrint(False, self.len_ask_ords)
        
            
        if not self.output:
            return None
        
        self.update_status()
        
        now     = datetime.utcnow()
        days    = ( now - self.start_time ).total_seconds() / SECONDS_IN_DAY
        print   (     'Start Time:        %s' % self.start_time.strftime( '%Y-%m-%d %H:%M:%S' ))
        print   (     'Current Time:      %s' % now.strftime( '%Y-%m-%d %H:%M:%S' ))
        print   (     'Days:              %s' % round( days, 1 ))
        print   (     'Hours:             %s' % round( days * 24, 1 ))
        print   (     'Reference Spot Price BTC:        %s' % self.get_spot('BTC'))
        print   (     'Reference Spot Price ETH:        %s' % self.get_spot('ETH'))
        
        
        pnl_usd = self.equity_usd - self.equity_usd_init
        pnl_btc = self.equity_btc - self.equity_btc_init
        
        print   (     'Equity ($):        %7.2f'   % self.equity_usd)
        print  (     'P&L ($)            %7.2f'   % pnl_usd)
        print   (     'Equity (BTC):      %7.4f'   % self.equity_btc)
        print   (     'P&L (BTC)          %7.4f'   % pnl_btc)

        print   (     '\nPositions: ')

        t = 0
        a = 0   
        te = 0
        ae = 0
        usd = 0
        table = PrettyTable(['Exchange', 'Symbol', 'Position', 'Bid/Ask Order Counts', 'Max. Qty of Orders',   'BBO', '+/- BBO, Best Bid/Ask'])
        
        qty = {}
        
        restartThread = False
        for pos in self.positions:
            qty[pos] = 0
            if 'ETH' in pos:
                ae = ae + math.fabs(self.positions[pos]['size'])
                te = te + self.positions[pos]['size']
            else:
                a = a + math.fabs(self.positions[pos]['size'])
                t = t + self.positions[pos]['size']
            len_ords = len(self.bid_ords[pos]) + len(self.ask_ords[pos])
            l = 999999999999999999999999
            h = 0
            lwin = ""
            hwin = ""
            bids = 0
            asks = 0
            
            self.len_bid_ords[pos] = len(self.bid_ords[pos] )
            self.len_ask_ords[pos]  = len(self.ask_ords[pos] )
            bidaskcount = { 'bids': self.len_bid_ords[pos], 'asks': self.len_ask_ords[pos]}
            bidorask = 'neither'
            if bidaskcount['asks'] > bidaskcount['bids']:
                bidorask = 'ask'
            elif bidaskcount['asks'] < bidaskcount['bids']:
                bidorask = 'bid'
            if bidorask == 'neither':
                thebbo = self.get_bbo(self.exfuts[pos], pos)
                bbo = thebbo['bid']
                thebid = thebbo['bid']
                theask = thebbo['ask']
            else:
                thebbo = self.get_bbo(self.exfuts[pos], pos)
                bbo = thebbo[bidorask]
                thebid = thebbo['bid']
                theask = thebbo['ask']
            closest = {}
            closest['ask'] = thebbo['ask']
            closest['bid'] = thebbo['bid']
            la = 999999999999999999999999
            ha = 0
            lb = 999999999999999999999999
            hb = 0
            lwin = ""
            hwin = ""
            prices = {}
            prices['asks'] = []
            prices['bids'] = []
            for order in self.bid_ords[pos]:
                prices['bids'].append(float(order['price']))
                if float(order['price']) != 0:
                    if float(order['price']) > hb:
                        hb = float(order['price'])
                    if float(order['price']) < lb:
                        lb = float(order['price'])
                    if float(order['qty']) > qty[pos]:
                        qty[pos] = float(order['qty'])
            for order in self.ask_ords[pos]:
            
                prices['asks'].append(float(order['price']))
                if float(order['price']) != 0:
                    if float(order['price']) > ha:
                        ha = float(order['price'])
                    if float(order['price']) < la:
                        la = float(order['price'])
                    if float(order['qty']) > qty[pos]:
                        qty[pos] = float(order['qty'])
            
            closest = {'bid': hb, 'ask': la}

                
            
            
            if bidorask == 'neither':
                bidorask = 'bid'
            table.add_row   ([self.exfuts[pos], pos.replace('-bybit', ''), self.positions[pos]['size'], str(bidaskcount), qty[pos], bbo, str(closest[bidorask] - bbo)])
            usd = usd + self.positions[pos]['size']
            
            if 'BTC' in pos and (closest[bidorask] - bbo > 5 or closest[bidorask] - bbo < -5):
                restartThread = True
            if 'ETH' in pos and (closest[bidorask] - bbo > 1 or closest[bidorask] - bbo < -1):
                restartThread = True
            
        print  (     table)
        
        diff = t - self.oldt
        diffe = te - self.oldte
        self.oldt = t
        self.oldte = te
        print   (     '\nNet delta (exposure) BTC: $' + str(t) + ', difference since last status output: ' + str(diff))
        print   (     'Net delta (exposure) ETH: $' + str(te) + ', difference since last status output: ' + str(diffe))
        print   (     'Total absolute delta (IM exposure) BTC: $' + str(a))
        print   (     'Total absolute delta (IM exposure) ETH: $' + str(ae))
        print   (     'Total absolute delta (IM exposure) combined: $' + str(ae + a))
        self.IM = 0
        self.IM = (0.01 + (((a+ae)/self.equity_usd) *0.005))*100
        self.LEV = 0    
        self.LEV = round((ae+a)/self.equity_usd * 1000) / 1000  
        self.IM = round(self.IM * 1000)/1000
        
        print  (     'Actual initial margin across all accounts: ' + str(self.IM) + '% and leverage is ' + str(round(self.LEV * 1000)/1000) + 'x')
        print  (     'Lev max short BTC: ' + str(round(self.LEV_LIM_SHORT['BTC'] * 1000) / 1000) + ' and long: ' + str(round(self.LEV_LIM_LONG['BTC'] * 1000) / 1000) + ' and percent of BTC in position out of max for short, then long: ' + str(round((a / self.equity_usd) / self.LEV_LIM_SHORT['BTC'] * 1000 ) / 10)+ '%, ' + str(round((a / self.equity_usd) / self.LEV_LIM_LONG['BTC'] * 1000 ) / 10) + '%') 
        print  (     'Lev max short ETH: ' + str(round(self.LEV_LIM_SHORT['ETH'] * 1000) / 1000) + ' and long: ' + str(round(self.LEV_LIM_LONG['ETH'] * 1000) / 1000) + ' and percent of ETH in position out of max for short, then long: ' + str(round((ae / self.equity_usd) / self.LEV_LIM_SHORT['ETH'] * 1000 ) / 10) + '%, ' + str(round((ae / self.equity_usd) / self.LEV_LIM_LONG['ETH'] * 1000 ) / 10) + '%') 
        string = 'Long / short BTC: ' + self.arbmult['BTC']['long'] + ' / ' + self.arbmult['BTC']['short']
        string = string + ' and long / short ETH: ' + self.arbmult['ETH']['long'] + ' / ' + self.arbmult['ETH']['short']

        print   (     string)    
        print   (     '\nMean Loop Time: %s' % round( self.mean_looptime, 2 ))

        for token in self.futtoks:
            for ex in self.futtoks[token]:
                extraPrint(False, [token, ex])
                self.calculate_eth_btc(token, ex)    
                extraPrint(False, self.futtoks[token][ex])
                extraPrint(False, self.len_bid_ords[self.futtoks[token][ex]])
                extraPrint(False, self.len_ask_ords[self.futtoks[token][ex]])
    def editOrders(self, ex, token):
        asks = []
        bids = []
        askbids = self.get_asks_bids(ex, token)
        asks = askbids['asks']
        bids = askbids['bids']
        skew_size = {}
        skew_size['BTC'] = 0
        skew_size['ETH'] = 0
        qty = self.qty
        if self.qty == None:
            qty = MIN_ORDER_SIZE
        if token == 'BTC-PERPETUAL':
            qty = qty / 10
        qty = round(qty)
        for k in self.positions:
            if 'ETH' in k:
                skew_size['ETH'] = skew_size['ETH'] + self.positions[k]['size']
            else:
                skew_size['BTC'] = skew_size['BTC'] + self.positions[k]['size']

        # bid edit
        try:
            if ex == 'deribit':
                extraPrint(False, self.futtoks[token][ex])
                extraPrint(False, self.iask[self.futtoks[token][ex]])
                extraPrint(False, self.bid_ords)
                extraPrint(False, self.len_bid_ords[self.futtoks[token][ex]])


            mexAmendOrds = []
            for i in range(0, min(len(asks),(len(bids)))):
                gogo = True
                if len(self.bid_ords[self.futtoks[token][ex]]) > i:
                    if 'status' in self.bid_ords[self.futtoks[token][ex]][i]:
                        if self.bid_ords[self.futtoks[token][ex]][i]['status'] == 'new':
                        
                            if float(bids[i]) == float(self.bid_ords[self.futtoks[token][ex]][i]['price']):
                                gogo = False 

                                #print(' ')
                                #print(ex + ' ' + self.futtoks[token][ex] + ' bid price  at ' + str(bids[i]) + ' unchanged! skippping it!')
                                #print(' ') 
                            if gogo == True and len(self.bid_ords[self.futtoks[token][ex]]) > i:
                            #print('min asks bids 4: ' + str(self.asksleftbefore[self.futtoks[token][ex]]) + ', ' + str(self.bidsleftbefore[self.futtoks[token][ex]]))
                                oid = self.bid_ords[self.futtoks[token][ex]][i ][ 'orderID' ]
                                self.ibid[self.futtoks[token][ex]] = self.ibid[self.futtoks[token][ex]] - 1
                                if ex == 'bitmex':
                                    self.bid_ords[self.futtoks[token][ex]][i ][ 'price' ] = bids[i]
                                    mexAmendOrds.append({"orderID":oid, "price": bids[i]})
            if ex == 'bitmex':
                if len(mexAmendOrds) > 0:
                    try:
                        self.mex.Order.Order_amendBulk(orders=json.dumps(mexAmendOrds)).result()
                    except:
                        PrintException()#abc=123
            for i in range(0, min(len(asks),(len(bids)))):
                gogo = True
                if len(self.bid_ords[self.futtoks[token][ex]]) > i:
                    if 'status' in self.bid_ords[self.futtoks[token][ex]][i]:
                        if self.bid_ords[self.futtoks[token][ex]][i]['status'] == 'new':
                        
                            if float(bids[i]) == float(self.bid_ords[self.futtoks[token][ex]][i]['price']):
                                gogo = False 

                                #print(' ')
                                #print(ex + ' ' + self.futtoks[token][ex] + ' bid price  at ' + str(bids[i]) + ' unchanged! skippping it!')
                                #print(' ') 
                            if gogo == True and len(self.bid_ords[self.futtoks[token][ex]]) > i:
                            #print('min asks bids 4: ' + str(self.asksleftbefore[self.futtoks[token][ex]]) + ', ' + str(self.bidsleftbefore[self.futtoks[token][ex]]))
                                oid = self.bid_ords[self.futtoks[token][ex]][i ][ 'orderID' ]
                                self.ibid[self.futtoks[token][ex]] = self.ibid[self.futtoks[token][ex]] - 1
                                try:
                                    #print(token)
                                    if ex == 'deribit':
                                        
                                        #print( 'edit deribit bid : ' + str(oid) + ' at bid ' + str(asks[i]))
                                        #print('edit deribit bid ' + str(oid))
                                        try:
                                            extraPrint(False, self.client.edit( oid, qty,  bids[i] ))
                                        except:
                                            abc123=1
                                    if ex == 'bybit':
                                        #print('edit bybit bid: ' + str(oid))
                                        try:
                                            extraPrint(False, self.bit.Order.Order_replace(order_id=oid, symbol=self.futtoks[token][ex],  p_r_price=bids[i]).result())
                                        except:
                                            PrintException()#abc=123
                                except Exception as e:
                                    PrintException()
                                    extraPrint(False, e)
                                    PrintException()#abc=123#extraPrint(False, e)

                                    extraPrint(False, e)
                    
        except Exception as e:
            PrintException()
            PrintException()#abc=123#extraPrint(False, e)
        # ask edit
        
        try:
            if ex == 'deribit':
                extraPrint(False, self.futtoks[token][ex])
                extraPrint(False, self.iask[self.futtoks[token][ex]])
                
                extraPrint(False, self.len_ask_ords[self.futtoks[token][ex]])
            mexAmendOrds = []
            for i in range(0, min(len(asks),(len(bids)))):
                if len(self.ask_ords[self.futtoks[token][ex]]) > i:
                    if 'status' in self.ask_ords[self.futtoks[token][ex]][i]:
                        if self.ask_ords[self.futtoks[token][ex]][i]['status'] == 'new':
                            gogo = True
                            
                            if float(asks[i]) == float(self.ask_ords[self.futtoks[token][ex]][i]['price']):
                                gogo = False 

                                #print(' ')
                                #print(ex + ' ' + self.futtoks[token][ex] + ' ask price at ' + str(asks[i]) + ' unchanged! skippping it!')
                                #print('     ') 
                            
                        if gogo == True and len(self.ask_ords[self.futtoks[token][ex]]) > i:
                            
                            extraPrint(False, 'min asks bids 5: ' + str(self.asksleftbefore[self.futtoks[token][ex]]) + ', ' + str(self.bidsleftbefore[self.futtoks[token][ex]]))
                            oid = self.ask_ords[self.futtoks[token][ex]][i ][ 'orderID' ]
                            self.ask_ords[self.futtoks[token][ex]][i ]['price'] = asks[i]
                            self.iask[self.futtoks[token][ex]] = self.iask[self.futtoks[token][ex]] - 1
                            if ex == 'bitmex':
                                try:
                                    mexAmendOrds.append({"orderID": oid, "price": asks[i]})
                                except:
                                    PrintException()#abc=123
            if ex == 'bitmex':
                if len(mexAmendOrds) > 0:
                    try:

                        self.mex.Order.Order_amendBulk(orders=json.dumps(mexAmendOrds)).result()
                    except:
                        PrintException()#abc=123
            for i in range(0, min(len(asks),(len(bids)))):
                if len(self.ask_ords[self.futtoks[token][ex]]) > i:
                    if 'status' in self.ask_ords[self.futtoks[token][ex]][i]:
                        if self.ask_ords[self.futtoks[token][ex]][i]['status'] == 'new':
                            gogo = True
                            
                            if float(asks[i]) == float(self.ask_ords[self.futtoks[token][ex]][i]['price']):
                                gogo = False 

                                #print(' ')
                                #print(ex + ' ' + self.futtoks[token][ex] + ' ask price at ' + str(asks[i]) + ' unchanged! skippping it!')
                                #print('     ') 
                            
                        if gogo == True and len(self.ask_ords[self.futtoks[token][ex]]) > i:
                            
                            extraPrint(False, 'min asks bids 5: ' + str(self.asksleftbefore[self.futtoks[token][ex]]) + ', ' + str(self.bidsleftbefore[self.futtoks[token][ex]]))
                            oid = self.ask_ords[self.futtoks[token][ex]][i ][ 'orderID' ]

                            self.iask[self.futtoks[token][ex]] = self.iask[self.futtoks[token][ex]] - 1
                            try:
                                extraPrint(False, token)
                                if ex == 'deribit':
                                    qty = self.qty
                                    if self.qty == None:
                                        qty = MIN_ORDER_SIZE
                                    if token == 'BTC':
                                        qty = qty / 10
                                    qty = round(qty)
                                   #print( 'edit deribit ask : ' + str(oid) + ' at ask ' + str(asks[i]))
                                    (self.client.edit( oid, qty,  asks[i] ))
                                if ex == 'bybit':
                                    #print(oid)
                                    try:
                                    #print('edit bybit ask: ' + str(oid))
                                        extraPrint(False, self.bit.Order.Order_replace(order_id=oid, symbol=self.futtoks[token][ex], p_r_price=asks[i]).result())
                                    except:
                                        PrintException()#abc=123
                            except Exception as e:
                                PrintException()#abc=123#PrintException()
                                extraPrint(False, e)
                                PrintException()#abc=123#extraPrint(False, e)
                                extraPrint(False, e)
           
        except Exception as e:
            PrintException()#abc=123#PrintException()
            PrintException()#abc=123#extraPrint(False, e)   
        self.asksleft[self.futtoks[token][ex]] = self.asksleftbefore[self.futtoks[token][ex]] + self.len_ask_ords[self.futtoks[token][ex]]
        self.bidsleft[self.futtoks[token][ex]] = self.bidsleftbefore[self.futtoks[token][ex]] + self.len_bid_ords[self.futtoks[token][ex]]         
    def place_orders( self, ex, token ):
        #self.update_positions()
        self.editOrders(ex, token)
          
        fut = self.futtoks[token][ex]
        #print('fut begin: ' + fut + ' token: ' + token + ' ex: ' + ex)
        asks = []
        bids = []
        askbids = self.get_asks_bids(ex, token)
        asks = askbids['asks']
        bids = askbids['bids']
        
        
        if self.futtoks[token][ex] not in self.doneFuts: 
            self.doneFuts.append(self.futtoks[token][ex])
           #print(self.doneFuts)
        else:
            #print(fut + ' done! returning') 
            return
        ords = []
        
        #print('fut: ' + fut + ' token: ' + token + ' ex: ' + ex)
        
        extraPrint(False, 'fut, token')
        extraPrint(False, fut)
        extraPrint(False, token)
        if self.monitor:
            return None
        con_sz  = self.con_size  

        asks = []
        bids = []
        
        extraPrint(False, ex)
        extraPrint(False, token)
        extraPrint(False, self.futtoks[token][ex])
        extraPrint(False, self.len_bid_ords)
        extraPrint(False, self.len_ask_ords)
         ## FIX THIS IN PROD

        #self.PCT_LIM_SHORT[token]  = self.INITIAL_MARGIN_LIMIT_SHORT
        #self.PCT_LIM_LONG[token]  = self.INITIAL_MARGIN_LIMIT_LONG
        #self.LEV_LIM_SHORT[token]  = self.LEVERAGE_LIMIT_SHORT
        #self.LEV_LIM_LONG[token]  = self.LEVERAGE_LIMIT_LONG
        #else:
            
            #self.PCT_LIM_SHORT[token]  = self.INITIAL_MARGIN_LIMIT_SHORT
            #self.PCT_LIM_LONG[token]  = self.INITIAL_MARGIN_LIMIT_LONG
            #self.LEV_LIM_SHORT[token]  = self.LEVERAGE_LIMIT_SHORT
            #self.LEV_LIM_LONG[token]  = self.LEVERAGE_LIMIT_LONG
        bal_btc         = self.bals['total']
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
       #print(fut + 'im: ' + str(self.IM) + ' lim long: ' + str(self.PCT_LIM_LONG[token]) + ' lim short: ' + str(self.PCT_LIM_SHORT[token]))
       #print(fut + ' lev: ' + str(self.LEV) + ' lim long: ' + str(self.LEV_LIM_LONG[token]) + ' lim short: ' + str(self.LEV_LIM_SHORT[token]))
        #if self.IM > self.PCT_LIM_LONG[token]:
        #    place_bids = False
        #    nbids = 0
        #if self.IM > self.PCT_LIM_SHORT[token]:
        #    place_asks = False
        #    nasks = 0
        extraPrint(False, self.LEV)
        extraPrint(False, self.LEV_LIM_LONG[token])
        a = 0
        ae = 0
        for pos in self.positions:

            if 'ETH' in pos:
                ae = ae + math.fabs(self.positions[pos]['size'])
            else:
                a = a + math.fabs(self.positions[pos]['size'])
        if 'ETH' in token:
            if (((ae / self.equity_usd) / self.LEV_LIM_LONG['ETH'] * 1000 ) / 10) > 100:
            
                place_bids = False
                nbids = 0
            if (((ae / self.equity_usd) / self.LEV_LIM_SHORT['ETH'] * 1000 ) / 10) > 100:
                place_asks = False
                nasks = 0
        else:
            if (((a / self.equity_usd) / self.LEV_LIM_LONG['BTC'] * 1000 ) / 10) > 100:
            
                place_bids = False
                nbids = 0
            if (((a / self.equity_usd) / self.LEV_LIM_SHORT['BTC'] * 1000 ) / 10) > 100:
                place_asks = False
                nasks = 0
        min_order_size_btc = MIN_ORDER_SIZE / spot
        # 18 / (7000) 0.02571428571428571428571428571429
        # 22 / (7000) 0.00314285714285714285714285714286
        qtybtc  = float(max( PCT_QTY_BASE  * bal_btc, min_order_size_btc))
       
        extraPrint(False, place_bids)
        extraPrint(False, place_asks)

        skew_size = {}
        skew_size['ETH'] = 0
        skew_size['BTC'] = 0
        for k in self.positions:
            if 'ETH' in k:
                skew_size['ETH'] = skew_size['ETH'] + self.positions[k]['size']
            else:
                skew_size['BTC'] = skew_size['BTC'] + self.positions[k]['size']

        token = 'BTC'
        if 'ETH' in fut:
            token = 'ETH'
        try:
            prc = self.get_bbo(ex, fut)['bid']
        except Exception as e:
            abc123 = 1
            #print('no bid, returning')
            
        if ex == 'bitmex':
            self.qty = round ( float(prc) * qtybtc )
            
        if self.qty > self.maxqty:
            self.maxqty = self.qty
        self.MAX_SKEW = self.MAX_SKEW_OLD
        self.MAX_SKEW = self.qty * 2.25
        
        
          
        asks = []
        bids = []
        askbids = self.get_asks_bids(ex, token)
        asks = askbids['asks']
        bids = askbids['bids'] 
        r = None

        #short, are we selling?
        avgpos = {}
        countpos = {}
        for token2 in self.exchangeRates:
            avgpos[token2] = 0
            countpos[token2] = 0
            for ex2 in self.totrade:
                avgpos[token2] = avgpos[token2] + math.fabs(self.positions[self.futtoks[token2][ex2]]['size'])
                countpos[token2] = countpos[token2] + 1
            avgpos[token2] = avgpos[token2] / countpos[token2]
        """
        if math.fabs(self.positions[self.futtoks[token][ex]]['size']) > 1.1 * avgpos[token]:
            #print(ex + '  ' + token + ' is over 1.1x the average balance. Let\'s reduce creatively')
            #print('min asks bids 3: ' + str(self.asksleft[self.futtoks[token][ex]]) + ', ' + str(self.bidsleft[self.futtoks[token][ex]]))
            try:
                prc = self.get_bbo(ex, fut)['bid']
            except Exception as e:
                abc123 = 1
                #print('no bid, returning')
                
            if ex == 'bitmex':
                self.qty = round ( float(prc) * qtybtc )
                
            if self.qty > self.maxqty:
                self.maxqty = self.qty
            self.MAX_SKEW = self.MAX_SKEW_OLD
            self.MAX_SKEW = self.qty * 5.5
            extraPrint(False, token + ', ' + ex + ' qty: ' + str(self.qty / 10))
            if self.positions[self.futtoks[token][ex]]['size'] >= 0:
                ex3 = self.arbmult[token]['short']
                if ex3 == 'bitmex':
                    mexBids = []
                    for i in range(self.asksleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                        mexBids.append({"symbol":self.futtoks[token]['bitmex'], "orderQty":round(self.qty*0.66), "price":bids[i],"execInst":"ParticipateDoNotInitiate"})
                   
                    if  len(mexBids) > 0:
                        #if self.qty + skew_size[token] <= self.MAX_SKEW:
                            if self.domex == True:
                                r2 = Timer(0.5, self.mextimer, ())
                                r2.start()
                                #self.domex = False
                                r = self.mex.Order.Order_newBulk(orders=json.dumps(mexBids)).result()
                                #print(r)
                
                
                if ex == 'bitmex':
                    mexAsks = []
                    for i in range(self.asksleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                        mexAsks.append({"symbol":self.futtoks[token]['bitmex'], "orderQty":-1*round(self.qty), "price":asks[i],"execInst":"ParticipateDoNotInitiate"})
                    
                    if  len(mexAsks) > 0:
                        #if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                            if self.domex == True:
                                r2 = Timer(0.5, self.mextimer, ())
                                r2.start()
                                #self.domex = False
                                r = self.mex.Order.Order_newBulk(orders=json.dumps(mexAsks)).result()
                
                
                for i in range(self.asksleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                    #print('buy short arb exchange at reduced qty')
                    if ex3 == 'deribit':
                        
                        if 'BTC-PERPETUAL' == self.futtoks[token]['deribit']:
                            

                            #print('token2: ' + self.futtoks[token]['deribit'])
                            
                            #print('futtoks: ' + self.futtoks[token]['deribit'])
                            if  self.bidsleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                                #f self.qty + skew_size[token] <= self.MAX_SKEW:
                                    r = self.client.buy( self.futtoks[token]['deribit'], round(round(self.qty*0.66) / 10),bids[i], 'true' )
                        else:
                            if  self.bidsleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                                #if self.qty + skew_size[token] <= self.MAX_SKEW:
                                    r = self.client.buy( self.futtoks[token]['deribit'], round(self.qty*0.66),bids[i], 'true' )
                        
                    if ex3 == 'bybit':
                        if  True:
                            #if self.qty + skew_size[token] <= self.MAX_SKEW:
                                r = self.bit.Order.Order_new(side="Buy",symbol=self.futtoks[token]['bybit'].replace('-bybit', ''),order_type="Limit",qty=round(self.qty*0.66),price=bids[i],time_in_force="PostOnly").result()
                      
                    #print('sell to reduce... ' + str(i))
                    extraPrint(False, self.len_ask_ords[fut])
                    
                    if ex == 'deribit':
                        
                        if 'BTC-PERPETUAL' == self.futtoks[token]['deribit']:
                                
                            #print('token1: ' + self.futtoks[token]['deribit'])
                            
                            #print('futtoks: ' + self.futtoks[token]['deribit'])
                            if  self.asksleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                                #if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                                    r = self.client.sell( self.futtoks[token]['deribit'], round(self.qty / 10),asks[i], 'true' )
                        else:
                            if  self.asksleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                                #if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                                    r = self.client.sell( self.futtoks[token]['deribit'], round(self.qty),asks[i], 'true' )
                    if ex == 'bybit':
                        extraPrint(False, self.len_ask_ords)
                        extraPrint(False, self.len_ask_ords[self.futtoks[token]['bybit']])
                        if  True:
                            #if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                                r = self.bit.Order.Order_new(side="Sell",symbol=self.futtoks[token]['bybit'].replace('-bybit', ''),order_type="Limit",qty=self.qty,price=asks[i],time_in_force="PostOnly").result()
                  

            if self.positions[self.futtoks[token][ex]]['size'] <= 0:
                ex3 = self.arbmult[token]['long']
                if ex3 == 'bitmex':
                    mexAsks = []
                    for i in range(self.bidsleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                        mexAsks.append({"symbol":self.futtoks[token]['bitmex'], "orderQty":-1*round(self.qty*0.66), "price":asks[i],"execInst":"ParticipateDoNotInitiate"})
                    
                    if  len(mexAsks) > 0:
                        #if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                            if self.domex == True:
                                r2 = Timer(0.5, self.mextimer, ())
                                r2.start()
                                #self.domex = False
                                r = self.mex.Order.Order_newBulk(orders=json.dumps(mexAsks)).result()
                if ex == 'bitmex':
                    mexBids = []
                    for i in range(self.bidsleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                        mexBids.append({"symbol":self.futtoks[token]['bitmex'], "orderQty":round(self.qty), "price":bids[i],"execInst":"ParticipateDoNotInitiate"})
                   
                    if  len(mexBids) > 0:
                        #if self.qty + skew_size[token] <= self.MAX_SKEW:
                            if self.domex == True:
                                r2 = Timer(0.5, self.mextimer, ())
                                r2.start()
                                #self.domex = False
                                r = self.mex.Order.Order_newBulk(orders=json.dumps(mexBids)).result()
                                #print(r)
                for i in range(self.bidsleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                    #print('sell the long arb opp at reduced qty')
                    
                    if ex3 == 'deribit':
                        
                        if 'BTC-PERPETUAL' == self.futtoks[token]['deribit']:
                                
                            #print('token1: ' + self.futtoks[token]['deribit'])
                            
                            #print('futtoks: ' + self.futtoks[token]['deribit'])
                            if  self.asksleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                                #if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                                    r = self.client.sell( self.futtoks[token]['deribit'], round(round(self.qty*0.66) / 10),asks[i], 'true' )
                        else:
                            if  self.asksleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                                #if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                                    r = self.client.sell( self.futtoks[token]['deribit'], round(round(self.qty*0.66)),asks[i], 'true' )
                    if ex3 == 'bybit':
                        extraPrint(False, self.len_ask_ords)
                        extraPrint(False, self.len_ask_ords[self.futtoks[token]['bybit']])
                        if  True:
                            #if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                                r = self.bit.Order.Order_new(side="Sell",symbol=self.futtoks[token]['bybit'].replace('-bybit', ''),order_type="Limit",qty=round(self.qty*0.66),price=asks[i],time_in_force="PostOnly").result()
    
                    #print('buy to reduce... ' + str(i))

                    extraPrint(False, self.len_bid_ords[fut])
                    
                    
                    
                    if ex == 'deribit':
                        
                        if 'BTC-PERPETUAL' == self.futtoks[token]['deribit']:
                            

                            #print('token2: ' + self.futtoks[token]['deribit'])
                            
                            #print('futtoks: ' + self.futtoks[token]['deribit'])
                            if  self.bidsleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                                if self.qty + skew_size[token] <= self.MAX_SKEW:
                                    r = self.client.buy( self.futtoks[token]['deribit'], round(self.qty / 10),bids[i], 'true' )
                        else:
                            if  self.bidsleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                                if self.qty + skew_size[token] <= self.MAX_SKEW:
                                    r = self.client.buy( self.futtoks[token]['deribit'], round(self.qty),bids[i], 'true' )
                        
                    if ex == 'bybit':
                        if  True:
                            if self.qty + skew_size[token] <= self.MAX_SKEW:
                                r = self.bit.Order.Order_new(side="Buy",symbol=self.futtoks[token]['bybit'].replace('-bybit', ''),order_type="Limit",qty=self.qty,price=bids[i],time_in_force="PostOnly").result()
                      
        """
            
            #print( 'No bid no offer for ' + fut + " " + ex)
        if ex is not self.arbmult[token]['short'] and ex is not self.arbmult[token]['long']:
            #print(ex + ' is not long OR short for ' + token)
            #print('min asks bids 7: ' + str(self.asksleft[self.futtoks[token][ex]]) + ', ' + str(self.bidsleft[self.futtoks[token][ex]]))
            
            if self.positions[self.futtoks[token][ex]]['size'] >= 0:
                if self.qty + skew_size[token] <= -1 *  self.MAX_SKEW:
                    if ex == 'bitmex':
                        mexAsks = []
                        for i in range(self.asksleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                            mexAsks.append({"symbol":self.futtoks[token]['bitmex'], "orderQty":-1*round(self.qty), "price":asks[i],"execInst":"ParticipateDoNotInitiate"})
                        
                        if  len(mexAsks) > 0:
                            #if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                                if self.domex == True:
                                    r2 = Timer(0.5, self.mextimer, ())
                                    r2.start()
                                    #self.domex = False
                                    r = self.mex.Order.Order_newBulk(orders=json.dumps(mexAsks)).result()
                #print('sell!')
                for i in range(self.asksleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                    #print(i)
                    #print(asks[i])
                    if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                        if ex == 'deribit':
                            
                            if 'BTC-PERPETUAL' == self.futtoks[token]['deribit']:
                                
                                #print('token1: ' + self.futtoks[token]['deribit'])
                                
                                #print('futtoks: ' + self.futtoks[token]['deribit'])
                                if  True:
                                    if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                                        r = self.client.sell( self.futtoks[token]['deribit'], round(self.qty / 10),asks[i], 'true' )
                            else:
                                if  True:
                                    if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                                        r = self.client.sell( self.futtoks[token]['deribit'], round(self.qty),asks[i], 'true' )
                        if ex == 'bybit':
                            extraPrint(False, self.len_ask_ords)
                            extraPrint(False, self.len_ask_ords[self.futtoks[token]['bybit']])
                            if  self.len_ask_ords[self.futtoks[token]['bybit']] <= self.MAX_LAYERS:
                                if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:

                                    r = self.bit.Order.Order_new(side="Sell",symbol=self.futtoks[token]['bybit'].replace('-bybit', ''),order_type="Limit",qty=self.qty,price=asks[i],time_in_force="PostOnly").result()

            if self.positions[self.futtoks[token][ex]]['size'] <= 0:
                #print('buy!')
                if self.qty + skew_size[token] <= self.MAX_SKEW:
                    if ex == 'bitmex':

                        mexBids = []
                        for i in range(self.bidsleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                            mexBids.append({"symbol":self.futtoks[token]['bitmex'], "orderQty":round(self.qty), "price":bids[i],"execInst":"ParticipateDoNotInitiate"})
                       
                        if  len(mexBids) > 0:
                            #if self.qty + skew_size[token] <= self.MAX_SKEW:
                                if self.domex == True:
                                    r2 = Timer(0.5, self.mextimer, ())
                                    r2.start()
                                    #self.domex = False
                                    r = self.mex.Order.Order_newBulk(orders=json.dumps(mexBids)).result()
                                    #print(r)
            
                for i in range(self.bidsleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                    if self.qty + skew_size[token] <= self.MAX_SKEW:
                        
                        if ex == 'deribit':
                            
                            if 'BTC-PERPETUAL' == self.futtoks[token]['deribit']:
                                

                                #print('token2: ' + self.futtoks[token]['deribit'])
                                
                                #print('futtoks: ' + self.futtoks[token]['deribit'])
                                if  True:
                                    if self.qty + skew_size[token] <= self.MAX_SKEW:
                                        r = self.client.buy( self.futtoks[token]['deribit'], round(self.qty / 10),bids[i], 'true' )
                            else:
                                if  True:   
                                    if self.qty + skew_size[token] <= self.MAX_SKEW:
                                        r = self.client.buy( self.futtoks[token]['deribit'], round(self.qty),bids[i], 'true' )
                            
                        if ex == 'bybit':
                            if  True:
                                if self.qty + skew_size[token] <= self.MAX_SKEW:
                                    r = self.bit.Order.Order_new(side="Buy",symbol=self.futtoks[token]['bybit'].replace('-bybit', ''),order_type="Limit",qty=self.qty,price=bids[i],time_in_force="PostOnly").result()

         
              
        if not place_bids and not place_asks:
           #print('not place asks or bids')
           #print('min asks bids 3: ' + str(self.asksleft[self.futtoks[token][ex]]) + ', ' + str(self.bidsleft[self.futtoks[token][ex]]))
            try:
                prc = self.get_bbo(ex, fut)['bid']
            except Exception as e:
                abc123 = 1
                #print('no bid, returning')
                
            if ex == 'bitmex':
                self.qty = round ( float(prc) * qtybtc )
                
            if self.qty > self.maxqty:
                self.maxqty = self.qty
            self.MAX_SKEW = self.MAX_SKEW_OLD
            self.MAX_SKEW = self.qty * 2.25
            extraPrint(False, token + ', ' + ex + ' qty: ' + str(self.qty / 10))
            if self.positions[self.futtoks[token][ex]]['size'] >= 0:
                if ex == 'bitmex':
                    if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                        mexAsks = []
                        for i in range(self.asksleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                            mexAsks.append({"symbol":self.futtoks[token]['bitmex'], "orderQty":-1*round(self.qty), "price":asks[i],"execInst":"ParticipateDoNotInitiate"})
                        
                        if  len(mexAsks) > 0:
                            #if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                                if self.domex == True:
                                    r2 = Timer(0.5, self.mextimer, ())
                                    r2.start()
                                    #self.domex = False
                                    r = self.mex.Order.Order_newBulk(orders=json.dumps(mexAsks)).result()
                                   #print(r)
                for i in range(self.asksleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                    #print('sell over max ' + str(i))
                    extraPrint(False, self.len_ask_ords[fut])
                    if ex == 'deribit':
                        
                        if 'BTC-PERPETUAL' == self.futtoks[token]['deribit']:
                                
                            #print('token1: ' + self.futtoks[token]['deribit'])
                            
                            #print('futtoks: ' + self.futtoks[token]['deribit'])
                            if  self.asksleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                                if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                                    r = self.client.sell( self.futtoks[token]['deribit'], round(self.qty / 10),asks[i], 'true' )
                                   #print(r)
                        else:
                            if  self.asksleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                                if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                                    r = self.client.sell( self.futtoks[token]['deribit'], round(self.qty),asks[i], 'true' )
                                   #print(r)
                    if ex == 'bybit':
                        extraPrint(False, self.len_ask_ords)
                        extraPrint(False, self.len_ask_ords[self.futtoks[token]['bybit']])
                        if  True:
                            if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                                r = self.bit.Order.Order_new(side="Sell",symbol=self.futtoks[token]['bybit'].replace('-bybit', ''),order_type="Limit",qty=self.qty,price=asks[i],time_in_force="PostOnly").result()
                  
                               #print(r)

            if self.positions[self.futtoks[token][ex]]['size'] <= 0:
                if self.qty + skew_size[token] <= self.MAX_SKEW:
                    if ex == 'bitmex':

                        mexBids = []
                        for i in range(self.bidsleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                            mexBids.append({"symbol":self.futtoks[token]['bitmex'], "orderQty":round(self.qty), "price":bids[i],"execInst":"ParticipateDoNotInitiate"})
                       
                        if  len(mexBids) > 0:
                            #if self.qty + skew_size[token] <= self.MAX_SKEW:
                                if self.domex == True:
                                    r2 = Timer(0.5, self.mextimer, ())
                                    r2.start()
                                    #self.domex = False
                                    r = self.mex.Order.Order_newBulk(orders=json.dumps(mexBids)).result()
                                    #print(r)
                                   #print(r)
                for i in range(self.bidsleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                    #print('buy over max ' + str(i))

                    extraPrint(False, self.len_bid_ords[fut])
                    if ex == 'deribit':
                        
                        if 'BTC-PERPETUAL' == self.futtoks[token]['deribit']:
                            

                            #print('token2: ' + self.futtoks[token]['deribit'])
                            
                            #print('futtoks: ' + self.futtoks[token]['deribit'])
                            if  self.bidsleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                                if self.qty + skew_size[token] <= self.MAX_SKEW:
                                    r = self.client.buy( self.futtoks[token]['deribit'], round(self.qty / 10),bids[i], 'true' )
                                   #print(r)
                        else:
                            if  self.bidsleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                                if self.qty + skew_size[token] <= self.MAX_SKEW:
                                    r = self.client.buy( self.futtoks[token]['deribit'], round(self.qty),bids[i], 'true' )
                        
                                   #print(r)
                    if ex == 'bybit':
                        if  True:
                            if self.qty + skew_size[token] <= self.MAX_SKEW:
                                r = self.bit.Order.Order_new(side="Buy",symbol=self.futtoks[token]['bybit'].replace('-bybit', ''),order_type="Limit",qty=self.qty,price=bids[i],time_in_force="PostOnly").result()
                      

            #print( 'No bid no offer for ' + fut + " " + ex)
            
        #return    
        #print(r)
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

        self.execute_arb (ex, fut, skew_size, nbids, nasks, place_bids, place_asks, bids, asks, qtybtc, con_sz, tsz, cancel_oids )    


    def execute_arb ( self, ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, qtybtc, con_sz, tsz, cancel_oids):
        
        #print('execute_arb')
        token = 'BTC'
        if 'ETH' in fut:
            token = 'ETH'
        try:
            prc = self.get_bbo(ex, fut)['bid']
        except Exception as e:
            abc123 = 1
            #print('no bid, returning')
            
        if ex == 'bitmex':
            self.qty = round ( float(prc) * qtybtc )
        if self.qty > self.maxqty:
            self.maxqty = self.qty
        
        extraPrint(False, token + ', ' + ex + ' qty: ' + str(self.qty / 10))
        self.MAX_SKEW = self.MAX_SKEW_OLD
        self.MAX_SKEW = self.qty * 2.25

        
        
        
        
        
            
        self.execute_longs (  ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, qtybtc, con_sz, tsz, cancel_oids)
        
        #self.execute_shorts (  ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, qtybtc, con_sz, tsz, cancel_oids)

    def execute_longs ( self,  ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, qtybtc, con_sz, tsz, cancel_oids):
        
        #print('execute_long')
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
        if self.positions[fut]['floatingPl'] > 0.1 and math.fabs(self.positions[fut]['size']) > avg * 1.05:
            extraPrint(False, fut + ' in profit and 1.05x average in size! Maybe reduce!')
    
    
   
        
    
    
    # short Reduce
            asks = []
            bids = []
            bbo = self.get_bbo(ex, self.futtoks[token][ex])
            asks.append(bbo['ask'])
            bids.append(bbo['bid'])

            if self.positions[fut]['size'] > 0:
                if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                    if 'XBT' in fut or fut == 'ETHUSD':
                        mexAsks = []
                        for i in range(self.asksleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                            mexAsks.append({"symbol":self.futtoks[token]['bitmex'], "orderQty":-1*round(self.qty), "price":asks[i],"execInst":"ParticipateDoNotInitiate"})
                        
                        if  len(mexAsks) > 0:
                            #if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                                if self.domex == True:
                                    r2 = Timer(0.5, self.mextimer, ())
                                    r2.start()
                                    #self.domex = False
                                    r = self.mex.Order.Order_newBulk(orders=json.dumps(mexAsks)).result()
                #print('min asks bids 6: ' + str(self.asksleft[self.futtoks[token][ex]]) + ', ' + str(self.bidsleft[self.futtoks[token][ex]]))
                for i in range(self.asksleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                    if 'PERPETUAL' in fut and self.asksleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                    # deribit
                        
                        if 'BTC-PERPETUAL' == self.futtoks[token]['deribit']:
                            
                            
                            #print('token5: ' + self.futtoks[token]['deribit'])
                            
                            #print('futtoks: ' + self.futtoks[token]['deribit'])
                            if  self.asksleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                                if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                                    self.client.sell( self.futtoks[token]['deribit'], round(self.qty / 10),asks[i], 'true' )
                        else:
                            if  self.asksleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                                if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                                    self.client.sell( self.futtoks[token]['deribit'], round(self.qty),asks[i], 'true' )
                            

                    if 'bybit' in fut or 'BTCUSD' == fut:
                    # bybit
                        extraPrint(False, self.len_ask_ords)
                        extraPrint(False, self.len_ask_ords[self.futtoks[token]['bybit']])

                        if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:

                            
                            self.bit.Order.Order_new(side="Sell",symbol=self.futtoks[token]['bybit'].replace('-bybit', ''),order_type="Limit",qty=self.qty,price=asks[i],time_in_force="PostOnly").result()
                      
                
    # long reduce
    
            else:
                if 'XBT' in fut or fut == 'ETHUSD':
                    if self.qty + skew_size[token] <= self.MAX_SKEW:
                        mexBids = []
                        for i in range(self.bidsleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                            mexBids.append({"symbol":self.futtoks[token]['bitmex'], "orderQty":round(self.qty), "price":bids[i],"execInst":"ParticipateDoNotInitiate"})
                       
                        if  len(mexBids) > 0:
                            #if self.qty + skew_size[token] <= self.MAX_SKEW:
                                if self.domex == True:
                                    r2 = Timer(0.5, self.mextimer, ())
                                    r2.start()
                                    #self.domex = False
                                    r = self.mex.Order.Order_newBulk(orders=json.dumps(mexBids)).result()
                                    #print(r)
                #print('min asks bids 1: ' + str(self.asksleft[self.futtoks[token][ex]]) + ', ' + str(self.bidsleft[self.futtoks[token][ex]]))
                for i in range(self.bidsleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                    if 'PERPETUAL' in fut:
                    # deribit
                        
                        if 'BTC-PERPETUAL' == self.futtoks[token]['deribit']:
                            
                            
                            #print('token6: ' + self.futtoks[token]['deribit'])
                            
                            #print('futtoks: ' + self.futtoks[token]['deribit'])
                            if  self.bidsleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                                if self.qty + skew_size[token] <= self.MAX_SKEW:
                                    self.client.buy( self.futtoks[token]['deribit'], round(self.qty / 10),bids[i], 'true' )
                        else:
                            if  self.bidsleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                                if self.qty + skew_size[token] <= self.MAX_SKEW:
                                    self.client.buy( self.futtoks[token]['deribit'], round(self.qty),bids[i], 'true' )
                            
                    
                    if 'bybit' in fut or 'BTCUSD' == fut:
                    # bybit
                        if self.qty + skew_size[token] <= self.MAX_SKEW:
                            self.bit.Order.Order_new(side="Buy",symbol=self.futtoks[token]['bybit'].replace('-bybit', ''),order_type="Limit",qty=self.qty,price=bids[i],time_in_force="PostOnly").result()
            
                                    
    # Long add on winning ex, short other ex - or rather 
 #       if  self.bidsleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:

#            self.client.buy( 'BTC-PERPETUAL', 3, self.get_bbo('deribit', 'BTC-PERPETUAL')['bid'], 'true' )
        asks = []
        bids = []
        askbids = self.get_asks_bids(ex, token)
        asks = askbids['asks']
        bids = askbids['bids']
        #print('min asks bids 2: ' + str(self.asksleft[self.futtoks[token][ex]]) + ', ' + str(self.bidsleft[self.futtoks[token][ex]]))
        longing = self.arbmult[token]['long']
        shorting = self.arbmult[token]['short']

        if longing == ex and ex == 'bitmex':
            if self.qty + skew_size[token] <= self.MAX_SKEW and place_bids == True:
                mexBids = []
                for i in range(self.bidsleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                    mexBids.append({"symbol":self.futtoks[token]['bitmex'], "orderQty":round(self.qty), "price":bids[i],"execInst":"ParticipateDoNotInitiate"})
               
                if  len(mexBids) > 0:
                    #if self.qty + skew_size[token] <= self.MAX_SKEW:
                        if self.domex == True:
                            r2 = Timer(0.5, self.mextimer, ())
                            r2.start()
                            #self.domex = False
                            r = self.mex.Order.Order_newBulk(orders=json.dumps(mexBids)).result()
                            #print(r)
        if shorting == ex and ex == 'bitmex':   
            if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                mexAsks = []
                for i in range(self.asksleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)):
                    mexAsks.append({"symbol":self.futtoks[token]['bitmex'], "orderQty":-1*round(self.qty), "price":asks[i],"execInst":"ParticipateDoNotInitiate"})
                
                if  len(mexAsks) > 0:
                    #if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                        if self.domex == True:
                            r2 = Timer(0.5, self.mextimer, ())
                            r2.start()
                            #self.domex = False
                            r = self.mex.Order.Order_newBulk(orders=json.dumps(mexAsks)).result() 
        for i in range(self.bidsleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)): 
            if longing == 'deribit' and ex == 'deribit':
                
                if self.qty + skew_size[token] <= self.MAX_SKEW and place_bids == True:
                    if 'BTC-PERPETUAL' == self.futtoks[token]['deribit']:
                        if  self.bidsleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                            self.client.buy( self.futtoks[token]['deribit'], round(self.qty / 10),bids[i], 'true' )
                    else:
                        if  self.bidsleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                            self.client.buy( self.futtoks[token]['deribit'], round(self.qty),bids[i], 'true' )

        
            if longing == 'bybit' and ex == 'bybit':
                    if self.qty + skew_size[token] <= self.MAX_SKEW and place_bids == True:
                        
                        if  True:
                            r = self.bit.Order.Order_new(side="Buy",symbol=self.futtoks[token]['bybit'].replace('-bybit', ''),order_type="Limit",qty=self.qty,price=bids[i],time_in_force="PostOnly").result()
           
       
        for i in range(self.asksleft[self.futtoks[token][ex]], round(self.MAX_LAYERS)): 
            if shorting == 'bybit' and ex =='bybit':
                if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                    r = self.bit.Order.Order_new(side="Sell",symbol=self.futtoks[token]['bybit'].replace('-bybit', ''),order_type="Limit",qty=self.qty,price=asks[i],time_in_force="PostOnly").result()
            if shorting == 'deribit' and ex =='deribit':
                if self.qty + skew_size[token] * -1 <= self.MAX_SKEW:
                    if 'BTC-PERPETUAL' == self.futtoks[token]['deribit']:
                            
                        
                        #print('token8: ' + self.futtoks[token]['deribit'])
                        
                        #print('futtoks: ' + self.futtoks[token]['deribit'])
                        if  self.asksleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:

                            self.client.sell( self.futtoks[token]['deribit'], round(self.qty / 10),asks[i], 'true' )
                    else:
                        if  self.asksleft[self.futtoks[token][ex]] <= self.MAX_LAYERS:
                            self.client.sell( self.futtoks[token]['deribit'], round(self.qty),asks[i], 'true' )
       

        self.execute_cancels(ex, fut, skew_size[token],  nbids, nasks, place_bids, place_asks, bids, asks, qtybtc, con_sz, tsz, cancel_oids)


        
    def execute_cancels(self, ex, fut, skew_size,  nbids, nasks, place_bids, place_asks, bids, asks, qtybtc, con_sz, tsz, cancel_oids):
        if ex == 'deribit':
            for oid in cancel_oids:
                try:
                    abc123 = 1
                    #self.client.cancel( oid )
                except Exception as e:
                    self.logger.warn( 'Order cancellations failed: %s' % oid )
        if ex == 'bybit':
            
            #if nbids < len( self.bid_ords[self.futtoks[token][ex]] ):
            #    cancel_oids += [ o[ 'orderID' ] for o in self.bid_ords[self.futtoks[token][ex]][ nbids : ]]
            #if nasks < len( self.ask_ords[self.futtoks[token][ex]] ):
            #    cancel_oids += [ o[ 'orderID' ] for o in self.ask_ords[self.futtoks[token][ex]][ nasks : ]]
            
            for oid in cancel_oids:
                try:
                    abc123 = 1
                    #self.bit.Order.Order_cancel(order_id=oid).result()
                except Exception as e:
                    extraPrint(False, e)
                    PrintException()#abc=123#PrintException()
                    self.logger.warn( 'Order cancellations failed: %s' % oid )

        if ex == 'bitmex':
            for oid in cancel_oids:
                try:
                    #print('Try cancelled bitmex order... ' + str(oid))
                #    self.mex.Order.Order_cancel(orderID=oid).result()
                    abc123 = 1
                except Exception as e:
                    extraPrint(False, e)
                    PrintException()#abc=123#PrintException()
                    self.logger.warn( 'Order cancellations failed: %s' % oid )
    def restart( self ):        
        try:
            strMsg = 'RESTARTING'
            extraPrint(False,  strMsg )
            
            self.client.cancelall()
            extraPrint(False, 'cancel 1')
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
            extraPrint(False, e)
            pass
        finally:
            os.execv( sys.executable, [ sys.executable ] + sys.argv )        
            
    


    def run( self ):
        
        self.run_first()
        
        t_ts = t_out = t_loop = t_mtime = datetime.utcnow()

        while True:

            self.get_futures()
            
            
            
            self.update_rates()
            r = random.randint(0, 50)
            if r == 0:
                self.update_balances()  
            
            #self.update_positions()
        
            t_now   = datetime.utcnow()
            
            # Update time series and vols
            if ( t_now - t_ts ).total_seconds() >= WAVELEN_TS:
                t_ts = t_now
            sleep(0.01)
            size = int (100)
            """
            sleep(4)
            extraPrint(False, 'cancel 2')

            ords        = self.deri_orders
            self.deri_orders = []
            ords2 = []
            if len(ords) == 0:
                ords        = self.client.getopenorders( 'BTC-PERPETUAL' )
                ords2        = self.client.getopenorders( 'ETH-PERPETUAL' )
            
            for order in ords:
                try:
                    if 'order_id' in order:
                        self.client.cancel(order['order_id'])
                    else:
                        self.client.cancel(order['orderId'])
                except:
                    extraPrint(False, 'btc')
                    extraPrint(False, order)

            for order in ords2:
                try:
                    self.client.cancel(order['orderId'])
                except:
                    extraPrint(False, 'eth')
                    extraPrint(False, order)
            self.mex.Order.Order_cancelAll(symbol='ETHUSD').result()
            self.bit.Order.Order_cancelAll(symbol='BTCUSD').result()
            self.mex.Order.Order_cancelAll(symbol='XBTUSD').result()
            self.bit.Order.Order_cancelAll(symbol='ETHUSD').result()
            """ 
            self.doneFuts = []

            for ex in self.totrade:
                #self.update_mex_bit_pos_and_order()
                for token in self.exchangeRates:
                    #print(token + ' ' + ex)
                    
                    
                    self.place_orders(ex, token)
            #print('out of loop!')
            #self.place_orders()

            
            # Display status to terminal
            if self.output:    
                t_now   = datetime.utcnow()
                if ( t_now - t_out ).total_seconds() >= WAVELEN_OUT:
                     t_out = t_now
            self.output_status();
            
            # Restart if file change detected
            
           
            t_now       = datetime.utcnow()
            looptime    = ( t_now - t_loop ).total_seconds()
            
            t1  = looptime
            t2  = self.mean_looptime
            
            self.mean_looptime = t1
            
            t_loop      = t_now


    def run_first( self ):
       #print('---!!!--- new run ---!!!---')
        
        self.get_futures()
       #print(1)
        for ex in self.futures:
            for pair in self.futures[ex]:

                self.positions[pair] = {
                'size':         0,
                'averagePrice': None,
                'floatingPl': 0}
        
        for token in self.futtoks:
            for ex in self.futtoks[token]:
                self.len_bid_ords[self.futtoks[token][ex]] = 0
                self.len_ask_ords[self.futtoks[token][ex]] = 0
                self.bid_ords[self.futtoks[token][ex]]        = []
                        
                self.ask_ords[self.futtoks[token][ex]]        = []

                self.bidsleft[self.futtoks[token][ex]] = 0
                self.asksleft[self.futtoks[token][ex]] = 0
                self.bidsleftbefore[self.futtoks[token][ex]] = 0
                self.asksleftbefore[self.futtoks[token][ex]] = 0
                #self.orderStates[ex] = []
        
        
        
        ex = 'bitmex'
        for fut in self.futures['bitmex']:
            positions = requests.get("http://localhost:4444/position?symbol=" + fut).json()

            for pos in positions:
                size = pos['currentQty']
                avgEntry = pos['avgEntryPrice']
                floatingPl = pos['unrealisedPnlPcnt']
                #if 'ETH' in pos['symbol']:
                    #extraPrint(False, pos)
                    #extraPrint(False, self.ethrate)
                self.positions[pos['symbol']] = {
                    'name': pos['symbol'],
                    'size':         size,
                    'averagePrice': avgEntry,
                    'floatingPl': floatingPl}
        self.client.cancelall()
       #print(2)
        extraPrint(False, 'cancel 4')
        self.mex.Order.Order_cancelAll(symbol='ETHUSD').result()
        self.bit.Order.Order_cancelAll(symbol='BTCUSD').result()
        self.mex.Order.Order_cancelAll(symbol='XBTUSD').result()
        self.bit.Order.Order_cancelAll(symbol='ETHUSD').result()
            
        self.logger = get_logger( 'root', LOG_LEVEL )
        # Get all futures contracts
        if testing == False:
            #extraPrint(False, 'initiating bitmex websocket connections, this may take a second... note Bitmex closes websocket connections after 24hr, so this algorithm is set to restart itself then for you :)')    
            delta = timedelta(hours=23)
            nearly_one_day = (start_time + delta)
            wait_seconds = (nearly_one_day - start_time).seconds  
            r = Timer(wait_seconds, self.restart, ())
            r.start()
       
            #for k in self.futures['bitmex']:
            #    self.ws[k] = (BitMEXWebsocket(endpoint="https://www.bitmex.com/api/v1", symbol=k, api_key="hYWO6-TaiH-FC5kDGUTGP-hO", api_secret="Cz92m7jRam3JTWHQZwiIKWUcSl5jvexquXldAM79kWmRzqvW"))
             #   extraPrint(False, k + ' websocket started!')
            #extraPrint(False, 'setting that timer for ' + str(wait_seconds / 60 / 60) + ' hours...')
        delta = timedelta(hours=15)
        nearly_one_day = (start_time + delta)
        wait_seconds = (nearly_one_day - start_time).seconds  
        if testing == True:
            r = Timer(wait_seconds, self.restart, ())
            r.start()
        self.update_balances()

       #print(3)
        
        try:

            loop = asyncio.get_event_loop()
           #print('launch lopo in thread..')
            t = threading.Thread(target=self.der_pos)
            t.start()
            t = threading.Thread(target=self.der_ords)
            t.start()
            t = threading.Thread(target=self.mex_pos)
            t.start()
            t = threading.Thread(target=self.mex_ords)
            t.start()
            t = threading.Thread(target=self.bit_pos)
            t.start()
            t = threading.Thread(target=self.bit_ords)
            t.start()
            t = threading.Thread(target=self.loop_in_thread, args=(loop,))
            t.start()
        except Exception as e:
            PrintException()#abc=123#PrintException()


        #self.update_positions()
        

        self.update_rates()

       #print(4)
        for token in self.futtoks:
            for ex in self.futtoks[token]:
                extraPrint(False, [token, ex])
                self.calculate_eth_btc(token, ex) 
        self.start_time         = datetime.utcnow()

        self.equity_btc = self.bals['total']

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
        extraPrint(False, dir(bitmex))
        
        self.update_status()

       #print(5)
        
        for ex in self.totrade:
            for fut in self.futures[ex]:
                positions       = self.client.positions()
                for pos in positions:
                    if pos['instrument'] == fut:

                        if pos[ 'instrument' ] in self.futures['deribit']:
                            if 'BTC' in pos[ 'instrument' ]:
                               
                                pos['size'] = pos['size'] * 10
                            self.positions[ pos[ 'instrument' ]] = pos

        asksbids = self.get_asks_bids('bitmex', 'BTC')
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
            PrintException()#abc=123#PrintException()

        
        spot    = self.get_spot('BTC')
        t = 0
        
        
        self.equity_btc = self.bals['total']

        
        self.equity_usd = self.equity_btc * spot


        #self.update_positions()
                
     


mmbot = MarketMaker( monitor = False, output = True )       
if __name__ == '__main__':
    if testing == True:
        try:
            os.remove('log.txt')
        except Exception as e:
            abc123 = 1
    try:
        (mmbot.run())
    except( KeyboardInterrupt, SystemExit ):
        extraPrint(False,  "Cancelling open orders" )
        if testing == False:
            try:
                os.rename('log.txt', 'log-' + str(start_time) + '.txt')
            except Exception as e:
                abc123 = 1
        
        mmbot.client.cancelall()
        extraPrint(False, 'cancel 3')
        mmbot.mex.Order.Order_cancelAll(symbol='XBTUSD').result()
        mmbot.mex.Order.Order_cancelAll(symbol='ETHUSD').result()
        mmbot.bit.Order.Order_cancelAll(symbol='ETHUSD').result()
        mmbot.bit.Order.Order_cancelAll(symbol='BTCUSD').result()
        
        sys.exit()
    except Exception as e:
       #print('restarting...'
        #print(str(e))
        print  (     traceback.format_exc())
        mmbot.restart()
    