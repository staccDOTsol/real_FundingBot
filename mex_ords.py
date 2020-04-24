import market_maker
from time import sleep
market_maker.mmbot.get_futures()
import requests
import pymongo
from pymongo import MongoClient
client = MongoClient()
db = client.market_maker
ask_ords = db.ask_ords
bid_ords = db.bid_ords

while True:
    sleep(1)
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
                if order['ordStatus'].lower() == 'new':
                    #print('bitmex order!')
                    #print('mex order')

                    order['status'] = 'new'
                       
                    
                    order['name'] = market_maker.mmbot.futtoks[token][ex]
                    if order[ 'side' ].lower() == 'buy':
                        addBidOrders.append(order)
                    elif order[ 'side' ].lower() == 'sell':
                        addAskOrders.append(order)
                
        
            ask_ords.update({'name': market_maker.mmbot.futtoks[token][ex]}, {'name': market_maker.mmbot.futtoks[token][ex],'asks':addAskOrders}, upsert=True);
            bid_ords.update({'name': market_maker.mmbot.futtoks[token][ex]}, {'name': market_maker.mmbot.futtoks[token][ex],"bids":addBidOrders}, upsert=True);

    
    except Exception as e:
        market_maker.PrintException()