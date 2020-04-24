import market_maker
from time import sleep
market_maker.mmbot.get_futures()

import pymongo
from pymongo import MongoClient
client = MongoClient()
db = client.market_maker
dbpositions = db.positions

ex = 'bybit'
while True:
    sleep(1)
    try:
        for fut in market_maker.mmbot.futures['bybit']:
            positions = market_maker.mmbot.bit.Positions.Positions_myPosition().result()[0]['result']
            for pos in positions:   
                if pos[ 'symbol' ] in market_maker.mmbot.futures['bybit'] or pos['symbol'] == 'ETHUSD':
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
                    dbpositions.update({'name': name}, toinsert, upsert=True);
                    
                
    except Exception as e:
        
        market_maker.PrintException()
