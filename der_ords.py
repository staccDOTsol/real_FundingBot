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
        brem = False
        arem = False
        ex = 'deribit'
        count = 0
        for token in market_maker.mmbot.exchangeRates:
            ords = market_maker.mmbot.client.getopenorders(market_maker.mmbot.futtoks[token][ex])
            
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
                order['name'] = market_maker.mmbot.futtoks[token][ex]
                if order[ 'side' ].lower() == 'buy':
                    newbidords.append(o)
                elif order[ 'side' ].lower() == 'sell':

                    newaskords.append(o)
                    #self.orderStates[ex].append(order['orderID'])
                

            
            #prnt('deribit #self.orderStates[ex]')                  
            #print(#self.orderStates[ex])
            
            ask_ords.update({'name': market_maker.mmbot.futtoks[token][ex]}, {'name': market_maker.mmbot.futtoks[token][ex],"asks": newaskords}, upsert=True);
            bid_ords.update({'name': market_maker.mmbot.futtoks[token][ex]}, {'name': market_maker.mmbot.futtoks[token][ex],"bids": newbidords}, upsert=True);

            #for order in self.bid_ords[self.futtoks[token][ex]]:

    except Exception as e:
        market_maker.PrintException()
