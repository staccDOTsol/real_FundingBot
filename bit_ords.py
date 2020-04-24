import market_maker
from time import sleep
market_maker.mmbot.get_futures()

import pymongo
from pymongo import MongoClient
client = MongoClient()
db = client.market_maker
ask_ords = db.ask_ords
bid_ords = db.bid_ords

while True:
    sleep(1)
    try:
        ex = 'bybit'


        count = 0
        for token in market_maker.mmbot.exchangeRates:

            brem = False
            arem = False
            addBidOrders = []
            addAskOrders = []
            ords2 = []
            print(market_maker.mmbot.futtoks[token][ex].replace('-bybit', ''))
            ords = market_maker.mmbot.bit.Order.Order_getOrders(order="true",symbol=market_maker.mmbot.futtoks[token][ex].replace('-bybit', '')).result()[0]['result']
            
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
                        print('bybit order')
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
                        
                        order['name'] = market_maker.mmbot.futtoks[token][ex]
                        if order[ 'side' ].lower() == 'buy':
                            addBidOrders.append(order)
                        elif order[ 'side' ].lower() == 'sell':
                            addAskOrders.append(order)
                   
            ask_ords.update({'name': market_maker.mmbot.futtoks[token][ex]}, {'name': market_maker.mmbot.futtoks[token][ex],"asks": addAskOrders}, upsert=True);
            bid_ords.update({'name': market_maker.mmbot.futtoks[token][ex]}, {'name': market_maker.mmbot.futtoks[token][ex],"bids": addBidOrders}, upsert=True);
                    #self.orderStates[ex].append(order['orderID'])

            #print('bybit #self.orderStates[ex]')
            #print(#self.orderStates[ex])

    except Exception as e:
        market_maker.PrintException()
