import market_maker
from time import sleep
market_maker.mmbot.get_futures()
import requests
import pymongo
from pymongo import MongoClient
client = MongoClient()
db = client.market_maker
dbpositions = db.positions

while True:
    sleep(1)
    try:

        ex = 'bitmex'
        for fut in market_maker.mmbot.futures['bitmex']:
            positions = requests.get("http://localhost:4444/position?symbol="+fut).json()
            for pos in positions:
                size = pos['currentQty']
                avgEntry = pos['avgEntryPrice']
                floatingPl = pos['unrealisedPnlPcnt']
                #if 'ETH' in pos['symbol']:
                    #extraPrint(False, pos)
                    #extraPrint(False, self.ethrate)
                
                dbpositions.update({'name': pos['symbol']}, {
                    'name': pos['symbol'],
                    'size':         size,
                    'averagePrice': avgEntry,
                    'floatingPl': floatingPl}, upsert=True);
    except:
        market_maker.PrintException()