import market_maker
from time import sleep
market_maker.mmbot.get_futures()

import pymongo
from pymongo import MongoClient
client = MongoClient()
db = client.market_maker
dbpositions = db.positions

while True:
    sleep(1)
    try:
        ex = 'deribit'

        positions       = market_maker.mmbot.client.positions()
        for pos in positions:
            fut = pos['instrument']

            if pos[ 'instrument' ] in market_maker.mmbot.futures['deribit']:
                if 'BTC' in pos[ 'instrument' ]:
                   
                    pos['size'] = pos['size'] * 10
                pos['name'] = pos[ 'instrument' ]
                dbpositions.update({'name': pos[ 'instrument' ]}, pos, upsert=True);
    except Exception as e:
        market_maker.PrintException()